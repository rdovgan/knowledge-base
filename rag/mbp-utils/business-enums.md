---
module: mbp-utils
domain: business-enums
generated_at: 2025-01-09T12:30:00Z
status: approved
review_score: 0.95
attempts: 2
---

# Business Enums Domain Documentation

## Overview

The `business-enums` domain within the `mbp-utils` module provides a comprehensive collection of enumerations and language utilities that define core business constants for the BookingPal platform. This domain serves as the central source of truth for all business logic enums, ensuring consistency across distributed systems and preventing magic values throughout the codebase.

## Package Structure

```
com.mybookingpal.utils.enums
├── BookingPalEnums.java
└── Language.java
```

## Core Components

### 1. Valued Interface

The `Valued` interface is a contract that all business enums implement to provide both numeric and string representations of their values.

```java
public interface Valued {
    int getValue();
    String getStringValue();
}
```

This interface enables:
- Database mapping (integer values)
- API communication (string values)
- Type-safe enum conversion

#### Utility Methods for Valued Enums

The `BookingPalEnums` class provides several static methods for working with `Valued` enums:

```java
// Get enum by integer value
public static <E extends Enum<E>> E getValuedEnum(Class<E> clazz, int value)

// Get enum by string value
public static <E extends Enum<E>> E getValuedEnum(Class<E> clazz, String value)

// Get enum by name (case-insensitive)
public static <E extends Enum<E>> E getEnum(Class<E> clazz, String name)

// Null-safe version returning null instead of throwing exception
public static <E extends Enum<E>> E getValuedEnumNullSafe(Class<E> clazz, String value)
public static <E extends Enum<E>> E getValuedEnumNullSafe(Class<E> clazz, int value)
```

**Usage Example:**
```java
// Returns PriceType.LOCAL (value 0)
PriceType local = BookingPalEnums.getValuedEnum(PriceType.class, 0);

// Returns Channel.AIRBNB
Channel airbnb = BookingPalEnums.getValuedEnum(Channel.class, "ABB");

// Returns null if not found (safe operation)
Channel unknown = BookingPalEnums.getValuedEnumNullSafe(Channel.class, "UNKNOWN");
```

## BookingPalEnums

The `BookingPalEnums` class is a container for all business enumerations. Each enum is a nested static class implementing `Valued` (except where noted).

### 2. YieldType Enum

Defines various yield management and promotion types used in pricing strategies.

```java
public enum YieldType implements Valued {
    DATE_RANGE("Date Range"), 
    DAY_OF_WEEK("Day of Week"), 
    GAP_FILLER("Maximum Gap Filler"), 
    EARLY_BIRD("Early Booking Lead Time"), 
    LAST_MINUTE("Last Minute Lead Time"), 
    LENGTH_OF_STAY("Length of Stay"), 
    OCCUPANCY_ABOVE("Occupancy Above"), 
    OCCUPANCY_BELOW("Occupancy Below"), 
    WEEKEND("Weekend"), 
    WEEKLY("Weekly"),
    BASE("Basic Promotion"), 
    SAME_DAY_DEAL("Same Day Deal"), 
    EARLY_BOOKING_DEAL("Early Booking Deal"), 
    FREE_NIGHTS("Free Nights"), 
    SEASONAL_ADJUSTMENT("Season adjustment"), 
    STAYED_AT_LEAST_X_DAYS("Long-term stay adjustment"), 
    BOOKED_WITHIN_AT_MOST_X_DAYS("Last-minute discount"), 
    BOOKED_BEYOND_AT_LEAST_X_DAYS("Booking ahead discount"), 
    MOBILE_RATE("Mobile rate"), 
    BUSINESS_BOOKER("Business booker"), 
    GEO_RATE("Geo rate"), 
    CHANNEL_MARKUP("Channel Markup"), 
    CHANNEL_FEE_MARKUP("Channel Fee Markup");
}
```

#### Business Rules and Categorization

The `YieldType` enum provides several static methods to categorize yields:

| Method | Purpose | Includes |
|--------|---------|----------|
| `getSpecialPromotions()` | Core promotional offers | BASE, SAME_DAY_DEAL, EARLY_BOOKING_DEAL, FREE_NIGHTS |
| `getGeneralPromotions()` | General promotion types | DATE_RANGE, WEEKEND, WEEKLY, DAY_OF_WEEK, LENGTH_OF_STAY, LAST_MINUTE, EARLY_BIRD, OCCUPANCY_ABOVE, OCCUPANCY_BELOW |
| `getYields()` | Yield adjustment types | WEEKEND, DAY_OF_WEEK, GAP_FILLER, LENGTH_OF_STAY, OCCUPANCY_ABOVE, OCCUPANCY_BELOW |
| `getPMSSupportedYields()` | Yields supported by PMS | WEEKEND, DAY_OF_WEEK, DATE_RANGE, EARLY_BIRD, LAST_MINUTE, GAP_FILLER, LENGTH_OF_STAY, OCCUPANCY_ABOVE, OCCUPANCY_BELOW |
| `getPromotions()` | All promotion types | BASE, SAME_DAY_DEAL, EARLY_BOOKING_DEAL, FREE_NIGHTS, SEASONAL_ADJUSTMENT, STAYED_AT_LEAST_X_DAYS, BOOKED_WITHIN_AT_MOST_X_DAYS, BOOKED_BEYOND_AT_LEAST_X_DAYS, MOBILE_RATE, GEO_RATE, BUSINESS_BOOKER |
| `getPromotionsForRackRate()` | Promotions applicable to rack rates | BASE, SAME_DAY_DEAL, EARLY_BOOKING_DEAL, FREE_NIGHTS, WEEKEND, LENGTH_OF_STAY |
| `getAIRBNBPromotions()` | Airbnb-specific promotions | SEASONAL_ADJUSTMENT, STAYED_AT_LEAST_X_DAYS, BOOKED_WITHIN_AT_MOST_X_DAYS, BOOKED_BEYOND_AT_LEAST_X_DAYS |

**Usage Example:**
```java
// Check if a yield is a special promotion
Set<YieldType> specialPromos = YieldType.getSpecialPromotions();
boolean isSpecial = specialPromos.contains(YieldType.FREE_NIGHTS);

// Get all PMS-supported yields
Set<YieldType> pmsYields = YieldType.getPMSSupportedYields();
```

