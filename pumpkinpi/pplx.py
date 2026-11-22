"""Thin wrappers for the three Perplexity APIs PumpkinPi uses.

- Agent API   POST /v1/agent      turns the guest's prompt into a design plan (with web search)
              https://docs.perplexity.ai/docs/agent-api/quickstart
- Search API  POST /search        finds label / allergen pages for each ingredient
              https://docs.perplexity.ai/docs/search/quickstart
- Decisions   POST /v1/decisions  calibrated yes/no probabilities (allergens, pie readiness)
              https://docs.perplexity.ai/docs/decisions/decisions

The key comes from PERPLEXITY_API_KEY. Never hard-code it or show it on camera.
"""
from __future__ import annotations

import os
import time

import httpx

BASE = "https://api.perplexity.ai"
AGENT_URL = f"{BASE}/v1/agent"
SEARCH_URL = f"{BASE}/search"
DECISIONS_URL = f"{BASE}/v1/decisions"

AGENT_MODEL = os.environ.get("PUMPKINPI_AGENT_MODEL", "openai/gpt-5.6-sol")
DECIDER_MODEL = os.environ.get("PUMPKINPI_DECIDER_MODEL", "pplx-decider-latest")
RETRY_STATUS = (429, 500, 502, 503, 504)


def make_client() -> httpx.Client:
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        raise SystemExit("Set PERPLEXITY_API_KEY first (never hard-code it).")
    return httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=90.0)


def post(client: httpx.Client, url: str, body: dict, retries: int = 3) -> dict:
    for attempt in range(retries + 1):
        r = client.post(url, json=body)
        if r.status_code == 200:
            return r.json()
        if r.status_code in RETRY_STATUS and attempt < retries:
            time.sleep(min(2**attempt, 30))
            continue
        raise RuntimeError(f"{url} -> {r.status_code}: {r.text[:300]}")
    raise RuntimeError("unreachable")


def agent(client: httpx.Client, *, instructions: str, input: str, schema: dict, name: str,
          domains: list[str] | None = None) -> tuple[str, list[dict]]:
    """One Agent API run with web search and JSON output. Returns (json_text, search_results)."""
    tool: dict = {"type": "web_search"}
    if domains:
        tool["filters"] = {"search_domain_filter": domains}
    data = post(client, AGENT_URL, {
        "model": AGENT_MODEL,
        "instructions": instructions,
        "input": input,
        "tools": [tool],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
    })
    text, results = "", []
    for item in data.get("output", []):
        if item.get("type") == "message":
            text += "".join(c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text")
        elif item.get("type") == "search_results":
            results += item.get("results", [])
    return text, results


def search(client: httpx.Client, query: str | list[str], max_results: int = 5) -> list[dict]:
    """Search API: ranked results with title, url, snippet, date."""
    return post(client, SEARCH_URL, {"query": query, "max_results": max_results}).get("results", [])


def decide(client: httpx.Client, state, questions: dict, web_grounding: bool = False) -> dict:
    body = {"model": DECIDER_MODEL, "state": state, "questions": questions}
    if web_grounding:
        body["mode"] = "web_grounding"
    return post(client, DECISIONS_URL, body)
