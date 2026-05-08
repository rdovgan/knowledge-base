"""
Cross-Domain Flow Generator — creates end-to-end flow documents.

Problem: Each domain page describes one package in isolation.
         A booking flow spans 8-15 domains. No single chunk explains the full flow,
         so LLM answers say "we do not currently have complete documentation."

Solution: Generate dedicated flow pages that:
  1. Identify key business flows from domain names & class structure
  2. Collect all relevant domain summaries into one context window
  3. Use LLM to write an end-to-end flow document
  4. Index these flow pages alongside domain pages

Flow pages go into: rag/_flows/<flow_name>.md
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

log = logging.getLogger(__name__)


# ── Flow definitions ────────────────────────────────────────────
# Each flow specifies which domains it spans and what questions it answers.

FLOWS = {
    "booking_creation": {
        "title": "Booking Creation Flow",
        "description": "End-to-end flow from channel inquiry/API request through reservation creation, "
                       "price calculation, payment processing, and confirmation.",
        "keywords": ["reserv", "book", "inquir", "requesttobook", "availability"],
        "domain_patterns": [
            # REST entry points
            "rest_reservation", "rest_mybookingpal", "rest_bookt",
            "bookingrest_bookingcom", "bookingrest_supplierAPI",
            "homeaway_vrbo_rest_vrbooking", "rest_bookingdom",
            "rest_bookingsync", "friendlyrentals_booking",
            # Channel-specific REST
            "bookingcom", "bookingcore_rest", "bookingcore_event",
            # Supplier API entry
            "supplierAPI_reservation", "supplierAPI_requestToBook",
            # Core reservation logic
            "service_reservation", "reservation_calculation",
            "reservation_payment", "reservation_dto",
            "reservation_partner", "shared_reservation",
            "utils_reservation", "reservation_clarity",
            # Builder / factory
            "rest_reservation",
            # Confirmation
            "reservation_importCalendar",
        ],
        "questions": [
            "How is a booking created step by step?",
            "What happens when a reservation request comes from Booking.com?",
            "How does the booking flow from inquiry to confirmed reservation?",
            "What is the complete reservation creation process?",
            "How to finalize a booking?",
        ],
    },

    "booking_cancellation": {
        "title": "Booking Cancellation Flow",
        "description": "End-to-end flow for cancelling a reservation: cancel request → "
                       "cancellation policy check → refund calculation → state change → notifications.",
        "keywords": ["cancel", "cancellation"],
        "domain_patterns": [
            "reservation_cancel", "shared_cancellation", "supplierAPI_cancellationPolicy",
            "itrip_cancelBooking", "service_reservation",
            "reservation_calculation", "reservation_payment",
            "reservation_clarity", "supplierAPI_reservation",
        ],
        "questions": [
            "How does reservation cancellation work?",
            "What happens when a booking is cancelled?",
            "How are refunds calculated for cancellations?",
            "What is the cancellation policy flow?",
        ],
    },

    "booking_modification": {
        "title": "Booking Modification Flow",
        "description": "How existing reservations are modified: date changes, guest changes, "
                       "price recalculation, payment adjustment, and PMS sync.",
        "keywords": ["modif", "change", "amend"],
        "domain_patterns": [
            "reservation_modification", "service_reservation",
            "reservation_calculation", "reservation_payment",
            "reservation_clarity", "reservation_dto",
            "shared_reservation", "supplierAPI_reservation",
        ],
        "questions": [
            "How does reservation modification work?",
            "What happens when dates are changed on a booking?",
            "How is price recalculated on modification?",
        ],
    },

    "payment_processing": {
        "title": "Payment Processing Flow",
        "description": "End-to-end payment flow: payment method selection → gateway interaction → "
                       "commission calculation → payout → transaction recording.",
        "keywords": ["payment", "pay", "stripe", "gateway", "transaction", "commission", "payout"],
        "domain_patterns": [
            "reservation_payment", "payment_stripe", "rent_paymentrequest",
            "rest_reservation", "service_reservation",
            "reservation_clarity", "reservation_calculation",
            "shared_reservation", "supplierAPI_reservation",
        ],
        "questions": [
            "How does payment processing work?",
            "How are commissions calculated?",
            "How does Stripe integration work?",
            "What is the payment flow for a booking?",
        ],
    },

    "pricing_and_promotions": {
        "title": "Pricing and Promotions Flow",
        "description": "How prices are calculated: base rate → promotions → fees → taxes → "
                       "channel-specific markups → final price.",
        "keywords": ["pric", "promot", "yield", "fee", "tax", "rate", "charge"],
        "domain_patterns": [
            "reservation_calculation", "service_reservation",
            "reservation_clarity", "dto_chargefee",
            "reservation_dto", "shared_reservation",
            "supplierAPI_revenueManagment",
        ],
        "questions": [
            "How is pricing calculated for a reservation?",
            "How do promotions work?",
            "How are fees and taxes calculated?",
            "What is the pricing strategy?",
        ],
    },

    "channel_integration_bookingcom": {
        "title": "Booking.com Integration Flow",
        "description": "How MyBookingPal integrates with Booking.com: content sync → "
                       "availability push → reservation pull → confirmation push → payment reconciliation.",
        "keywords": ["bookingcom", "booking.com"],
        "domain_patterns": [
            "bookingrest_bookingcom", "bookingcom", "bookingcore_rest",
            "bookingcore_event", "booking_content", "booking_launcher",
            "booking_tasklet", "bookingrest_supplierAPI",
            "service_reservation", "reservation_calculation",
            "reservation_payment", "rest_reservation",
            "supplierAPI_reservation",
        ],
        "questions": [
            "How does Booking.com integration work?",
            "How are reservations received from Booking.com?",
            "How is content synced with Booking.com?",
        ],
    },

    "channel_integration_homeaway": {
        "title": "HomeAway/VRBO Integration Flow",
        "description": "How MyBookingPal integrates with HomeAway/VRBO: listing sync → "
                       "inquiry handling → booking → confirmation → payment.",
        "keywords": ["homeaway", "vrbo"],
        "domain_patterns": [
            "homeaway_vrbo_rest_vrbooking",
            "service_reservation", "reservation_calculation",
            "reservation_payment", "rest_reservation",
            "supplierAPI_reservation", "shared_reservation",
        ],
        "questions": [
            "How does HomeAway/VRBO integration work?",
            "How are bookings received from VRBO?",
        ],
    },

    "supplier_api_reservation": {
        "title": "Supplier API Reservation Flow",
        "description": "How property managers create and manage reservations via the Supplier API: "
                       "availability check → create reservation → payment → confirmation → modification → cancellation.",
        "keywords": ["supplier", "property manager", "pms"],
        "domain_patterns": [
            "supplierAPI_reservation", "supplierAPI_requestToBook",
            "supplierAPI_listing", "supplierAPI_authc",
            "service_reservation", "reservation_calculation",
            "reservation_payment", "reservation_clarity",
            "reservation_dto", "shared_reservation",
            "rest_reservation",
        ],
        "questions": [
            "How does the Supplier API work for reservations?",
            "How do property managers create bookings via API?",
            "What is the Supplier API reservation flow?",
        ],
    },

    "manual_reservation": {
        "title": "Manual Reservation Flow",
        "description": "How manual/offline reservations are created: PM creates reservation → "
                       "price override → payment recording → confirmation → PMS sync.",
        "keywords": ["manual", "offline", "direct"],
        "domain_patterns": [
            "manual_reservation", "service_reservation",
            "reservation_calculation", "reservation_payment",
            "reservation_dto", "shared_reservation",
            "reservation_partner",
        ],
        "questions": [
            "How are manual reservations created?",
            "How do offline bookings work?",
            "How do direct bookings work?",
        ],
    },

    "inquiry_tracking": {
        "title": "Inquiry Tracking Flow",
        "description": "How booking inquiries are received, tracked, and converted to reservations: "
                       "inquiry receipt → availability check → quote → conversion to booking.",
        "keywords": ["inquir", "quote", "availability"],
        "domain_patterns": [
            "supplierAPI_requestToBook", "service_reservation",
            "reservation_calculation", "rest_reservation",
            "supplierAPI_reservation", "shared_reservation",
            "shared_searchReservation", "reservation_dto",
        ],
        "questions": [
            "How are inquiries tracked?",
            "How does an inquiry become a booking?",
            "How does the request-to-book flow work?",
        ],
    },
}


def _load_domain_page(output_dir: str, domain_name: str, module: str) -> Optional[str]:
    """Load the content of a domain page."""
    safe_name = domain_name.replace('/', '_').replace(' ', '_')
    path = os.path.join(output_dir, module, '_domains', f"{safe_name}.md")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    # Try all modules
    for mod_dir in os.listdir(output_dir):
        mod_path = os.path.join(output_dir, mod_dir, '_domains', f"{safe_name}.md")
        if os.path.exists(mod_path):
            with open(mod_path, 'r', encoding='utf-8') as f:
                return f.read()
    return None


def _find_domain_in_json(domains: List[dict], name: str) -> Optional[dict]:
    """Find a domain by name in the domains list."""
    for d in domains:
        if d.get('name') == name:
            return d
    return None


def _collect_flow_context(flow_def: dict, domains: List[dict], output_dir: str) -> str:
    """Collect relevant domain page content for a flow."""
    context_parts = []
    seen_domains = set()

    for pattern in flow_def["domain_patterns"]:
        if pattern in seen_domains:
            continue
        seen_domains.add(pattern)

        # Find the domain
        dom = _find_domain_in_json(domains, pattern)
        if not dom:
            continue

        module = dom.get('module', '')
        content = _load_domain_page(output_dir, pattern, module)
        if content:
            # Strip frontmatter
            if content.startswith('---'):
                end = content.find('---', 3)
                if end > 0:
                    content = content[end + 3:].strip()

            # Truncate to ~3000 chars per domain to fit context window
            if len(content) > 3000:
                # Keep the enriched section (Architecture & Business Logic)
                marker = "## Architecture & Business Logic"
                idx = content.find(marker)
                if idx >= 0:
                    enriched = content[idx:]
                    if len(enriched) > 3000:
                        enriched = enriched[:3000] + "\n... (truncated)"
                    context_parts.append(f"### Domain: {pattern}\n\n{enriched}")
                else:
                    context_parts.append(f"### Domain: {pattern}\n\n{content[:3000]}... (truncated)")
            else:
                context_parts.append(f"### Domain: {pattern}\n\n{content}")

    return '\n\n---\n\n'.join(context_parts)


def _build_flow_prompt(flow_def: dict, context: str) -> str:
    """Build the LLM prompt for flow generation."""
    questions_str = '\n'.join(f'  - "{q}"' for q in flow_def["questions"])

    prompt = f"""You are documenting end-to-end business flows for a Java/Spring Boot property booking platform (MyBookingPal).

