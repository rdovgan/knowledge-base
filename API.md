# Knowledge Base API

Base URL: `http://172.18.1.132:8090`

---

## POST /api/query — Semantic Search

Returns raw matching chunks with distance scores. Useful when you need source documents without an LLM summary.

```bash
curl -X POST http://172.18.1.132:8090/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "ReservationNightlyRateRequest",
    "top_k": 5,
    "filter": {"module": "mbp"}
  }'
```

**GET shorthand:**

```bash
curl 'http://172.18.1.132:8090/api/query?q=InquiryReservation&top_k=3&format=md'
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Search query text |
| `top_k` | int | Number of results. Default: `5` |
| `filter` | object | Metadata filter, e.g. `{"module": "mbp"}`. Optional |
| `format` | string | `md` — template Markdown, `human` — LLM-synthesized Markdown. Optional |

### Response

```json
{
  "query": "...",
  "total_results": 5,
  "results": [...]
}
```

Returns Markdown (`text/markdown`) when `format=md` or `format=human`.

---

## POST /api/ask — RAG Question Answering

Retrieves relevant chunks and passes them to an LLM to generate a detailed answer with class/method references.

```bash
curl -X POST http://172.18.1.132:8090/api/ask \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "How does inquiry reservation work?",
    "top_k": 10
  }'
```

**GET shorthand:**

```bash
curl 'http://172.18.1.132:8090/api/ask?q=how+does+booking+work&top_k=8&format=md'
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Your question in plain English |
| `top_k` | int | Number of chunks to retrieve. Default: `10` |
| `filter` | object | Metadata filter, e.g. `{"module": "mbp"}`. Optional |
| `model` | string | Override the default LLM model name. Optional |
| `format` | string | `md` — template Markdown, `human` — LLM-rewritten Markdown. Optional |

### Response

```json
{
  "query": "...",
  "answer": "...",
  "model": "glm-5-turbo",
  "total_sources": 10,
  "sources": [...]
}
```

Returns Markdown (`text/markdown`) when `format=md` or `format=human`.

---

## format parameter

| Value | Behavior |
|-------|----------|
| *(omitted)* | JSON response |
| `md` | Server-side template render — fast, no extra LLM call |
| `human` | Additional LLM call rewrites the response as prose Markdown |
