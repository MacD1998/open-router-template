"""Formatting + table helpers for model and endpoint pricing.

OpenRouter quotes prices in dollars *per token*. Humans think in dollars per
million tokens, so everything here converts and formats defensively: any
missing or unparseable field becomes "-" rather than crashing.
"""


def per_million(per_token):
    """Convert a $/token string|number to a float $/million, or None."""
    try:
        return float(per_token) * 1_000_000
    except (TypeError, ValueError):
        return None


def fmt_price(per_token):
    """Format a $/token value as "$X.XXXX" per million, or "-" if absent."""
    value = per_million(per_token)
    if value is None:
        return "-"
    return f"${value:,.4f}"


def trunc(text, width):
    """Truncate a string to ``width`` chars, adding an ellipsis if cut."""
    text = str(text)
    return text if len(text) <= width else text[: width - 1] + "…"


def print_table(headers, rows):
    """Print a left-aligned, auto-width column table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def render(cells):
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells))

    print(render(headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(render(row))


def model_rows(models, limit=10):
    """Build (id, name, in $/M, out $/M) rows for a list of model dicts."""
    rows = []
    for m in models[:limit]:
        pricing = m.get("pricing") or {}
        rows.append(
            (
                trunc(m.get("id", "?"), 40),
                trunc(m.get("name", "?"), 30),
                fmt_price(pricing.get("prompt")),
                fmt_price(pricing.get("completion")),
            )
        )
    return rows


def endpoint_rows(endpoints, limit=10):
    """Build provider pricing rows, sorted cheapest-first by completion price.

    Cache pricing keys (``input_cache_read`` / ``input_cache_write``) are not
    exposed by every provider, hence the defensive ``.get`` + "-" fallback.
    """
    def completion_price(ep):
        value = per_million((ep.get("pricing") or {}).get("completion"))
        return value if value is not None else float("inf")

    ordered = sorted(endpoints, key=completion_price)
    rows = []
    for ep in ordered[:limit]:
        pricing = ep.get("pricing") or {}
        rows.append(
            (
                trunc(ep.get("provider_name", "?"), 20),
                trunc(ep.get("quantization") or "-", 8),
                fmt_price(pricing.get("prompt")),
                fmt_price(pricing.get("completion")),
                fmt_price(pricing.get("input_cache_read")),
                fmt_price(pricing.get("input_cache_write")),
            )
        )
    return rows