## Task
Write a comprehensive, step-by-step flow document titled "{flow_def['title']}".

{flow_def['description']}

## Source Context
The following domain-level documentation has been extracted from the codebase:

{context}

## Requirements
1. **Step-by-step flow** — Numbered steps from trigger to completion
2. **Class references** — Reference actual class names (e.g., `ReservationService`, `CalculatePriceService`)
3. **Sequence diagram** — Include a Mermaid sequenceDiagram showing the key participants
4. **Decision points** — Where does the flow branch? What conditions cause different paths?
5. **Error handling** — What happens when things go wrong?
6. **Configuration** — Which settings affect this flow?
7. **Channel variations** — How does the flow differ across channels (Booking.com, HomeAway, Airbnb, etc.)?

## Questions This Must Answer
{questions_str}

## Rules
- Use ONLY class/method/field names from the context above. Never invent names.
- Be specific about the business logic — this is for developers onboarding to the codebase.
- Write in clear, structured Markdown.
- 800-2500 words depending on complexity.
"""
    return prompt


def generate_flows(
    domains: List[dict],
    output_dir: str,
    api_key: str,
    base_url: str = "https://api.z.ai/api/coding/paas/v4",
    model: str = "glm-5-turbo",
    fallback_model: str = "glm-4.7",
    delay: float = 2.0,
    limit: int = 0,
) -> dict:
    """
    Generate cross-domain flow documents using LLM.

    Args:
        domains: List of domain dicts from domains.json
        output_dir: Wiki output directory (rag/)
        api_key: LLM API key
        base_url: LLM API base URL
        model: Primary LLM model
        fallback_model: Fallback LLM model
        delay: Seconds between API calls
        limit: Max flows to generate (0 = all)
    """
    from openai import OpenAI
    import time

    client = OpenAI(api_key=api_key, base_url=base_url)

    flows_dir = os.path.join(output_dir, "_flows")
    os.makedirs(flows_dir, exist_ok=True)

    generated = 0
    skipped = 0
    failed = 0

    for flow_name, flow_def in FLOWS.items():
        if limit > 0 and generated >= limit:
            log.info(f"Reached limit of {limit} flows. Stopping.")
            break

        flow_path = os.path.join(flows_dir, f"{flow_name}.md")

        # Skip if already generated and not empty
        if os.path.exists(flow_path):
            with open(flow_path, 'r') as f:
                existing = f.read()
            if len(existing) > 500 and 'status: generated' in existing:
                log.info(f"Skip (already exists): {flow_name}")
                skipped += 1
                continue

        # Collect context from domain pages
        context = _collect_flow_context(flow_def, domains, output_dir)
        if not context or len(context) < 200:
            log.warning(f"Skip (no context): {flow_name}")
            skipped += 1
            continue

        log.info(f"Generating flow: {flow_name} ({len(context)} chars context)...")

        prompt = _build_flow_prompt(flow_def, context)

        models_to_try = [model]
        if fallback_model and fallback_model != model:
            models_to_try.append(fallback_model)

        answer = None
        for m in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": "You are a senior Java architect writing end-to-end flow documentation. Be precise, use only the data provided. Write in Markdown."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=5000,
                )
                answer = response.choices[0].message.content
                break
            except Exception as e:
                log.warning(f"LLM call failed for model {m}: {e}")
                continue

        if not answer:
            failed += 1
            log.error(f"Failed to generate flow: {flow_name}")
            continue

        # Write flow page
        questions_str = '\n'.join(f'- "{q}"' for q in flow_def["questions"])
        domains_list = ', '.join(flow_def["domain_patterns"][:15])

        page = f"""---
