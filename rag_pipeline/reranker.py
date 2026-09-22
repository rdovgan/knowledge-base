"""
Jev (TypeSafe AI) chunk reranker — prototype.

Scores retrieved RAG chunks for relevance to the query using TypeSafe's Jev
"System One" model (typed score, not generated text) instead of spending the
main answer LLM on judging relevance. Not wired into dashboard.py yet — this
is an isolated prototype to validate the approach against the real API first.

Docs: https://docs.typesafe.ai/models
"""

import os
import logging
from typing import Dict, List, Optional

import requests

log = logging.getLogger(__name__)

JEV_API_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")

# Documented ceiling is 32k tokens for state + questions combined; stay under it.
JEV_STATE_TOKEN_BUDGET = 28000

RELEVANCE_LEVELS = ["irrelevant", "tangential", "relevant", "highly_relevant"]
DEFAULT_MIN_SCORE = 1.0  # drop anything at/below "tangential"


def _estimate_tokens(text: str) -> int:
    """Rough ~4 chars/token heuristic — good enough for a budget check, not billing."""
    return max(1, len(text) // 4)


def _fit_to_budget(results: List[Dict], token_budget: int) -> List[Dict]:
    """Keep as many leading results as fit under the state token budget."""
    fitted = []
    used = 0
    for r in results:
        cost = _estimate_tokens(r.get("text", ""))
        if used + cost > token_budget and fitted:
            break
        fitted.append(r)
        used += cost
    return fitted


def _build_request(query: str, batch: List[Dict]) -> dict:
    state = [
        {
            "index": i,
            "source_file": r.get("metadata", {}).get("source_file", "?"),
            "text": r.get("text", ""),
        }
        for i, r in enumerate(batch)
    ]
    questions = {
        f"relevance_{i}": {
            "type": "score",
            "instructions": (
                f"How relevant is the state item at index {i} to answering "
                f"this question: '{query}'?"
            ),
            "criteria": RELEVANCE_LEVELS,
        }
        for i in range(len(batch))
    }
    return {"model": JEV_MODEL, "state": state, "questions": questions}


def rerank_chunks(
    query: str,
    results: List[Dict],
    api_key: Optional[str] = None,
    min_score: float = DEFAULT_MIN_SCORE,
    timeout: float = 5.0,
) -> List[Dict]:
    """
    Score `results` (dicts with at least a `text` key, as returned by
    rag_pipeline.indexer.query_rag) for relevance to `query` via Jev.

    Returns results sorted by relevance, with anything scored below
    `min_score` dropped. On any failure — missing key, network error, bad
    response — returns `results` unchanged. Reranking is a quality
    improvement, never a hard dependency for the RAG answer path.
    """
    api_key = api_key or os.environ.get("TYPESAFE_API_KEY", "")
    if not api_key or not results:
        return results

    batch = _fit_to_budget(results, JEV_STATE_TOKEN_BUDGET)
    leftover = results[len(batch):]  # didn't fit in the state budget

    payload = _build_request(query, batch)

    try:
        resp = requests.post(
            JEV_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        if resp.status_code in (401, 403):
            log.warning("Jev rerank skipped: TYPESAFE_API_KEY rejected (invalid/expired), "
                        "falling back to unranked results")
            return results
        resp.raise_for_status()
        answers = resp.json().get("answers", {})
    except Exception as e:
        log.warning(f"Jev rerank unavailable, falling back to unranked results: {e}")
        return results

    scored = []
    for i, r in enumerate(batch):
        ans = answers.get(f"relevance_{i}") or {}
        score = ans.get("score")
        scored.append({**r, "jev_relevance": score, "jev_confidence": ans.get("confidence")})

    # A 200 with no usable scores (empty/malformed `answers`) is a response we
    # can't trust, not a legitimate "nothing is relevant" verdict — fall back.
    if not any(r["jev_relevance"] is not None for r in scored):
        log.warning("Jev rerank returned no usable scores, falling back to unranked results")
        return results

    kept = [r for r in scored if r["jev_relevance"] is not None and r["jev_relevance"] >= min_score]
    kept.sort(key=lambda r: r["jev_relevance"], reverse=True)

    # never silently drop chunks that didn't fit the budget — keep them, unscored,
    # appended in their original order
    return kept + leftover