### 3. Channel Enum

Defines all distribution channels supported by the platform, including OTAs (Online Travel Agencies), PMS systems, and internal channels.

```java
public enum Channel implements Valued {
    // Major OTAs
    BOOKINGCOM("Booking.com", "BKG"), 
    AIRBNB("AirBnb", "ABB"), 
    AIRBNB_STAGING("AirBnb", "ABBStaging"), 
    EXPEDIA("Expedia", "EXP"), 
    EXPEDIA_HC("Expedia Hotel Collect", "EXP_HC"), 
    EXPEDIA_HC_OLD("Expedia Hotel Collect Old", "EXP_HC_OLD"), 
    HOMEAWAY("HomeAway", "HAC"), 
    AGODA("Agoda", "AGD"), 
    TRIP_ADVISOR("Trip advisor", "TRA"), 
    
    // Search and Direct Channels
    GOOGLE("Google", "GGL"), 
    
    // Hotel Chains
    MARRIOTT("Marriott", "MRT"), 
    HYATT("Hyatt", "HYATT"), 
    HVMI_MARRIOT("HVMI Marriott", "HVMI"), 
    
    // Vacation Rental Platforms
    THIRDHOME("ThirdHome", "TRH"), 
    HOME_TO_GO("HomeToGo", "HTOG"), 
    
    // Regional and Specialized Channels
    SECRA("Secra", "SCR"), 
    FEWO("Fewo", "FEWO"), 
    INNTOPIA("Inntopia", "INP"), 
    PLUM_GUIDE("Plum Guide", "PLMG"), 
    BEACH_HOUSE("BeachHouse", "BHS"), 
    ATLAS("Atlas", "ATLS"), 
    SKI_DOT_COM("Ski.com", "SKI"), 
    WHIMSTAY("Whimstay", "WHM"), 
    YONDER("Yonder", "YON"), 
    YONDER_AFFILIATE("Yonder Affiliate", "YND"), 
    GOT_TO_GO("Got2Go", "GTG"), 
    LODGEA("Lodgea", "LOG"), 
    BEACH_GUIDE("BeachGuide", "BHG"), 
    VACATION_AT_MY_PLACE("Vacation At My Place", "VAMP"), 
    RENTALZ("Rentalz", "RETZ"), 
    RENTALZ_TWO("Rentalz2", "RENZ"), 
    RENTBUTTON("RentButton", "RNTZ"), 
    SMILING_HOUSE("Smiling House", "SGH"), 
    SMOKY_MOUNTAIN("Smoky Mountain", "SMK"), 
    THE_BACH("The BACH", "BACH"), 
    QUINTESS_COLLECTIONS("Quintess Collections", "QUIN"), 
    MOUNTAIN_SKI_TRIPS("Mountain Ski Trips", "MSR"), 
    MONAKER_BOOKING("Monaker Booking", "MNB"), 
    
    // API and Integration Channels
    BOOKINGPAL("Bookingpal", "BP"), 
    ALLEGIANT_AIR("Allegiant Air", "AAY"), 
    WA_HOME_STAY("WaHomeStay", "WAH"), 
    TRAVEL_STAYTION("TravelStaytion", "TVS"), 
    THIRD_HOME("Thirdhome", "THD"), 
    CHANNEL_CONNECTOR("Channel Connector", "ZUM"), 
    SOJOURN_API("SojournAPI", "SOJ"), 
    UNA_TRAVEL_FROM_XOKIND("Una Travel from XOKind", "XOK"), 
    
    // Testing and Internal
    TEST_CHANNEL("Test Channel", "TCA");
}
```

#### Channel Properties

Each channel has two properties:
- **Name**: Full display name (e.g., "Booking.com")
- **Value**: Abbreviation/code (e.g., "BKG")

#### Note on THIRDHOME vs THIRD_HOME

There are two separate channel constants with similar names:
- `THIRDHOME("ThirdHome", "TRH")` - The primary ThirdHome channel
- `THIRD_HOME("Thirdhome", "THD")` - A separate ThirdHome channel variant

These are distinct channels with different codes ("TRH" vs "THD") and should be treated independently.

#### Channel Categorization Methods

| Method | Purpose | Channels |
|--------|---------|----------|
| `getChannelAbbreviations()` | Channels with standard abbreviations | BOOKINGCOM, AIRBNB, EXPEDIA, EXPEDIA_HC, EXPEDIA_HC_OLD, HOMEAWAY, GOOGLE, INNTOPIA |
| `getExpediaAbbreviations()` | All Expedia variants | EXPEDIA, EXPEDIA_HC, EXPEDIA_HC_OLD |
| `getChannels()` | Primary distribution channels | BOOKINGCOM, AIRBNB, EXPEDIA, HOMEAWAY, AGODA, TRIP_ADVISOR, GOOGLE, INNTOPIA |
| `getSupportedDifferentDisplayNamesChannel()` | Channels with custom display names | AIRBNB, BOOKINGCOM, EXPEDIA, HOMEAWAY, EXPEDIA_HC |
| `getChannelsForGuidelinesProducts()` | Channels with guideline products | MARRIOTT |
| `getChannelsSupportedChannelCommissionOnProductLevel()` | Channels supporting product-level commissions | BOOKINGCOM, EXPEDIA, EXPEDIA_HC, AIRBNB, TRIP_ADVISOR, HOMEAWAY |
| `getSupportedChannelSpecificTax()` | Channels supporting channel-specific taxes | BOOKINGCOM, EXPEDIA, EXPEDIA_HC, AIRBNB, HOMEAWAY |

**Usage Example:**
```java
// Get channel display name
String name = Channel.BOOKINGCOM.getName(); // Returns "Booking.com"
String code = Channel.BOOKINGCOM.getStringValue(); // Returns "BKG"

// Check if channel supports product-level commission
Set<Channel> commissionChannels = Channel.getChannelsSupportedChannelCommissionOnProductLevel();
boolean supported = commissionChannels.contains(Channel.AIRBNB);

// Convert abbreviation list to names
List<String> abbs = Arrays.asList("BKG", "ABB", "EXP");
List<String> names = Channel.getByAbb(abbs);
```

### 4. TypeOfCharge Enum

