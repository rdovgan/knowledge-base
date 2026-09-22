#!/usr/bin/env python3
"""
Standalone test for rag_pipeline.reranker — validates the Jev integration
in isolation, without touching dashboard.py.

Usage:
    python3 scripts/test_reranker.py --mock     # no API key needed, fakes the HTTP call
    python3 scripts/test_reranker.py            # hits the real Jev API (needs TYPESAFE_API_KEY)
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _load_env():
    """Same convention as dashboard.py's load_env() — read .env into os.environ."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

SAMPLE_QUERY = "How does reservation creation validate duplicate bookings?"

SAMPLE_RESULTS = [
    {
        "text": (
            "ReservationService.createReservation() checks the pending_transactions "
            "table for an existing entry with the same channel_id and guest email "
            "before inserting a new reservation, to prevent duplicate bookings from "
            "retried requests."
        ),
        "metadata": {"source_file": "ReservationService.java", "domain": "reservations", "module": "core"},
        "distance": 0.12,
    },
    {
        "text": (
            "LoggingAspect intercepts all @RestController methods and writes request/"
            "response payloads to the audit log table for compliance purposes."
        ),
        "metadata": {"source_file": "LoggingAspect.java", "domain": "logging", "module": "infra"},
        "distance": 0.31,
    },
    {
        "text": (
            "DuplicateDetectionUtil.isDuplicate() hashes the (channelId, guestEmail, "
            "checkIn, checkOut) tuple and looks it up in a short-lived Redis cache "
            "with a 5 minute TTL to catch rapid double-submits."
        ),
        "metadata": {"source_file": "DuplicateDetectionUtil.java", "domain": "reservations", "module": "core"},
        "distance": 0.18,
    },
    {
        "text": (
            "CurrencyConverter.convert() calls the exchange-rate provider and caches "
            "rates for 1 hour."
        ),
        "metadata": {"source_file": "CurrencyConverter.java", "domain": "billing", "module": "core"},
        "distance": 0.40,
    },
]


def _mock_response(query, results):
    """Fake a Jev /v1/systemone response: score chunks that mention 'duplicate' or
    'validat' higher, everything else lower — just enough to prove the plumbing."""
    answers = {}
    for i, r in enumerate(results):
        text = r["text"].lower()
        if "duplicate" in text or "pending_transactions" in text:
            score, conf = 2.8, 0.91
        elif "validat" in text:
            score, conf = 1.9, 0.7
        else:
            score, conf = 0.2, 0.85
        answers[f"relevance_{i}"] = {"type": "score", "score": score, "confidence": conf}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"model": "jev-mock", "answers": answers, "usage": {"input_tokens": 123, "output_tokens": 40}}

    return _Resp()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="fake the HTTP call, no API key needed")
    parser.add_argument("--min-score", type=float, default=1.0)
    args = parser.parse_args()

    _load_env()
    from rag_pipeline import reranker

    print(f"Query: {SAMPLE_QUERY}\n")
    print("Before rerank (vector-distance order):")
    for r in SAMPLE_RESULTS:
        print(f"  distance={r['distance']:.2f}  {r['metadata']['source_file']}")

    if args.mock:
        os.environ.setdefault("TYPESAFE_API_KEY", "mock-key")
        with patch("rag_pipeline.reranker.requests.post", lambda *a, **kw: _mock_response(SAMPLE_QUERY, SAMPLE_RESULTS)):
            ranked = reranker.rerank_chunks(SAMPLE_QUERY, SAMPLE_RESULTS, min_score=args.min_score)
    else:
        if not os.environ.get("TYPESAFE_API_KEY"):
            print("\nNo TYPESAFE_API_KEY set and --mock not passed — nothing to call. "
                  "Set the key in .env or pass --mock to test the plumbing offline.")
            return
        ranked = reranker.rerank_chunks(SAMPLE_QUERY, SAMPLE_RESULTS, min_score=args.min_score)

    print("\nAfter rerank:")
    for r in ranked:
        rel = r.get("jev_relevance")
        conf = r.get("jev_confidence")
        tag = f"relevance={rel:.2f} confidence={conf:.2f}" if rel is not None else "unscored (fallback)"
        print(f"  {tag}  {r['metadata']['source_file']}")


if __name__ == "__main__":
    main()
