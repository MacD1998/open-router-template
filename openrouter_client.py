"""Thin wrapper around the OpenRouter API.

Two kinds of calls live here:

* ``list_models`` / ``list_endpoints`` hit OpenRouter's *catalog* REST
  endpoints. These are plain JSON GETs (no auth required), so we use the
  standard library ``urllib`` and avoid pulling in an HTTP dependency.

* ``chat_completion`` uses the official OpenAI SDK pointed at OpenRouter's
  ``base_url`` — this is the whole point of OpenRouter's OpenAI-compatible
  API: existing OpenAI code works unchanged.

Every call is wrapped so callers get an ``OpenRouterError`` with a readable
message instead of a raw traceback.
"""

import json
import urllib.error
import urllib.request

from openai import OpenAI

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(Exception):
    """Raised for any failure talking to OpenRouter (network, HTTP, auth)."""


# --------------------------------------------------------------------------
# Catalog endpoints (public, no key needed)
# --------------------------------------------------------------------------
def _get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise OpenRouterError(
            f"HTTP {exc.code} ({exc.reason}) from {url}"
        ) from exc
    except urllib.error.URLError as exc:
        raise OpenRouterError(
            f"Network error contacting {url}: {exc.reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OpenRouterError(f"Invalid JSON from {url}: {exc}") from exc


def list_models():
    """Return the list of available models (each a dict with id/name/pricing)."""
    return _get_json(f"{BASE_URL}/models").get("data", [])


def list_endpoints(model):
    """Return the per-provider endpoint info for one model.

    ``model`` is the full "author/slug" id, e.g. "meta-llama/llama-3.1-8b-instruct".
    The returned dict has an ``endpoints`` list, one entry per provider.
    """
    return _get_json(f"{BASE_URL}/models/{model}/endpoints").get("data", {})


# --------------------------------------------------------------------------
# Chat completions (OpenAI SDK -> OpenRouter)
# --------------------------------------------------------------------------
def make_client(api_key):
    """Build an OpenAI SDK client pointed at OpenRouter."""
    return OpenAI(base_url=BASE_URL, api_key=api_key)


def chat_completion(client, model, prompt):
    """Run one chat completion and return the RAW response as a dict.

    Two ``extra_body`` keys matter here:

    * ``usage.include`` asks OpenRouter to attach real billing info (cost,
      cached tokens, serving provider) to the response. Those fields are NOT
      part of the standard OpenAI usage object, so we return ``model_dump()``
      (the full raw JSON) and let the caller dig them out.
    * ``provider.sort = "price"`` tells OpenRouter to route to the cheapest
      provider first, so the served provider matches the cheapest-first
      pricing table printed in Phase 3. (Use "throughput" or "latency"
      instead to optimize for speed.)
    """
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            extra_body={
                "usage": {"include": True},
                "provider": {"sort": "price"},
            },
        )
    except Exception as exc:  # SDK raises many subclasses; normalize them all
        raise OpenRouterError(f"Chat completion failed: {exc}") from exc
    return resp.model_dump()
