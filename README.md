# OpenRouter usage & pricing — CLI template

A small, self-contained reference showing how to use the
[OpenRouter](https://openrouter.ai) API from Python with the **plain OpenAI
SDK** — including the two things that are easy to get wrong: reading per-model /
per-provider **pricing**, and getting **real token + cost accounting** back from
each call.

It is intentionally dependency-light (`openai`, `python-dotenv`) and decoupled
from any agent framework. Copy the folder, point it at your key, run it.

## What it demonstrates

Running `python main.py` walks through five phases:

1. **Model listing** — `GET /models`, printed as a truncated table
   (id, name, input $/M, output $/M).
2. **Selected model** — resolved from `OPENROUTER_MODEL`.
3. **Per-model provider pricing** — `GET /models/{author}/{slug}/endpoints`,
   a truncated table of providers sorted cheapest-first
   (provider, quantization, input/output/cache-read/cache-write $/M).
4. **Sample calls** — 3 hardcoded prompts run against the model with live
   `[1/3] … done` progress, each requesting real usage accounting and routed
   to the **cheapest provider** (`provider: {"sort": "price"}`), so the served
   provider matches the top of the Phase 3 table.
5. **Usage summary** — total input/output/cache tokens, **real billed cost**,
   and which provider(s) actually served the calls.

## Setup

```bash
cd template
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt

cp .env.example .env
# then edit .env and paste your key
```

You need an OpenRouter API key — create one at
<https://openrouter.ai/keys> (it looks like `sk-or-v1-...`).

`.env` must contain (both are required; the model has a sensible default):

```
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct
```

## Run

```bash
python main.py
```

No arguments, no web UI — it prints everything to the terminal. The catalog
phases (1–3) work even before you spend anything; phases 4–5 make 3 cheap real
calls (fractions of a cent on the default model).

## Example output

A full run with the default model (`meta-llama/llama-3.1-8b-instruct`).
Prices and the served provider are live values, so yours will differ slightly:

```text
=== Available models (showing 10) ===
id                                       name                            input $/M         output $/M
---------------------------------------  ------------------------------  ----------------  ----------------
google/gemini-3.1-flash-image            Google: Nano Banana 2 (Gemini…  $0.5000           $3.0000
google/gemini-3-pro-image                Google: Nano Banana Pro (Gemi…  $2.0000           $12.0000
cohere/north-mini-code:free              Cohere: North Mini Code (free)  $0.0000           $0.0000
z-ai/glm-5.2                             Z.ai: GLM 5.2                   $0.9800           $3.0800
openrouter/fusion                        OpenRouter: Fusion              $-1,000,000.0000  $-1,000,000.0000
moonshotai/kimi-k2.7-code                MoonshotAI: Kimi K2.7 Code      $0.6800           $3.4100
~anthropic/claude-fable-latest           Anthropic: Claude Fable Latest  $10.0000          $50.0000
anthropic/claude-fable-5                 Anthropic: Claude Fable 5       $10.0000          $50.0000
nex-agi/nex-n2-pro                       Nex AGI: Nex-N2-Pro             $0.2500           $1.0000
nvidia/nemotron-3.5-content-safety:free  NVIDIA: Nemotron 3.5 Content …  $0.0000           $0.0000

=== Selected model: meta-llama/llama-3.1-8b-instruct ===

=== Providers for meta-llama/llama-3.1-8b-instruct (showing 10) ===
provider    quant    input $/M  output $/M  cache_read $/M  cache_write $/M
----------  -------  ---------  ----------  --------------  ---------------
DeepInfra   fp8      $0.0200    $0.0300     -               -
DeepInfra   bf16     $0.0200    $0.0500     -               -
Novita      fp8      $0.0200    $0.0500     -               -
Groq        unknown  $0.0500    $0.0800     $0.0250         -
WandB       bf16     $0.2200    $0.2200     $0.2200         -
Cloudflare  fp8      $0.1520    $0.2870     -               -

=== Running 3 sample calls ===
[1/3] LLM request... done  (provider=DeepInfra, cost=$0.000001)
[2/3] LLM request... done  (provider=DeepInfra, cost=$0.000000)
[3/3] LLM request... done  (provider=DeepInfra, cost=$0.000001)

=== Usage summary (real billed values) ===
metric                    value
------------------------  ------------
Total input tokens        46
Total output tokens       43
Total cache read tokens   0
Total cache write tokens  0
Total cost (USD)          $0.000002
Providers                 DeepInfra x3

Note: 'Total cost' is the REAL billed amount summed from each response's usage.cost field, not an estimate.
```

## How each piece is done

Each feature maps to one function and one underlying OpenRouter call:

| Feature | Function (in this repo) | OpenRouter call |
|---------|-------------------------|-----------------|
| List available models + their prices | `openrouter_client.list_models()` → formatted by `pricing.model_rows()` | `GET /api/v1/models` |
| Resolve the selected model | `main.phase_2_selected_model()` (reads `OPENROUTER_MODEL`) | — (env var) |
| Per-provider pricing, cheapest-first | `openrouter_client.list_endpoints(model)` → sorted/formatted by `pricing.endpoint_rows()` | `GET /api/v1/models/{author}/{slug}/endpoints` |
| Run a chat call with cost accounting | `openrouter_client.chat_completion()` | `POST /api/v1/chat/completions` with `extra_body={"usage": {"include": True}}` |
| Route the call to the cheapest provider | `openrouter_client.chat_completion()` | same call, `extra_body={"provider": {"sort": "price"}}` |
| Extract real cost / cached tokens / provider | `usage_tracker.extract_usage(raw)` (reads `response.model_dump()`) | fields from the raw response: `usage.cost`, `usage.prompt_tokens_details.cached_tokens`, top-level `provider` |
| Accumulate totals across calls + summary | `usage_tracker.UsageTracker.add()` / `.print_summary()` | — (local aggregation) |
| $/token → $/million formatting | `pricing.per_million()` / `pricing.fmt_price()` | — (local formatting) |

## The one non-obvious lesson: `usage.include` + raw response

The OpenAI SDK's parsed `usage` object only gives you `prompt_tokens` /
`completion_tokens` / `total_tokens`. The numbers you actually care about with
OpenRouter — the **real billed `cost`**, **cached token counts**, and **which
provider served the request** — are OpenRouter-specific and are **not** in that
standard object.

Two things make them available:

1. **Ask for them.** Pass `extra_body={"usage": {"include": True}}` on the
   chat completion. Without this, OpenRouter does not attach cost details.
2. **Read the raw response.** Those fields live in the raw JSON, so we call
   `response.model_dump()` and dig out `usage.cost`,
   `usage.prompt_tokens_details.cached_tokens`, and the top-level `provider`.
   See `usage_tracker.extract_usage()` — every field is read defensively
   (`.get(...) or 0`) because not every provider reports every field.

This is why the summary can say "real billed values, not estimates": the cost
comes straight from `usage.cost`, computed by OpenRouter, not multiplied out of
a price table on our side.

## Provider routing (cheapest-first)

A single model is often served by several providers at different prices (that's
exactly what the Phase 3 table shows). By default OpenRouter load-balances
across them, so you can't be sure which one — or which price — you'll get.

The sample calls pin this down by passing a provider preference:

```python
extra_body={
    "usage": {"include": True},
    "provider": {"sort": "price"},   # route to the lowest-cost provider first
}
```

With `sort: "price"`, the provider that actually serves the call (shown in
Phase 4 / the Phase 5 summary) lines up with the top of the cheapest-first
Phase 3 table. Swap the value to `"throughput"` (fastest) or `"latency"`
(lowest latency) to optimize for speed instead. See
`openrouter_client.chat_completion()`.

## Swapping the model

Change `OPENROUTER_MODEL` in `.env` to any slug from the catalog
(`author/slug`). Browse them at <https://openrouter.ai/models>, or just read the
Phase 1 table this tool prints. Examples:

```
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1
OPENROUTER_MODEL=mistralai/mistral-nemo
```

Nothing else needs to change — Phase 3 will re-fetch that model's providers and
Phases 4–5 will bill against it.

## Files

| File | Role |
|------|------|
| `main.py` | Entry point; orchestrates the five phases. |
| `openrouter_client.py` | Thin wrapper: `list_models`, `list_endpoints`, `chat_completion` (with usage accounting). |
| `pricing.py` | Price conversion ($/token → $/M) and table formatting. |
| `usage_tracker.py` | Extracts OpenRouter usage fields and accumulates totals. |
| `.env.example` | Required env vars (copy to `.env`). |
| `requirements.txt` | `openai`, `python-dotenv`. |