Defines types of charge adjustments (decreases only).

```java
public enum TypeOfCharge implements Valued {
    DECREASE_PERCENT("Decrease Percent"), 
    DECREASE_AMOUNT("Decrease Amount");
}
```

### 5. YieldsTypeOfCharge Enum

Extended charge types including both increases and decreases for yield management.

```java
public enum YieldsTypeOfCharge implements Valued {
    DECREASE_PERCENT("Decrease Percent"), 
    DECREASE_AMOUNT("Decrease Amount"), 
    INCREASE_PERCENT("Increase Percent"), 
    INCREASE_AMOUNT("Increase Amount");
}

// Get all charge types
Set<YieldsTypeOfCharge> types = YieldsTypeOfCharge.getTypeValues();
```

### 6. CreatedPropertyStatusEnum

Defines the lifecycle states of property creation process.

```java
public enum CreatedPropertyStatusEnum implements Valued {
    NEW(0),           // Property just created
    IN_PROGRESS(1),    // Property being configured
    IMPORTED(2);       // Property successfully imported
}
```

**Business Logic:**
- Properties transition from NEW → IN_PROGRESS → IMPORTED
- Integer values used for database storage

### 7. ChannelNotificationEnum

Defines webhook endpoint paths for channel notifications. This enum maps notification types to their corresponding API endpoints.

```java
public enum ChannelNotificationEnum implements Valued {
    PRODUCT_ACTIVATION("/webmessages/multiunit/activate/"),
    PRODUCT_CREATE("/webmessages/multiunit/create/"),
    PRODUCT_UPDATE("/webmessages/multiunit/update/"),
    PRODUCT_DEACTIVATION("/webmessages/multiunit/deactivate/"),
    PRODUCT_PHOTO_CREATE("/webmessages/multiunit/photos/create/"),
    PRODUCT_PHOTO_UPDATE("/webmessages/multiunit/photos/update/"),
    CALENDAR_UPDATE("/webmessages/multiunit/calendar/update/"),
    YIELD_UPDATE("/webmessages/multiunit/yields/update/"),
    YIELD_PROMOTION_BOOKING_CREATE("/webmessages/bookingpromotion/create/v2/"),
    YIELD_PROMOTION_BOOKING_UPDATE("/webmessages/bookingpromotion/update/v2/"),
    YIELD_PROMOTION_BOOKING_ACTIVATE("/webmessages/bookingpromotion/activate/v2/"),
    YIELD_PROMOTION_BOOKING_INACTIVE("/webmessages/bookingpromotion/inactivate/v2/"),
    FEE_UPDATE("/webmessages/multiunit/fees/update/"),
    TAX_UPDATE("/webmessages/multiunit/taxes/update/"),
    RATE_PLAN("/webmessages/rateplan/product/{productId}/channel/{channelId}/rateplan/{ratePlanId}"),
    RESTRICTION_UPDATE("/webmessages/restriction/update/version/"),
    CHANNEL_CANCELLATION_CREATE("/webmessages/cancellation/channelId/"),
    LINKED_PRODUCT_AVAILABILITY_CALENDAR("/webmessages/multiunitkeytorep/availabilitycalendar/create/productid/"),
    // Airbnb-specific endpoints with parameterized paths
    YIELD_PROMOTION_AIRBNB_CREATE("/webmessages/airbnb/promo/create/productId/%d/supplierId/%d/channelId/%d/yieldIds/%s/environment/%s"),
    YIELD_PROMOTION_AIRBNB_DELETE("/webmessages/airbnb/promo/delete/productId/%d/supplierId/%d/channelId/%d/yieldIds/%s/environment/%s"),
    // Generic channel v2 endpoints
    CHANNEL_FEE_TAX("/webmessages/channel/feetax/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_ACTIVATION_DEACTIVATION("/webmessages/channel/activationdeactivation/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_CREATE_OR_UPDATE_LISTING("/webmessages/channel/createorupdatelisting/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_STATIC_DATA("/webmessages/channel/updatestaticdata/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_CREATE_OR_UPDATE_IMAGE("/webmessages/channel/createorupdateimage/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_DELETE_LISTING("/webmessages/channel/deletelisting/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_MAX_PERSON("/webmessages/channel/maxperson/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_RESTRICTION("/webmessages/channel/restriction/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_RESERVATION("/webmessages/channel/reservation/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_RATE("/webmessages/channel/rate/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_CALENDAR("/webmessages/channel/calendar/supplierId/%d/version/%s/channelId/%d"),
    CHANNEL_RATE_UPDATE("/webmessages/rate/update/"),
    COMMISSION_ON_PRODUCT_LEVEL("/webmessages/property/update/channel-specific-rates-and-availability"),
    ACTIVATION_DEACTIVATION("/webmessages/activationdeactivation/productId/%d"),
    CHANNEL_SPECIFIC_TAX("/webmessages/property/update/channel-specific-tax"),
    CHANNEL_DISCOUNT_CODE("/webmessages/channel/discount/discountCode/%s/channelId/%d");
}
```

**Important Notes:**
- Parameterized endpoints use `%d` for integers and `%s` for strings
- `getChannelNotification()` returns the set of v2 channel-specific endpoints

#### Legacy Endpoints

The enum includes some legacy endpoints that may no longer be in active use:

- `FEE_UPATE("/webmessages/bookingpromo/update")` - Contains a typo in the enum constant name ("UPATE" instead of "UPDATE"). This appears to be a legacy endpoint that may be deprecated. The typo is preserved in the source code and should be used exactly as written if referenced.
- `FEE_NET_RATE("/webmessages/rate/update/")` - Appears to be a legacy rate update endpoint

### 8. ChannelNotificationType

Types of notification operations.

```java
public enum ChannelNotificationType implements Valued {
    UPDATE("Update"),
    DELETE("delete"),
    CREATE("Create");
}
```

### 9. PriceType Enum

Defines price synchronization types.

```java
public enum PriceType implements Valued {
    LOCAL(0),   // Local/cached price
    LIVE(1);    // Live/fetch from source price
}
```

### 10. EntityType Enum

Defines various entity types used throughout the system.

