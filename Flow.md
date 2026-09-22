# RAG Pipeline — Cross-Domain Flow Documents

## Root Cause

The RAG pipeline had **712 domain pages**, each documenting a single Java package in isolation. A booking flow typically spans **8–15 domains** (REST endpoint → service → calculation → payment → confirmation → notification).

When the LLM retrieved fragments from individual domains, no single chunk explained the complete flow — resulting in responses like *"We do not currently have complete documentation for this process."*

---

## Solution: Cross-Domain Flow Documents

A new pipeline step was added — `rag_pipeline/flow_generator.py` — that generates end-to-end flow documents spanning multiple domains.

| Flow Document | Domains Spanned | Answers |
|---|---|---|
| `booking_creation.md` | 15+ | "How is a booking created?" |
| `booking_cancellation.md` | 8 | "How does cancellation work?" |
| `booking_modification.md` | 8 | "How are bookings modified?" |
| `payment_processing.md` | 9 | "How does payment work?" |
| `pricing_and_promotions.md` | 7 | "How is pricing calculated?" |
| `channel_integration_bookingcom.md` | 12 | "Booking.com integration?" |
| `channel_integration_homeaway.md` | 7 | "HomeAway/VRBO integration?" |
| `supplier_api_reservation.md` | 11 | "Supplier API reservation?" |
| `manual_reservation.md` | 7 | "Manual reservations?" |
| `inquiry_tracking.md` | 8 | "Inquiry → booking?" |

---

## New Commands

```bash
# Generate all flow docs
python3 run_rag.py flows

# Generate only the first 3 flows
python3 run_rag.py flows --limit 3

# Full pipeline run (now includes flows step)
python3 run_rag.py all
```

---

## What You Need to Do

**1. Wait for indexing to complete** (~50 min). Check status with:

```bash
python3 run_rag.py status
```

**2. Once indexed**, queries like *"how to finalize a booking"* will match the flow pages and return complete answers.

---

## Adding More Flows

Add new entries to the `FLOWS` dict in `rag_pipeline/flow_generator.py`. Define:

- `title`
- `description`
- `domain patterns`
- `questions it should answer`

Then regenerate:

```bash
python3 run_rag.py flows --force
```