type: flow
flow: {flow_name}
title: {flow_def['title']}
domains: [{domains_list}]
generated_at: {datetime.now().isoformat()}
status: generated
---

# {flow_def['title']}

{flow_def['description']}

## Questions Answered

{questions_str}

## Domains Covered

{', '.join(f'`{d}`' for d in flow_def['domain_patterns'])}

---

{answer}
"""

        with open(flow_path, 'w', encoding='utf-8') as f:
            f.write(page)

        generated += 1
        log.info(f"  ✅ Generated: {flow_name}")

        if delay > 0:
            time.sleep(delay)

    # Write flows index
    index_path = os.path.join(flows_dir, "index.md")
    index_lines = [
        "# End-to-End Business Flows\n",
        f"Generated: {datetime.now().isoformat()}\n",
        f"**Total flows:** {len(FLOWS)}\n",
        "",
        "These documents describe complete business processes that span multiple code domains.\n",
        "",
    ]
    for flow_name, flow_def in FLOWS.items():
        index_lines.append(f"## [{flow_def['title']}](./{flow_name}.md)")
        index_lines.append(f"")
        index_lines.append(f"{flow_def['description']}")
        index_lines.append(f"")

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(index_lines))

    log.info(f"Flow generation complete: {generated} generated, {failed} failed, {skipped} skipped")
    return {
        "generated": generated,
        "failed": failed,
        "skipped": skipped,
    }


def list_flows() -> dict:
    """Return all defined flows."""
    return FLOWS