```java
public enum EntityType implements Valued {
    RATE_PLAN("Rate Plan"),
    PRICE("Price"),
    RESTRICTION("Restriction"),
    CANCELLATION_RULE("Cancellation rule"),
    RATE_ITEMS("Rate plan items"),
    PRODUCT("Product"),
    RESERVATION("Reservation"),
    TAX("Tax"),
    FEE("Fee"),
    YIELD("Yield"),
    COMMISSION("Commission"),
    INFO("Info"),
    PROCESS("Process");
}
```

### 11. AttributeDisplayCategory Enum

Categories for organizing property attributes in the UI.

```java
public enum AttributeDisplayCategory {
    ACTIVITIES("Activities"),
    OUTDOOR_VIEW("Outdoor & view"),
    FOOD_DRINK("Food and Drink"),
    SHOPS("Shops"),
    SERVICES_EXTRAS("Services & extras"),
    POOL_SPA("Pool and Spa"),
    TRANSPORTATION("Transportation"),
    FRONT_DESK("Front Desk Services"),
    MISCELLANEOUS("Miscellaneous"),
    ROOM("Room amenities"),
    COMMON_AREAS("Common areas"),
    ENTARTAIMENT_FAMILY("Entertainment and Family Services"),
    CLEANING("Cleaning Services"),
    BUSINESS("Business Facilities"),
    ACCESSIBILITY("Accessibility"),
    BATHROOM("Bathroom"),
    MEDIA("Media & technology"),
    POLICY("Policy"),
    PROPERTY_TYPE("Property Type"),
    BED_TYPE("Bed Type"),
    ROOM_TYPE("Room type"),
    KEY_COLLECTION("Key Collection");
}
```

#### Getter Method

The `AttributeDisplayCategory` enum provides a getter for its string value:

```java
public String getValue() {
    return value;
}
```

**Usage Example:**
```java
String category = AttributeDisplayCategory.POOL_SPA.getValue();
// Returns "Pool and Spa"
```

### 12. PendingPayoutStatus Enum

Statuses for pending payout processing.

```java
public enum PendingPayoutStatus implements Valued {
    INITIAL(1, "Initial"),
    PENDING(2, "Pending"),
    APPROVED(3, "Approved"),
    CANCELLED(4, "Cancelled"),
    NOT_RECONCILED(5, "Not reconciled"),
    NOT_SHOW(6, "Not show"),
    ALREADY_APPROVED(7, "Already approved");
}
```

#### getTypeValues() Method

Returns a complete set of all pending payout status values:

```java
public static Set<PendingPayoutStatus> getTypeValues() {
    return EnumSet.of(INITIAL, PENDING, APPROVED, CANCELLED, NOT_RECONCILED, NOT_SHOW, ALREADY_APPROVED);
}
```

**Usage Example:**
```java
Set<PendingPayoutStatus> allStatuses = PendingPayoutStatus.getTypeValues();
// Returns: [INITIAL, PENDING, APPROVED, CANCELLED, NOT_RECONCILED, NOT_SHOW, ALREADY_APPROVED]

// Check if a status is valid
boolean isValid = PendingPayoutStatus.getTypeValues().contains(status);
```

### 13. BestStayz-Specific Enums

Several enums are specific to the BestStayz brand/platform:

#### BestStayzMessagingStatus

```java
public enum BestStayzMessagingStatus implements Valued {
    NEW(1, "New"),
    VIEWED(2, "Viewed"),
    ASSIGNED(4, "Assigned"),
    REPLIED(3, "Replied"),
    FORWARDED(5, "Forwarded"),
    UNASSIGNED(6, "Unassigned");
}
```

**Business Rules:**
- Messages flow through NEW → VIEWED → ASSIGNED → REPLIED
- FORWARDED and UNASSIGNED are alternate states
- Integer values are used for database storage

#### getTypeValues() Method

Returns all messaging status values:

```java
public static Set<BestStayzMessagingStatus> getTypeValues() {
    return EnumSet.of(NEW, VIEWED, ASSIGNED, REPLIED, FORWARDED, UNASSIGNED);
}
```

**Usage Example:**
```java
Set<BestStayzMessagingStatus> allStatuses = BestStayzMessagingStatus.getTypeValues();

// Iterate through all statuses
for (BestStayzMessagingStatus status : allStatuses) {
    System.out.println(status.getValue() + ": " + status.getStringValue());
}
```

#### BestStayzHomeownerDocument

```java
public enum BestStayzHomeownerDocument implements Valued {
    DRIVER_LICENSE(1),
    IDENTIFICATION_CARD(2);
}
```

#### getTypeValues() Method

Returns all supported document types:

```java
public static Set<BestStayzHomeownerDocument> getTypeValues() {
    return EnumSet.of(DRIVER_LICENSE, IDENTIFICATION_CARD);
}
```

**Usage Example:**
```java
Set<BestStayzHomeownerDocument> docTypes = BestStayzHomeownerDocument.getTypeValues();
// Returns: [DRIVER_LICENSE, IDENTIFICATION_CARD]
```

#### BestStayzHomeownerVerifyStatus

```java
public enum BestStayzHomeownerVerifyStatus implements Valued {
    PENDING(1, "Pending verification"),
    APPROVED(2, "Reviewed - Approved"),
    REJECTED(3, "Reviewed - Rejected");
}
```

#### getTypeValues() Method

Returns all verification status values:

```java
public static Set<BestStayzHomeownerVerifyStatus> getTypeValues() {
    return EnumSet.of(PENDING, APPROVED, REJECTED);
}
```

**Usage Example:**
```java
Set<BestStayzHomeownerVerifyStatus> statuses = BestStayzHomeownerVerifyStatus.getTypeValues();
boolean isApproved = statuses.contains(BestStayzHomeownerVerifyStatus.APPROVED);
```

#### BestStayzHomeownerAgent

```java
public enum BestStayzHomeownerAgent implements Valued {
    ONBOARDING_PERSON("OnboardingPerson"),
    ACCOUNT_MANAGER("AccountManager"),
    REGIONAL_MANAGER("RegionalManager"),
    SALES_REP("SalesRep");
}
```

#### BestStayzHomeownerStep

```java
public enum BestStayzHomeownerStep implements Valued {
    PRODUCT_CREATION("1"),
    TERMS_AND_CONDITIONS("2"),
    EMAIL_CONFIRMATION("3"),
    ALL("all");
}
```

