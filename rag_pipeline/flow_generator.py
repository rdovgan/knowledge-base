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
# module:domain_name format is used to disambiguate domains across modules.

FLOWS = {
    # ═══════════════════════════════════════════════════════════
    # SECTION 1: Reservation Lifecycle
    # ═══════════════════════════════════════════════════════════

    "booking_creation": {
        "title": "Booking Creation Flow",
        "section": "Reservation Lifecycle",
        "description": "End-to-end flow from channel inquiry/API request through reservation creation, "
                       "price calculation, payment processing, and confirmation.",
        "domain_patterns": [
            "rest_reservation", "rest_mybookingpal", "rest_bookt",
            "bookingrest_bookingcom", "bookingrest_supplierAPI",
            "homeaway_vrbo_rest_vrbooking", "rest_bookingdom",
            "rest_bookingsync", "friendlyrentals_booking",
            "bookingcom", "bookingcore_rest", "bookingcore_event",
            "supplierAPI_reservation", "supplierAPI_requestToBook",
            "service_reservation", "reservation_calculation",
            "reservation_payment", "reservation_dto",
            "reservation_partner", "shared_reservation",
            "utils_reservation", "reservation_clarity",
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
        "title": "Booking Cancellation Flow & Cancellation Types Hierarchy",
        "section": "Reservation Lifecycle",
        "description": "End-to-end flow for cancelling a reservation: cancel request → "
                       "cancellation policy hierarchy → refund calculation → state change → notifications. "
                       "Covers all cancellation types: guest-initiated, PM-initiated, channel-initiated, "
                       "no-show, modification-caused cancellation, and force majeure.",
        "domain_patterns": [
            "reservation_cancel", "shared_cancellation:mbp", "shared_cancellation:dataaccesslayer",
            "supplierAPI_cancellationPolicy",
            "itrip_cancelBooking", "service_reservation",
            "reservation_calculation", "reservation_payment",
            "reservation_clarity", "supplierAPI_reservation",
            "shared_policy", "reservation_dto",
        ],
        "questions": [
            "How does reservation cancellation work?",
            "What are the different cancellation types and their hierarchy?",
            "How are refunds calculated for cancellations?",
            "What is the cancellation policy flow?",
            "What is the difference between guest cancellation, PM cancellation, and channel cancellation?",
            "How does no-show cancellation work?",
            "What happens when a modification causes a cancellation?",
        ],
    },

    "booking_modification": {
        "title": "Booking Modification Flow",
        "section": "Reservation Lifecycle",
        "description": "How existing reservations are modified: date changes, guest changes, "
                       "price recalculation, payment adjustment, and PMS sync.",
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

    "failed_reservation": {
        "title": "Failed Reservation & Error Recovery Flow",
        "section": "Reservation Lifecycle",
        "description": "How failed reservations are handled: payment failure, PMS rejection, "
                       "channel timeout, duplicate detection, retry mechanisms, pending transaction management, "
                       "and compensation flows that cancel already-processed parts.",
        "domain_patterns": [
            "rest_reservation", "service_reservation",
            "reservation_payment", "reservation_partner",
            "shared_reservation", "shared_exceptions:core-module", "shared_exceptions:mbp",
            "reservation_calculation", "reservation_dto",
            "homeaway_vrbo_rest_vrbooking", "bookingrest_bookingcom",
            "rest_error", "queue_consumers",
        ],
        "questions": [
            "What happens when a reservation fails?",
            "How does the system handle payment failures during booking?",
            "What is the error recovery flow for failed reservations?",
            "How are pending transactions managed when a booking fails?",
            "How does duplicate reservation detection work?",
            "What compensation flows exist for partially completed bookings?",
        ],
    },

    "inquiry_tracking": {
        "title": "Inquiry Tracking & Request-to-Book Flow",
        "section": "Reservation Lifecycle",
        "description": "How booking inquiries are received, tracked, and converted to reservations: "
                       "inquiry receipt → availability check → quote → conversion to booking.",
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

    # ═══════════════════════════════════════════════════════════
    # SECTION 2: Pricing & Quote Calculation
    # ═══════════════════════════════════════════════════════════

    "quote_calculation": {
        "title": "Quote Calculation Flow",
        "section": "Pricing & Quote Calculation",
        "description": "How a price quote is calculated for a stay request: base rate lookup → "
                       "LOS rate lookup (Cassandra) → promotions/yields application → fee calculation → "
                       "tax calculation → commission calculation → channel markup → final quote. "
                       "Covers the full quote pipeline across product types.",
        "domain_patterns": [
            "reservation_calculation", "shared_quote", "shared_price",
            "utils_price", "json_price",
            "server_promotions", "shared_rate",
            "dto_chargefee", "calculation_fee",
            "calculation_strategy",
            "reservation_dto", "shared_commission:core-module", "shared_commission:mbp",
            "shared_fee", "shared_policy",
            "supplierAPI_revenueManagment", "supplierAPI_yield",
            "reservation_clarity",
        ],
        "questions": [
            "How is a quote calculated for a stay?",
            "What is the quote calculation pipeline?",
            "How are promotions applied to quotes?",
            "How are fees and taxes calculated in a quote?",
            "How does the pricing strategy work?",
            "How is the base rate determined for a quote?",
            "What is the difference between rack rate, LOS rate, and promotional rate?",
        ],
    },

    "los_pricing": {
        "title": "Length-of-Stay (LOS) Price Calculation & Import",
        "section": "Pricing & Quote Calculation",
        "description": "How LOS (Length-of-Stay) prices are stored in Cassandra, imported from channels/PMS, "
                       "and used for pricing. Covers: LOS price import from Booking.com/Expedia/Airbnb/HomeAway, "
                       "LOS-to-calendar transformation, Cassandra storage model, and LOS rate export to channels.",
        "domain_patterns": [
            "supplierAPI_losRates", "shared_rate",
            "airbnb_core_event", "airbnb_core_rest",
            "expedia_core_rest", "expedia_rest_expedia",
            "bookingrest_bookingcom", "bookingcore_rest",
            "homeaway_vrbo_rest_vrbooking",
            "server_nosql", "shared_dao",
            "reservation_calculation",
            "supplierAPI_priceRecommendation",
            "rest_channel:core-module", "rest_channel:mbp",
            "service_availability", "shared_restriction",
        ],
        "questions": [
            "How are LOS prices calculated?",
            "How are LOS prices imported from channels?",
            "How are LOS prices sent to channels?",
            "How does Cassandra store LOS prices?",
            "What is the LOS pricing model?",
            "How does the LOS import from Booking.com work?",
            "How does the LOS import from Expedia work?",
            "How does the LOS import from Airbnb work?",
            "How are LOS rates converted to daily rates?",
        ],
    },

    "product_types": {
        "title": "Product Types: Single Unit, Multi-Representational, Multi-Key",
        "section": "Pricing & Quote Calculation",
        "description": "How different product types work in MyBookingPal: Single Unit (one property = one listing), "
                       "Multi-Representational (one property = multiple rate plans/listings), and "
                       "Multi-Key (one property = multiple bookable units). How quote calculation, "
                       "availability, and calendar management differ across product types.",
        "domain_patterns": [
            "singleunit_dto", "singleunit_service",
            "multiunit_dto", "multiunit_service", "multiunit_channel", "multiunit_utils",
            "shared_multiunits", "batch_multiunit",
            "rest_multiunit", "model_multiunit",
            "service_units", "service_product",
            "rest_units", "shared_product",
            "reservation_calculation", "reservation_dto",
            "supplierAPI_product", "supplierAPI_listing",
        ],
        "questions": [
            "What are the different product types in MyBookingPal?",
            "How does a Single Unit product work?",
            "How does a Multi-Representational product work?",
            "How does a Multi-Key product work?",
            "How does quote calculation differ by product type?",
            "How does availability work for multi-key products?",
            "What is the difference between multi-rep and multi-key?",
            "How are units managed in multi-key products?",
        ],
    },

    "pricing_promotions": {
        "title": "Pricing, Promotions & Yield Management",
        "section": "Pricing & Quote Calculation",
        "description": "How prices are calculated: base rate → promotions → yields → fees → taxes → "
                       "channel-specific markups → final price. Covers weekend yields, day-of-week yields, "
                       "length-of-stay discounts, early bird, last minute, and channel-specific promotions.",
        "domain_patterns": [
            "reservation_calculation", "service_reservation",
            "reservation_clarity", "dto_chargefee",
            "reservation_dto", "shared_reservation",
            "supplierAPI_revenueManagment", "server_promotions",
            "shared_fee", "shared_rate", "shared_price",
            "calculation_fee", "calculation_strategy",
            "utils_price", "json_price",
        ],
        "questions": [
            "How is pricing calculated for a reservation?",
            "How do promotions work?",
            "How are fees and taxes calculated?",
            "What is the pricing strategy?",
            "How do yields work?",
            "How does revenue management work?",
            "How are weekend rates applied?",
            "How do length-of-stay discounts work?",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SECTION 3: Payment Processing
    # ═══════════════════════════════════════════════════════════

    "payment_processing": {
        "title": "Payment Processing Flow",
        "section": "Payment Processing",
        "description": "End-to-end payment flow: payment method selection → gateway interaction → "
                       "commission calculation → payout → transaction recording. "
                       "Covers LOCAL, API, CHANNEL_PARTNER, SUPPLIER_API, MAIL, PMS_GATEWAY payment types.",
        "domain_patterns": [
            "reservation_payment", "payment_stripe", "rent_paymentrequest",
            "rest_reservation", "service_reservation",
            "reservation_clarity", "reservation_calculation",
            "shared_reservation", "supplierAPI_reservation",
            "shared_commission:core-module", "shared_commission:mbp",
            "shared_transaction", "server_commission:core-module", "server_commission:mbp",
        ],
        "questions": [
            "How does payment processing work?",
            "How are commissions calculated?",
            "How does Stripe integration work?",
            "What is the payment flow for a booking?",
        ],
    },

    "funds_holder": {
        "title": "Payment Flow by Funds Holder Type",
        "section": "Payment Processing",
        "description": "How payment routing differs based on the 'funds holder' configuration: "
                       "MBP holds funds, Channel Partner holds funds, Property Manager holds funds, "
                       "PMS Gateway holds funds. Covers money flow, commission distribution, payout timing, "
                       "and transaction recording for each funds holder type.",
        "domain_patterns": [
            "reservation_payment", "rest_reservation",
            "shared_transaction", "shared_commission:core-module", "shared_commission:mbp",
            "server_commission:core-module", "server_commission:mbp",
            "reservation_clarity", "shared_reservation",
            "reservation_calculation", "reservation_partner",
            "payment_stripe", "rent_paymentrequest",
        ],
        "questions": [
            "How does the funds holder setting affect payment?",
            "What happens when MBP holds funds vs the channel?",
            "How does payment work when the property manager holds funds?",
            "How does PMS Gateway payment work?",
            "How are commissions distributed based on funds holder?",
            "What is the difference between funds holder types?",
            "How does payout work for each funds holder?",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SECTION 4: Channel Integration
    # ═══════════════════════════════════════════════════════════

    "channel_bookingcom": {
        "title": "Booking.com Integration Flow",
        "section": "Channel Integration",
        "description": "How MyBookingPal integrates with Booking.com: content sync → "
                       "availability push → reservation pull/push → confirmation push → payment reconciliation. "
                       "Covers OTA API, reservation pull scheduler, delta/full sync, and LOS pricing.",
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
            "How does the Booking.com reservation pull work?",
            "How are rates and availability pushed to Booking.com?",
        ],
    },

    "channel_airbnb": {
        "title": "Airbnb Integration Flow",
        "section": "Channel Integration",
        "description": "How MyBookingPal integrates with Airbnb: OAuth2 connection → "
                       "listing sync → availability/calendar push → inquiry/booking webhooks → "
                       "reservation creation → messaging → review sync. Covers Airbnb-specific "
                       "pricing (unbundled fees, pass-through taxes) and multi-unit handling.",
        "domain_patterns": [
            "airbnb", "airbnb_core_rest", "airbnb_core_event", "airbnb_core_calculation",
            "airbnb_rest_airbnb:mbp", "airbnb_rest_supplierAPI", "airbnb_rest_wheelhouse",
            "airbnb_dto_airbnb", "airbnb_rest_scrappedfromchannel",
            "service_reservation", "reservation_calculation",
            "reservation_payment", "rest_reservation",
            "supplierAPI_reservation", "shared_reservation",
            "oauth2",
        ],
        "questions": [
            "How does Airbnb integration work?",
            "How are bookings received from Airbnb?",
            "How does Airbnb OAuth2 connection work?",
            "How does Airbnb inquiry handling work?",
            "How are Airbnb unbundled fees handled?",
            "How does calendar sync work with Airbnb?",
            "How does Airbnb multi-unit listing work?",
        ],
    },

    "channel_expedia": {
        "title": "Expedia Integration Flow",
        "section": "Channel Integration",
        "description": "How MyBookingPal integrates with Expedia Group (Expedia, Hotels.com, Vrbo via Expedia): "
                       "listing management → rate/availability push → booking retrieval → "
                       "confirmation → cancellation. Covers Expedia-specific API, LOS rates, and batch processing.",
        "domain_patterns": [
            "expedia", "expedia_core_rest", "expedia_core_calculation",
            "expedia_rest_expedia", "expedia_batch_expedia",
            "service_reservation", "reservation_calculation",
            "reservation_payment", "rest_reservation",
            "supplierAPI_reservation", "shared_reservation",
        ],
        "questions": [
            "How does Expedia integration work?",
            "How are bookings received from Expedia?",
            "How does Expedia batch processing work?",
            "How are rates pushed to Expedia?",
            "How does Expedia LOS pricing work?",
        ],
    },

    "channel_homeaway": {
        "title": "HomeAway/VRBO Integration Flow",
        "section": "Channel Integration",
        "description": "How MyBookingPal integrates with HomeAway/VRBO: listing sync → "
                       "inquiry handling → booking → confirmation → payment. "
                       "Covers HomeAway-specific fee handling, PMS availability checks, and iCal sync.",
        "domain_patterns": [
            "homeaway_vrbo_rest_vrbooking",
            "service_reservation", "reservation_calculation",
            "reservation_payment", "rest_reservation",
            "supplierAPI_reservation", "shared_reservation",
            "reservation_cancel",
        ],
        "questions": [
            "How does HomeAway/VRBO integration work?",
            "How are bookings received from VRBO?",
            "How does VRBO inquiry handling work?",
            "How are fees handled for HomeAway bookings?",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SECTION 5: Rates & Availability
    # ═══════════════════════════════════════════════════════════

    "rates_availability": {
        "title": "Rates & Availability Management",
        "section": "Rates & Availability",
        "description": "How rates and availability are managed in the platform: rate creation → "
                       "calendar management → restriction rules → channel push. "
                       "Covers daily rates, LOS rates, restrictions (min stay, closed to arrival/departure, "
                       "CTA/CTD), and how they propagate to connected channels.",
        "domain_patterns": [
            "supplierAPI_rateAvailability", "supplierAPI_losRates",
            "supplierAPI_ratePlans", "supplierAPI_yield",
            "shared_rate", "shared_price", "shared_restriction",
            "service_availability", "rest_availability",
            "service_restriction",
            "rest_channel:core-module", "rest_channel:mbp",
            "shared_predicate",
            "service_units", "rest_units",
        ],
        "questions": [
            "How are rates and availability managed?",
            "How do restriction rules work?",
            "What are CTA/CTD restrictions?",
            "How do minimum stay restrictions work?",
            "How are rates pushed to channels?",
            "How does availability sync work?",
            "What is the rate calendar?",
        ],
    },

    "rates_import": {
        "title": "Rates Import & Price Recommendation",
        "section": "Rates & Availability",
        "description": "How rates are imported into MyBookingPal from external sources: "
                       "PMS rate import, channel rate import, iCal import, XML feed parsing, "
                       "and the price recommendation engine (Wheelhouse integration). "
                       "Covers scheduled jobs, cron tasks, and batch processing for rate updates.",
        "domain_patterns": [
            "supplierAPI_priceRecommendation", "supplierAPI_losRates",
            "supplierAPI_rateAvailability",
            "airbnb_rest_wheelhouse", "supplierAPI_wheelhouse",
            "server_cron4j:core-module", "server_cron4j:mbp",
            "server_job", "script_targets",
            "shared_rate", "shared_price",
            "server_script",
            "booking_tasklet", "expedia_batch_expedia",
            "server_ftp",
            "supplierAPI_importFromChannel",
            "reservation_importCalendar",
        ],
        "questions": [
            "How are rates imported into the system?",
            "How does the price recommendation engine work?",
            "How does Wheelhouse integration work?",
            "How are rates imported from PMS?",
            "How does iCal import work?",
            "How do scheduled rate update jobs work?",
            "How does XML feed rate parsing work?",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SECTION 6: Infrastructure & Technology
    # ═══════════════════════════════════════════════════════════

    "kafka_messaging": {
        "title": "Kafka Messages & Event-Driven Architecture",
        "section": "Infrastructure & Technology",
        "description": "How Kafka messages are used throughout the platform: event types (reservation created, "
                       "modified, cancelled; availability changed; listing updated), message producers, "
                       "consumers, topics, and the queue consumer architecture. "
                       "Covers channel event processing and async workflows.",
        "domain_patterns": [
            "queue_consumers", "shared_messaging",
            "wm_endpoint", "wm_model",
            "airbnb_core_event", "bookingcore_event",
            "server_thread",
            "rest_response", "shared_api:dataaccesslayer", "shared_api:mbp",
            "api_strategy",
        ],
        "questions": [
            "How are Kafka messages used in the system?",
            "What events are published when a reservation is created?",
            "How do queue consumers work?",
            "What is the event-driven architecture?",
            "How are channel events processed asynchronously?",
            "What Kafka topics exist?",
            "How does message routing work?",
        ],
    },

    "elasticsearch": {
        "title": "Elasticsearch Integration",
        "section": "Infrastructure & Technology",
        "description": "How Elasticsearch is used in the platform: product search, "
                       "availability search, listing indexing, full-text search, "
                       "geolocation queries, and the search API. Covers index management, "
                       "data synchronization, and query construction.",
        "domain_patterns": [
            "dal_elastic", "shared_search:core-module",
            "shared_dao", "rest_channel:core-module",
            "shared_dto:core-module", "shared_api:dataaccesslayer",
            "service_location:core-module", "service_location:mbp",
            "rest_registration",
        ],
        "questions": [
            "How is Elasticsearch used in the platform?",
            "How does product search work?",
            "How are listings indexed in Elasticsearch?",
            "How does availability search work?",
            "How is data synced to Elasticsearch?",
            "How do geolocation queries work?",
        ],
    },

    "redis_cache": {
        "title": "Redis Cache Usage",
        "section": "Infrastructure & Technology",
        "description": "How Redis is used for caching throughout the platform: "
                       "caching strategies, cache invalidation, distributed locking, "
                       "rate limiting, session management, and data structures used. "
                       "Covers Redis client configuration and common cache patterns.",
        "domain_patterns": [
            "redis:redis", "redis:mbp",
            "server_cache:core-module", "server_cache:mbp",
            "cache", "cache_dto",
            "shared_predicate",
        ],
        "questions": [
            "How is Redis used in the platform?",
            "What is cached in Redis?",
            "How does cache invalidation work?",
            "How does distributed locking work with Redis?",
            "What Redis data structures are used?",
            "How does the Redis client work?",
        ],
    },

    "cassandra_los": {
        "title": "Cassandra Storage for LOS Prices",
        "section": "Infrastructure & Technology",
        "description": "How Apache Cassandra is used to store and retrieve Length-of-Stay (LOS) prices: "
                       "data model, column family design, write path (import from channels), "
                       "read path (quote calculation), consistency levels, and compaction strategies. "
                       "Covers the NoSQL layer for high-throughput price data.",
        "domain_patterns": [
            "server_nosql", "supplierAPI_losRates",
            "shared_dao", "mybatis_typehandler",
            "supplierAPI_rateAvailability",
            "reservation_calculation",
            "shared_rate", "shared_price",
        ],
        "questions": [
            "How is Cassandra used for LOS prices?",
            "What is the Cassandra data model for LOS prices?",
            "How are LOS prices written to Cassandra?",
            "How are LOS prices read from Cassandra?",
            "What consistency levels are used?",
            "How does the NoSQL layer work?",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SECTION 7: PMS Integration
    # ═══════════════════════════════════════════════════════════

    "pms_integration": {
        "title": "PMS Integrations (Maestro, Streamline, LiveRez, Kigo, etc.)",
        "section": "PMS Integration",
        "description": "How MyBookingPal integrates with Property Management Systems: "
                       "reservation push/pull, availability sync, rate sync, guest data sync, "
                       "and PMS-specific adapters. Covers Maestro (SOAP OTA), Streamline, LiveRez, "
                       "Kigo, and other PMS integrations.",
        "domain_patterns": [
            "maestro_rest_maestro", "streamline",
            "liverez", "kigo",
            "soap_ota", "ota_server",
            "service_reservation", "rest_reservation",
            "reservation_importCalendar",
            "supplierAPI_reservation",
            "rest_availability", "service_availability",
            "server_api:mbp", "server_api:dataaccesslayer",
            "marriott_rest_marriott", "marriott_service_marriott", "marriott_shared_marriott",
            "script_collectingFeesAndTaxesFromPMS",
        ],
        "questions": [
            "How does PMS integration work?",
            "How does Maestro integration work?",
            "How does Streamline integration work?",
            "How does LiveRez integration work?",
            "How does Kigo integration work?",
            "How are reservations pushed to PMS?",
            "How does availability sync with PMS work?",
            "How does the SOAP OTA integration work?",
            "How does Marriott PMS integration work?",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # SECTION 8: Technical Architecture
    # ═══════════════════════════════════════════════════════════

    "tech_architecture": {
        "title": "Technical Architecture: Modules & Dependencies",
        "section": "Technical Architecture",
        "description": "The overall technical architecture of MyBookingPal: module structure, "
                       "layer organization, dependency graph between modules (mbp, core-module, "
                       "dataaccesslayer, parent-dal, channel-integration, channel-batch-jobs, "
                       "web-messages, redis, mbp-utils). Covers how modules relate to each other, "
                       "shared code patterns, and the technology stack.",
        "domain_patterns": [
            "shared_dao", "shared_dto:dataaccesslayer", "shared_dto:core-module",
            "shared_api:dataaccesslayer", "shared_api:mbp",
            "shared_exceptions:core-module", "shared_exceptions:mbp",
            "shared_validator", "shared_channel",
            "server_api:mbp", "server_api:dataaccesslayer",
            "rest_authorization", "oauth2",
            "utils_enums", "utils_entity", "utils_service",
            "server_util:dataaccesslayer", "server_util:core-module",
            "rest_channel:core-module",
            "shared_predicate", "shared_registration",
            "provider", "provider_masking",
            "mybatis_typehandler",
        ],
        "questions": [
            "What is the overall architecture of MyBookingPal?",
            "How do the modules relate to each other?",
            "What is the dependency graph between modules?",
            "What technologies are used (Spring, MyBatis, Redis, Cassandra, Elasticsearch)?",
            "How is the codebase organized?",
            "What shared code exists between modules?",
            "How does the data access layer work?",
            "What is the role of each module?",
        ],
    },

    "manual_reservation": {
        "title": "Manual / Direct Reservation Flow",
        "section": "Reservation Lifecycle",
        "description": "How manual/offline reservations are created: PM creates reservation → "
                       "price override → payment recording → confirmation → PMS sync.",
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
}


def _load_domain_page(output_dir: str, domain_name: str, module: str) -> Optional[str]:
    """Load the content of a domain page."""
    safe_name = domain_name.replace('/', '_').replace(' ', '_')
    path = os.path.join(output_dir, module, '_domains', f"{safe_name}.md")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    # Try all modules
    if os.path.isdir(output_dir):
        for mod_dir in os.listdir(output_dir):
            mod_path = os.path.join(output_dir, mod_dir, '_domains', f"{safe_name}.md")
            if os.path.exists(mod_path):
                with open(mod_path, 'r', encoding='utf-8') as f:
                    return f.read()
    return None


def _find_domain_in_json(domains: List[dict], name: str, module: str = None) -> Optional[dict]:
    """Find a domain by name (and optionally module) in the domains list."""
    for d in domains:
        if d.get('name') == name:
            if module is None or d.get('module') == module:
                return d
    # Fallback: return first match by name
    if module is not None:
        for d in domains:
            if d.get('name') == name:
                return d
    return None


def _collect_flow_context(flow_def: dict, domains: List[dict], output_dir: str) -> str:
    """Collect relevant domain page content for a flow."""
    context_parts = []
    seen_domains = set()

    for pattern in flow_def["domain_patterns"]:
        # Parse module qualifier: "domain_name" or "domain_name:module"
        if ':' in pattern:
            domain_name, module = pattern.rsplit(':', 1)
        else:
            domain_name = pattern
            module = None

        dedup_key = f"{domain_name}:{module or '*'}"
        if dedup_key in seen_domains:
            continue
        seen_domains.add(dedup_key)

        # Find the domain
        dom = _find_domain_in_json(domains, domain_name, module)
        if not dom:
            continue

        actual_module = dom.get('module', '')
        content = _load_domain_page(output_dir, domain_name, actual_module)
        if content:
            # Strip frontmatter
            if content.startswith('---'):
                end = content.find('---', 3)
                if end > 0:
                    content = content[end + 3:].strip()

            # Truncate to ~3000 chars per domain to fit context window
            if len(content) > 3000:
                marker = "## Architecture & Business Logic"
                idx = content.find(marker)
                if idx >= 0:
                    enriched = content[idx:]
                    if len(enriched) > 3000:
                        enriched = enriched[:3000] + "\n... (truncated)"
                    context_parts.append(f"### Domain: {domain_name} (module: {actual_module})\n\n{enriched}")
                else:
                    context_parts.append(f"### Domain: {domain_name} (module: {actual_module})\n\n{content[:3000]}... (truncated)")
            else:
                context_parts.append(f"### Domain: {domain_name} (module: {actual_module})\n\n{content}")

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
7. **Channel/system variations** — How does the flow differ across channels or system configurations?

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

        # Skip if already generated and not empty (use --force to regenerate)
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
        domains_list = ', '.join(flow_def["domain_patterns"][:20])
        section = flow_def.get("section", "")

        page = f"""---
type: flow
flow: {flow_name}
title: {flow_def['title']}
section: {section}
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

    # Write flows index organized by section
    _write_flows_index(flows_dir)

    # Write GitBook SUMMARY.md
    _write_gitbook_summary(flows_dir)

    log.info(f"Flow generation complete: {generated} generated, {failed} failed, {skipped} skipped")
    return {
        "generated": generated,
        "failed": failed,
        "skipped": skipped,
    }


def _write_flows_index(flows_dir: str):
    """Write index.md organized by sections."""
    sections = {}
    for flow_name, flow_def in FLOWS.items():
        section = flow_def.get("section", "Other")
        if section not in sections:
            sections[section] = []
        sections[section].append((flow_name, flow_def))

    index_lines = [
        "# End-to-End Business Flows\n",
        f"Generated: {datetime.now().isoformat()}\n",
        f"**Total flows:** {len(FLOWS)}\n",
        "",
        "These documents describe complete business processes that span multiple code domains.\n",
        "",
    ]

    for section_name, flows in sections.items():
        index_lines.append(f"## {section_name}")
        index_lines.append("")
        for flow_name, flow_def in flows:
            index_lines.append(f"### [{flow_def['title']}](./{flow_name}.md)")
            index_lines.append(f"")
            index_lines.append(f"{flow_def['description']}")
            index_lines.append(f"")

    index_path = os.path.join(flows_dir, "index.md")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(index_lines))


def _write_gitbook_summary(flows_dir: str):
    """Write GitBook SUMMARY.md with section grouping."""
    sections = {}
    for flow_name, flow_def in FLOWS.items():
        section = flow_def.get("section", "Other")
        if section not in sections:
            sections[section] = []
        sections[section].append((flow_name, flow_def))

    lines = ["# Summary", ""]
    lines.append("- [End-to-End Business Flows](./index.md)")
    lines.append("")

    for section_name, flows in sections.items():
        # GitBook doesn't support section headers in SUMMARY directly,
        # so we use a blank entry with bold as a visual separator
        lines.append(f"- **{section_name}**")
        for flow_name, flow_def in flows:
            lines.append(f"  - [{flow_def['title']}](./{flow_name}.md)")
        lines.append("")

    summary_path = os.path.join(flows_dir, "SUMMARY.md")
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def list_flows() -> dict:
    """Return all defined flows."""
    return FLOWS
