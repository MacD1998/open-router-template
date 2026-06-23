"""OpenRouter usage + pricing reference (standalone CLI).

Run with no arguments:  python main.py

It walks through five phases:
  1. List available models (with pricing) from the live catalog.
  2. Resolve the selected model from OPENROUTER_MODEL.
  3. List per-provider pricing (endpoints) for that model.
  4. Run a few sample chat calls with live progress + real cost accounting.
  5. Print a final token/cost usage summary.

This is a teaching reference: plain OpenAI SDK pointed at OpenRouter, no web
UI, no agent framework.
"""

import os
import sys

from dotenv import load_dotenv

import openrouter_client as orc
from openrouter_client import OpenRouterError
from pricing import endpoint_rows, model_rows, print_table
from usage_tracker import UsageTracker, extract_usage

# Used only if OPENROUTER_MODEL is not set in the environment.
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"

SAMPLE_PROMPTS = [
    "What is 2+2?",
    "Name a color.",
    "Say hello in French.",
]


def phase_1_list_models():
    print("=== Available models (showing 10) ===")
    models = orc.list_models()
    if not models:
        print("(no models returned)")
        return
    print_table(
        ["id", "name", "input $/M", "output $/M"],
        model_rows(models, limit=10),
    )


def phase_2_selected_model():
    model = os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
    print(f"\n=== Selected model: {model} ===")
    return model


def phase_3_provider_pricing(model):
    print(f"\n=== Providers for {model} (showing 10) ===")
    data = orc.list_endpoints(model)
    endpoints = data.get("endpoints", []) if isinstance(data, dict) else []
    if not endpoints:
        print("(no provider endpoints returned for this model)")
        return
    print_table(
        ["provider", "quant", "input $/M", "output $/M", "cache_read $/M", "cache_write $/M"],
        endpoint_rows(endpoints, limit=10),
    )


def phase_4_sample_calls(client, model, tracker):
    print(f"\n=== Running {len(SAMPLE_PROMPTS)} sample calls ===")
    total = len(SAMPLE_PROMPTS)
    for i, prompt in enumerate(SAMPLE_PROMPTS, start=1):
        # Print without a newline first, then flush so progress is live, not
        # buffered until the end.
        print(f"[{i}/{total}] LLM request...", end="", flush=True)
        try:
            raw = orc.chat_completion(client, model, prompt)
        except OpenRouterError as exc:
            print(f" FAILED ({exc})")
            continue
        usage = extract_usage(raw)
        tracker.add(usage)
        print(
            f" done  (provider={usage['provider']}, "
            f"cost=${usage['cost']:.6f})"
        )


def phase_5_summary(tracker):
    print("\n=== Usage summary (real billed values) ===")
    tracker.print_summary()


def main():
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key.startswith("sk-or-..."):
        print(
            "ERROR: OPENROUTER_API_KEY is not set.\n"
            "Copy .env.example to .env and add your key "
            "(get one at https://openrouter.ai/keys).",
            file=sys.stderr,
        )
        return 1

    try:
        phase_1_list_models()
        model = phase_2_selected_model()
        phase_3_provider_pricing(model)

        client = orc.make_client(api_key)
        tracker = UsageTracker()
        phase_4_sample_calls(client, model, tracker)
        phase_5_summary(tracker)
    except OpenRouterError as exc:
        print(f"\nERROR talking to OpenRouter: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