### 14. ChannelProductSettingsType Enum

Settings types for channel product configuration.

```java
public enum ChannelProductSettingsType implements Valued {
    PASS_THROUGH_TAXES_COLLECTION_TYPE(1),
    PM_CONFIRMATION_TO_USE_NEW_TAX_API(2);
}
```

#### getTypeValues() Method

Returns all channel product settings types:

```java
public static Set<ChannelProductSettingsType> getTypeValues() {
    return EnumSet.of(PASS_THROUGH_TAXES_COLLECTION_TYPE, PM_CONFIRMATION_TO_USE_NEW_TAX_API);
}
```

**Usage Example:**
```java
Set<ChannelProductSettingsType> settings = ChannelProductSettingsType.getTypeValues();
// Returns: [PASS_THROUGH_TAXES_COLLECTION_TYPE, PM_CONFIRMATION_TO_USE_NEW_TAX_API]

// Check if a setting type exists
boolean exists = settings.contains(ChannelProductSettingsType.PM_CONFIRMATION_TO_USE_NEW_TAX_API);
```

### 15. ChannelAffiliateStatus Enum

Status of channel affiliate relationships.

```java
public enum ChannelAffiliateStatus implements Valued {
    CREATED(1, "Created"),
    CANCELLED(2, "Cancelled");
}
```

#### getTypeValues() Method

Returns all affiliate status values:

```java
public static Set<ChannelAffiliateStatus> getTypeValues() {
    return EnumSet.of(CREATED, CANCELLED);
}
```

**Usage Example:**
```java
Set<ChannelAffiliateStatus> statuses = ChannelAffiliateStatus.getTypeValues();
// Returns: [CREATED, CANCELLED]
```

### 16. FailedPaymentSupportLetterType Enum

Types of support letters for failed payments.

```java
public enum FailedPaymentSupportLetterType implements Valued {
    BALANCE_PAYMENT("balancePayment"),
    CANCELLED_RESERVATION("cancelledReservation"),
    ACCEPTED_PAYMENT("acceptedPayment");
}
```

### 17. PaymentMethodType Enum

Payment methods supported for payouts.

```java
public enum PaymentMethodType implements Valued {
    MAIL(1, "mail"),
    PAYPAL(2, "paypal"),
    BANK(3, "bank"),
    WIRE(4, "wire");
}
```

#### getTypeValues() Method

Returns all supported payment method types:

```java
public static Set<PaymentMethodType> getTypeValues() {
    return EnumSet.of(PAYPAL, BANK, WIRE, MAIL);
}
```

**Usage Example:**
```java
Set<PaymentMethodType> paymentMethods = PaymentMethodType.getTypeValues();

// Check if a payment method is supported
boolean isSupported = paymentMethods.contains(PaymentMethodType.PAYPAL);

// Iterate through all payment methods
for (PaymentMethodType method : paymentMethods) {
    System.out.println(method.getStringValue());
}
```

### 18. Tax-Related Enums

#### PMConfirmationToUseTaxEligibility

```java
public enum PMConfirmationToUseTaxEligibility implements Valued {
    NOT_CONFIRMED(0),
    CONFIRMED(1);
}
```

#### getTypeValues() Method

Returns all tax eligibility confirmation values:

```java
public static Set<PMConfirmationToUseTaxEligibility> getTypeValues() {
    return EnumSet.of(NOT_CONFIRMED, CONFIRMED);
}
```

**Usage Example:**
```java
Set<PMConfirmationToUseTaxEligibility> values = PMConfirmationToUseTaxEligibility.getTypeValues();
// Returns: [NOT_CONFIRMED, CONFIRMED]
```

#### AirbnbTaxEligibilityLevel

```java
public enum AirbnbTaxEligibilityLevel implements Valued {
    INELIGIBLE("INELIGIBLE", 1),
    NO_AIRBNB_COLLECTED_TAX("NO_AIRBNB_COLLECTED_TAX", 2),
    OVERRIDE_AIRBNB_COLLECTED_TAX("OVERRIDE_AIRBNB_COLLECTED_TAX", 3),
    STACKED_AIRBNB_COLLECTED_TAX("STACKED_AIRBNB_COLLECTED_TAX", 4);
}
```

**Business Rules:**
- Each level represents a different tax collection behavior with Airbnb
- `INELIGIBLE`: Property cannot collect taxes through Airbnb
- `NO_AIRBNB_COLLECTED_TAX`: Airbnb does not collect taxes for this property
- `OVERRIDE_AIRBNB_COLLECTED_TAX`: Override Airbnb's tax collection
- `STACKED_AIRBNB_COLLECTED_TAX`: Stack taxes on top of Airbnb's collection

#### getTypeValues() Method

Returns all Airbnb tax eligibility levels:

```java
public static Set<AirbnbTaxEligibilityLevel> getTypeValues() {
    return EnumSet.of(INELIGIBLE, NO_AIRBNB_COLLECTED_TAX, OVERRIDE_AIRBNB_COLLECTED_TAX, STACKED_AIRBNB_COLLECTED_TAX);
}
```

**Usage Example:**
```java
Set<AirbnbTaxEligibilityLevel> levels = AirbnbTaxEligibilityLevel.getTypeValues();

// Check all tax levels
for (AirbnbTaxEligibilityLevel level : levels) {
    System.out.println(level.getValue() + ": " + level.getStringValue());
}

// Validate a tax level
boolean isValid = AirbnbTaxEligibilityLevel.getTypeValues().contains(taxLevel);
```

### 19. ZendeskCustomFieldEnum Enum

Custom field IDs for Zendesk integration.

```java
public enum ZendeskCustomFieldEnum implements Valued {
    PM_ID("25496826", "PM ID"),
    PROPERTY_ID("25496846", "Property ID"),
    MOR("360011104471", "MOR");
}
```

### 20. ProductBedroomTypes Enum

Types of bedrooms in a property.

```java
public enum ProductBedroomTypes implements Valued {
    BEDROOM("Bedroom"),
    LIVING_ROOM("Living Room");
}
```

### 21. User Notification Enums

#### EntityTypeUserNotification

```java
public enum EntityTypeUserNotification implements Valued {
    RESERVATION(1, "reservation"),
    PRODUCT(2, "product");
}
```

