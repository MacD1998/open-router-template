"""Accumulate token + cost usage across multiple OpenRouter calls.

The key lesson encoded here: the billing-grade numbers (real ``cost``, cached
token counts, serving ``provider``) come from OpenRouter-specific fields in the
RAW response JSON, not the SDK's tidy ``usage`` object. ``extract_usage`` digs
them out defensively, and ``UsageTracker`` sums them.
"""

from collections import Counter

from pricing import fmt_price, print_table


def extract_usage(raw):
    """Pull the OpenRouter-specific accounting fields out of a raw response.

    ``raw`` is ``response.model_dump()``. Everything is read with ``.get`` and
    ``or 0`` so a provider that omits a field never crashes the run.
    """
    usage = raw.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}

    return {
        # Provider that actually served the request (lives at the top level).
        "provider": raw.get("provider") or "unknown",
        "input_tokens": usage.get("prompt_tokens") or 0,
        "output_tokens": usage.get("completion_tokens") or 0,
        # Cache reads/writes are reported under prompt_tokens_details when present.
        "cache_read_tokens": prompt_details.get("cached_tokens") or 0,
        "cache_write_tokens": (
            usage.get("cache_creation_input_tokens")
            or prompt_details.get("cache_creation_tokens")
            or 0
        ),
        # REAL billed cost in USD — not an estimate from a price table.
        "cost": usage.get("cost") or 0.0,
    }


class UsageTracker:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.cost = 0.0
        self.providers = Counter()

    def add(self, usage):
        """Add one ``extract_usage`` result to the running totals."""
        self.input_tokens += usage["input_tokens"]
        self.output_tokens += usage["output_tokens"]
        self.cache_read_tokens += usage["cache_read_tokens"]
        self.cache_write_tokens += usage["cache_write_tokens"]
        self.cost += usage["cost"]
        self.providers[usage["provider"]] += 1

    def provider_breakdown(self):
        """e.g. "DeepInfra x2, Novita x1" (most-used provider first)."""
        return ", ".join(
            f"{name} x{count}" for name, count in self.providers.most_common()
        )

    def print_summary(self):
        print_table(
            ["metric", "value"],
            [
                ("Total input tokens", f"{self.input_tokens:,}"),
                ("Total output tokens", f"{self.output_tokens:,}"),
                ("Total cache read tokens", f"{self.cache_read_tokens:,}"),
                ("Total cache write tokens", f"{self.cache_write_tokens:,}"),
                ("Total cost (USD)", f"${self.cost:.6f}"),
                ("Providers", self.provider_breakdown() or "-"),
            ],
        )
        print(
            "\nNote: 'Total cost' is the REAL billed amount summed from each "
            "response's usage.cost field, not an estimate."
        )