#### MessageUserNotification

```java
public enum MessageUserNotification implements Valued {
    NEW_RESERVATION("New %s reservation of %s for %s - %s from %s."),
    MODIFIED_RESERVATION("Reservation %s for %s was modified."),
    CANCELLED_RESERVATION("Reservation %s for %s was cancelled."),
    PRODUCT_STATUS_CHANGED("Product %s state was changed from %s -> %s. Reason: %s");
}
```

### 22. ProductState Enum

Lifecycle states for products.

```java
public enum ProductState implements Valued {
    INITIAL("Initial"),
    ON_HOLD("OnHold"),
    INCOMPLETE("Incomplete"),
    COMPLETE("Complete"),
    DISTRIBUTED("Distributed"),
    ARCHIVED("Archived"),
    INREVIEW("InReview");
}
```

### 23. ReservationImportType Enum

Methods for importing reservations.

```java
public enum ReservationImportType implements Valued {
    Link(1, "Link"),
    File(2, "File");
}
```

### 24. LogEmailEntityIdEnum Enum

Entity types for email logging (does not implement Valued).

```java
public enum LogEmailEntityIdEnum {
    Reservation(1, "Reservation"),
    GroupReservation(2, "Group reservation");

    public Integer getValue() { return this.value; }
    public String getName() { return this.name; }
    public static LogEmailEntityIdEnum getByInt(Integer value) { ... }
}
```

### 25. HomeownerPhotoType Enum

Types of homeowner photos.

```java
public enum HomeownerPhotoType implements Valued {
    ORIGINAL(1, "Original"),
    TEMPORARY(2, "Temporary");
}
```

#### getTypeValues() Method

Returns all homeowner photo types:

```java
public static Set<HomeownerPhotoType> getTypeValues() {
    return EnumSet.of(ORIGINAL, TEMPORARY);
}
```

**Usage Example:**
```java
Set<HomeownerPhotoType> photoTypes = HomeownerPhotoType.getTypeValues();
// Returns: [ORIGINAL, TEMPORARY]

// Validate photo type
boolean isValid = HomeownerPhotoType.getTypeValues().contains(photoType);
```

### 26. ResidencyCategoryEnum Enum

Categories for property residency (does not implement Valued).

```java
public enum ResidencyCategoryEnum {
    PRIMARY_RESIDENCE(0, "primary_residence"),
    SECONDARY_RESIDENCE(1, "secondary_residence"),
    NON_RESIDENTIAL(2, "non_residential");

    public Integer getId() { return this.id; }
    public String getStringValue() { return this.name; }
}
```

#### getTypeValues() Method

Returns all residency categories:

```java
public static Set<ResidencyCategoryEnum> getTypeValues() {
    return EnumSet.of(PRIMARY_RESIDENCE, SECONDARY_RESIDENCE, NON_RESIDENTIAL);
}
```

#### getByString() Method

Looks up a residency category by its string value:

```java
public static ResidencyCategoryEnum getByString(String value) {
    return Arrays.stream(ResidencyCategoryEnum.values())
            .filter(residencyCategoryEnum -> residencyCategoryEnum.getStringValue() != null && residencyCategoryEnum.getStringValue().equals(value))
            .findFirst().orElse(null);
}
```

**Usage Example:**
```java
ResidencyCategoryEnum category = ResidencyCategoryEnum.getByString("secondary_residence");
// Returns: SECONDARY_RESIDENCE

// Invalid value returns null
ResidencyCategoryEnum invalid = ResidencyCategoryEnum.getByString("invalid_value");
// Returns: null
```

#### getResidencycategoryById() Method

Looks up a residency category by its integer ID:

```java
public static ResidencyCategoryEnum getResidencycategoryById(Integer id) {
    return Arrays.stream(ResidencyCategoryEnum.values())
            .filter(residencyCategoryEnum -> residencyCategoryEnum.getId() != null && residencyCategoryEnum.getId().equals(id))
            .findFirst().orElse(null);
}
```

**Usage Example:**
```java
ResidencyCategoryEnum category = ResidencyCategoryEnum.getResidencycategoryById(1);
// Returns: SECONDARY_RESIDENCE

// Invalid ID returns null
ResidencyCategoryEnum invalid = ResidencyCategoryEnum.getResidencycategoryById(99);
// Returns: null
```

### 27. PostalAddressPart Enum

Components of postal addresses (does not implement Valued).

```java
public enum PostalAddressPart {
    City("city"),
    Address("address"),
    State("state");

    public String getName() { return name; }
}
```

### 28. PortalType Enum

Types of system portals (does not implement Valued).

```java
public enum PortalType {
    MARRIOTT(0),
    PM_PORTAL(1),
    CHANNEL_PORTAL(2),
    REV_PAL(5),
    ADMIN(6),
    SUPPLIER_API(7);

    public Integer getId() { return id; }
}
```

### 29. PromotionTargetChannel Enum

Target channels for promotions, including geographic POS (Point of Sale) locations (does not implement Valued).

```java
public enum PromotionTargetChannel {
    ALGERIA_POS(1, "algeria_pos"),
    ARGENTINA_POS(2, "argentina_pos"),
    AUSTRALIA_POS(3, "australia_pos"),
    BELARUS_POS(4, "belarus_pos"),
    BRAZIL_POS(5, "brazil_pos"),
    CANADA_POS(6, "canada_pos"),
    CHILE_POS(7, "chile_pos"),
    CHINA_POS(8, "china_pos"),
    COLOMBIA_POS(9, "colombia_pos"),
    DOMESTIC_POS(10, "domestic_pos"),
    EU_POS(11, "eu_pos"),
    HONG_CONG_POS(12, "hong_kong_pos"),
    INDIA_POS(13, "india_pos"),
    INDONESIA_POS(14, "indonesia_pos"),
    INTERNATIONAL_POS(15, "international_pos"),
    IRAN_POS(16, "iran_pos"),
    ISRAEL_POS(17, "israel_pos"),
    JAPAN_POS(18, "japan_pos"),
    KAZAKHSTAN_POS(19, "kazakhstan_pos"),
    KUWAIT_POS(20, "kuwait_pos"),
    MALAYSIA_POS(21, "malaysia_pos"),
    MEXICO_POS(22, "mexico_pos"),
    NEW_ZEALAND_POS(23, "new_zealand_pos"),
    OMAN_POS(24, "oman_pos"),
    PAKISTAN_POS(25, "pakistan_pos"),
    PERU_POS(26, "peru_pos"),
    PHILIPPINES_POS(27, "philippines_pos"),
    QATAR_POS(28, "qatar_pos"),
    RUSSIA_POS(29, "russia_pos"),
    SAUDI_ARABIA_POS(30, "saudi_arabia_pos"),
    SINGAPORE_POS(31, "singapore_pos"),
    SOUTH_AFRICA_POS(32, "south_africa_pos"),
    SOUTH_KOREA_POS(33, "south_korea_pos"),
    SWITZERLAND_POS(34, "switzerland_pos"),
    TAIWAN_POS(35, "taiwan_pos"),
    THAILAND_POS(36, "thailand_pos"),
    TRINIDAD_TOBAGO_POS(37, "trinidad_&_tobago_pos"),
    TURKEY_POS(38, "turkey_pos"),
    UKRAINE_POS(39, "ukraine_pos"),
    UNITED_ARAB_EMIRATES_POS(40, "united_arab_emirates_pos"),
    UNITED_STATES_POS(41, "united_states_pos"),
    VIETNAM_POS(42, "vietnam_pos"),
    APP(43, "app"),
    ALL(44, "all");

    public Integer getId() { return id; }
    public String getName() { return name; }
}
```

#### Getter Methods

The `PromotionTargetChannel` enum provides two getter methods:

```java
public Integer getId() {
    return id;
}

public String getName() {
    return name;
}
```

**Usage Example:**
```java
PromotionTargetChannel channel = PromotionTargetChannel.UNITED_STATES_POS;
int id = channel.getId();        // Returns: 41
String name = channel.getName(); // Returns: "united_states_pos"
```

#### Lookup Methods

```java
public static PromotionTargetChannel getById(Integer id) {
    return Arrays.stream(PromotionTargetChannel.values())
            .filter(targetChannel -> targetChannel.getId().equals(id))
            .findFirst().orElse(null);
}

public static PromotionTargetChannel getByName(String name) {
    return Arrays.stream(PromotionTargetChannel.values())
            .filter(targetChannel -> targetChannel.getName().equals(name))
            .findFirst().orElse(null);
}
```

**Usage Example:**
```java
// Lookup by ID
PromotionTargetChannel channel = PromotionTargetChannel.getById(41);
// Returns: UNITED_STATES_POS

// Lookup by name
PromotionTargetChannel channel = PromotionTargetChannel.getByName("united_states_pos");
// Returns: UNITED_STATES_POS

// Invalid values return null
PromotionTargetChannel invalid = PromotionTargetChannel.getById(99);
// Returns: null
```

**Geographic Coverage:** 40+ countries supported as POS targets.

### 30. ReservationLogActivity Enum

Types of reservation activities for logging (does not implement Valued).

```java
public enum ReservationLogActivity {
    CREATE("Creation"),
    MODIFY("Modification"),
    PAYMENT_PROCESS("PaymentProcess"),
    CANCEL("Cancellation");

    public String getName() { return name; }
}
```

## Language Class

The `Language` class provides language code utilities and translation support.

### Language Code Enum

```java
public enum Code { de, en, es, fr, ru, tr, nl, pl, it }
```

### Language Constants

```java
public static final String DE = "DE";
public static final String EN = "EN";
public static final String ES = "ES";
public static final String FR = "FR";
public static final String RU = "RU";
public static final String TR = "TR";
public static final String NL = "NL";
public static final String PL = "PL";
public static final String IT = "IT";
public static final String PT = "PT";
public static final String FI = "FI";
```

### Translatable Languages

The class maintains an array of translatable languages:

```java
private static final NameId[] translatable = {
    new NameId("English", "EN"),
    new NameId("Bulgarian", "BG"),
    new NameId("Catalan", "CA"),
    new NameId("Czech", "CS"),
    new NameId("Danish", "DA"),
    new NameId("German", "DE"),
    new NameId("Greek", "EL"),
    new NameId("Spanish", "ES"),
    new NameId("Finnish", "FI"),
    new NameId("French", "FR"),
    new NameId("Hindi", "HI"),
    new NameId("Croatian", "HR"),
    new NameId("Hungarian", "HU"),
    new NameId("Indonesian", "IN"),
    new NameId("Italian", "IT"),
    new NameId("Japanese", "JA"),
    new NameId("Korean", "KO"),
    new NameId("Lithuanian", "LT"),
    new NameId("Latvian", "LV"),
    new NameId("Dutch", "NL"),
    new NameId("Norwegian", "NO"),
    new NameId("Polish", "PL"),
    new NameId("Portuguese", "PT"),
    new NameId("Romanian", "RO"),
    new NameId("Russian", "RU"),
    new NameId("Slovak", "SK"),
    new NameId("Slovenian", "SL"),
    new NameId("Serbian", "SR"),
    new NameId("Swedish", "SV"),
    new NameId("Thai", "TH"),
    new NameId("Turkish", "TR"),
    new NameId("Vietnamese", "VI"),
    new NameId("Chinese", "ZH")
};
```

**Business Rule:** English is not considered a translatable language (it's the base language).

### Language Utility Methods

#### `isTranslatable(String code)`
Checks if a language code is translatable (not English).

```java
public static boolean isTranslatable(String code) {
    if (EN.equalsIgnoreCase(code)) {
        return false;
    }
    for (NameId nameId : translatable) {
        if (nameId.getId().equalsIgnoreCase(code)) {
            return true;
        }
    }
    return false;
}
```

**Usage:**
```java
boolean canTranslate = Language.isTranslatable("DE");  // true
boolean canTranslate = Language.isTranslatable("EN");  // false
```

#### `getLanguage(String code)`
Retrieves a `NameId` object for a language code. Returns English as default if not found.

```java
public static NameId getLanguage(String code) {
    for (NameId nameId : translatable) {
        if (nameId.getId().equalsIgnoreCase(code)) {
            return nameId;
        }
    }
    return translatable[0]; // Returns English
}
```

**Usage:**
```java
NameId language = Language.getLanguage("DE");
// language.getId() = "DE"
// language.getName() = "German"
```

## Business Rules and Patterns

### 1. Enum Value Pattern

Most enums in this domain follow the `Valued` interface pattern:
- **Integer Value**: Used for database storage (compact, efficient)
- **String Value**: Used for API communication and display (human-readable)
- **Name**: Used for internal reference (Java enum constant)

**Example:**
```java
public enum PriceType implements Valued {
    LOCAL(0),   // getValue() returns 0, getStringValue() is not used
    LIVE(1);    // getValue() returns 1, getStringValue() is not used
}
```

### 2. getTypeValues() Pattern

Many enums provide a `getTypeValues()` static method that returns a `Set` of all enum values:

```java
public static Set<EnumType> getTypeValues() {
    return EnumSet.of(VALUE1, VALUE2, VALUE3);
}
```

**Benefits:**
- Provides a consistent way to iterate over all valid values
- Enables validation by checking membership in the set
- Supports dropdown population in UI components

**Enums with getTypeValues():**
- YieldsTypeOfCharge
- PendingPayoutStatus
- BestStayzMessagingStatus
- BestStayzHomeownerDocument
- ChannelProductSettingsType
- BestStayzHomeownerVerifyStatus
- ChannelAffiliateStatus
- PaymentMethodType
- PMConfirmationToUseTaxEligibility
- AirbnbTaxEligibilityLevel
- HomeownerPhotoType
- ResidencyCategoryEnum

### 3. Categorization Methods

Many enums provide static methods that return subsets of enum values based on business rules:

```java
// Get specific categories
Set<YieldType> promotions = YieldType.getPromotions();
Set<Channel> commissionChannels = Channel.getChannelsSupportedChannelCommissionOnProductLevel();
```

### 4. Type-Safe Conversion

Utility methods ensure type-safe enum conversion:

```java
// Safe conversion with exceptions for invalid values
Channel channel = BookingPalEnums.getValuedEnum(Channel.class, "ABB");

// Null-safe conversion (returns null instead of throwing exception)
Channel unknown = BookingPalEnums.getValuedEnumNullSafe(Channel.class, "INVALID");
```

### 5. Internationalization Support

The `Language` class enables translation features:
- 30+ languages supported
- English treated as base language (not translatable)
- Case-insensitive language code matching

### 6. Channel-Specific Features

The `Channel` enum encodes business rules about channel capabilities:
- Commission support at product level
- Tax collection types
- Display name customization

## Integration Points

### Database Integration

Enums using `Valued` interface with integer values map directly to database columns:

```sql
CREATE TABLE reservations (
    id INT PRIMARY KEY,
    payment_method_type INT,  -- Maps to PaymentMethodType.getValue()
    status INT
);
```

### API Integration

String values are used in JSON APIs:

```json
{
  "channel": "ABB",
  "yieldType": "Early Booking Deal"
}
```

### Notification System

`ChannelNotificationEnum` provides webhook endpoints for real-time updates:

```java
String endpoint = ChannelNotificationEnum.PRODUCT_UPDATE.getStringValue();
// "/webmessages/multiunit/update/"
```

## Best Practices

### 1. Always Use Utility Methods

Instead of direct enum iteration, use provided categorization methods:

```java
// Good
Set<YieldType> promotions = YieldType.getPromotions();

// Avoid manual iteration
Set<YieldType> promotions = EnumSet.noneOf(YieldType.class);
for (YieldType type : YieldType.values()) {
    if (isPromotion(type)) {
        promotions.add(type);
    }
}
```

### 2. Use getTypeValues() for Validation

When validating enum values:

```java
// Good - use getTypeValues()
Set<PaymentMethodType> validMethods = PaymentMethodType.getTypeValues();
boolean isValid = validMethods.contains(inputMethod);

// Better - use null-safe lookup
PaymentMethodType method = BookingPalEnums.getValuedEnumNullSafe(PaymentMethodType.class, intValue);
```

### 3. Use Null-Safe Methods for Optional Values

When dealing with user input or external data:

```java
// Safe for external input
Channel channel = BookingPalEnums.getValuedEnumNullSafe(Channel.class, inputCode);
if (channel != null) {
    // Process channel
}
```

### 4. Leverage Language Utilities

For translation features:

```java
if (Language.isTranslatable(languageCode)) {
    NameId lang = Language.getLanguage(languageCode);
    // Trigger translation workflow
}
```

### 5. Check Channel Capabilities

Before performing channel-specific operations:

```java
Set<Channel> taxChannels = Channel.getSupportedChannelSpecificTax();
if (taxChannels.contains(channel)) {
    // Apply channel-specific tax logic
}
```

### 6. Handle Lookup Methods Correctly

When using `getByString()` or `getById()` methods:

```java
// Always check for null
ResidencyCategoryEnum category = ResidencyCategoryEnum.getByString(code);
if (category != null) {
    // Process valid category
} else {
    // Handle invalid code
}
```

## Migration Notes

### Adding New Enums

When adding new business enums:
1. Implement the `Valued` interface (if applicable)
2. Provide both integer and string values (if applicable)
3. Add `getTypeValues()` method if the enum needs a complete value set
4. Add utility methods for categorization (if needed)
5. Update this documentation

### Modifying Existing Enums

- **Never** change integer values (breaks database compatibility)
- **Never** remove enum constants (use deprecation instead)
- **Caution** when changing string values (affects API contracts)
- When adding new enum values, ensure they are included in `getTypeValues()` if the method exists

## Summary

The `business-enums` domain provides:
- **30+ enumerations** covering all major business concepts
- **Utility methods** for type-safe conversion and categorization
- **getTypeValues() pattern** for consistent value retrieval and validation
- **Internationalization support** for 30+ languages
- **Channel management** for 50+ distribution channels
- **Notification endpoints** for real-time system updates
- **Tax and payment** configuration enums
- **Lifecycle management** for products and reservations
- **Comprehensive lookup methods** for enums like ResidencyCategoryEnum and PromotionTargetChannel

This domain serves as the foundation for business logic across the BookingPal platform, ensuring consistency, type safety, and maintainability throughout the distributed system.

---

*Generated: 2025-01-09T12:30:00Z*
*Module: mbp-utils*
*Domain: business-enums*
*Status: draft*