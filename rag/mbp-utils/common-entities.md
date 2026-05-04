---
module: mbp-utils
domain: common-entities
generated_at: 2024-01-01T00:00:00Z
status: approved
review_score: 0.85
attempts: 1
---

# Common Entities Domain Documentation

This document provides comprehensive technical documentation for the `common-entities` domain within the `mbp-utils` module. This domain contains fundamental data structures and utility classes used throughout the MyBookingPal enterprise system for handling parameters, time calculations, identifiers, and monetary values.

## Overview

The `common-entities` domain consists of nine core classes that serve as foundational building blocks for the application:

| Class | Type | Purpose |
|-------|------|---------|
| `Parameter` | POJO | Encapsulates query and filter parameters |
| `Time` | Enum | Time unit enumeration with utility methods |
| `IdVersion` | POJO | Identifier with version tracking |
| `IdName` | POJO | Simple identifier with name (Integer ID) |
| `NameId` | POJO | Simple identifier with name (String ID) |
| `NameIdAction` | POJO | Extended NameId with pagination and filtering |
| `NameStateId` | POJO | Identifier with name and state, includes Builder |
| `BigDecimalExt` | Class | Extended BigDecimal for financial calculations |
| `Unit` | Class | Measurement unit definitions extending NameId |

---

## Class Documentation

### 1. Parameter

**Package:** `com.mybookingpal.utils.entity`

The `Parameter` class encapsulates common parameters used for querying and filtering data across the system. It serves as a generic parameter holder for various service operations.

#### Fields

| Field | Type | Description | Access |
|-------|------|-------------|--------|
| `organizationId` | `String` | Organization identifier | Private |
| `model` | `String` | Model name/type | Private |
| `id` | `String` | Entity identifier | Private |
| `type` | `String` | Entity type | Private |
| `fromDate` | `String` | Start date for range queries | Private |
| `toDate` | `String` | End date for range queries | Private |
| `currency` | `String` | Currency code | Private |

#### Methods

**Standard Getters/Setters (Active):**

```java
public String getId()
public void setId(String id)
public String getType()
public void setType(String type)
public String getCurrency()
public void setCurrency(String currency)
```

**Deprecated Methods:**

> **Note:** The following methods are marked as `@Deprecated` and should be avoided in new code:

```java
@Deprecated
public String getOrganizationid()
@Deprecated
public void setOrganizationid(String organizationid)
@Deprecated
public String getModel()
@Deprecated
public void setModel(String model)
@Deprecated
public String getFromdate()
@Deprecated
public void setFromdate(String fromdate)
@Deprecated
public String getTodate()
@Deprecated
public void setTodate(String todate)
```

**toString():**

```java
@Override
public String toString() {
    StringBuilder builder = new StringBuilder();
    builder.append("Parameter [organizationid=");
    builder.append(organizationId);
    builder.append(", model=");
    builder.append(model);
    builder.append(", id=");
    builder.append(id);
    builder.append(", type=");
    builder.append(type);
    builder.append(", fromdate=");
    builder.append(fromDate);
    builder.append(", todate=");
    builder.append(toDate);
    builder.append(", currency=");
    builder.append(currency);
    builder.append("]");
    return builder.toString();
}
```

#### Business Rules

1. **Naming Convention Discrepancy:** Internal fields use camelCase (`organizationId`, `fromDate`, `toDate`) while deprecated getters/setters use lowercase variants (`organizationid`, `fromdate`, `todate`)
2. **Deprecation Policy:** The `model` and `organizationId` fields have deprecated accessors, suggesting a transition to different parameter handling approaches

---

### 2. Time

**Package:** `com.mybookingpal.utils.entity`

The `Time` enum provides a comprehensive set of time-related utilities and constants for date/time manipulation throughout the system. It supports UN/CEFACT standard unit codes.

#### Enum Constants

| Constant | Milliseconds | Description |
|----------|--------------|-------------|
| `MILLISECOND` | 1 | Base time unit |
| `SECOND` | 1000 | One second |
| `MINUTE` | 60,000 | 60 seconds |
| `HOUR` | 3,600,000 | 60 minutes |
| `DAY` | 86,400,000 | 24 hours |
| `WEEK` | 604,800,000 | 7 days |
| `MONTH` | 2,592,000,000 | Nominal 30 days |
| `QUARTER` | 7,776,000,000 | Nominal 90 days |
| `YEAR` | 31,536,000,000 | 52 weeks |

#### Static Constants

```java
public static long SERVER_TZ_OFFSET = -120 * MINUTE.milliseconds(); // -2 hours offset
public static int SUNDAY = 0;
public static int MONDAY = 1;
public static int TUESDAY = 2;
public static int WEDNESDAY = 3;
public static int THURSDAY = 4;
public static int FRIDAY = 5;
public static int SATURDAY = 6;
```

#### Instance Methods

```java
public long milliseconds()
```
Returns the millisecond value of the time unit.

#### Static Utility Methods

**Conversion Methods:**

```java
public static long fromInt(int time)
public static long fromInt(int time, Time unit)
public static long fromDouble(double time)
public static long fromDouble(double time, Time unit)
public static double toDouble(long time)
public static double toDouble(long time, Time unit)
```

**Unit Resolution:**

```java
public static Time getUnit(String unit)
```
Converts UN/CEFACT unit codes to `Time` enum values:

| Unit Code | Returns |
|-----------|---------|
| `SEC` | `Time.SECOND` |
| `MIN` | `Time.MINUTE` |
| `HUR` | `Time.HOUR` |
| `DAY` | `Time.DAY` |
| `WEE` | `Time.WEEK` |
| `MON` | `Time.MONTH` |
| `ANN` | `Time.YEAR` |
| (other) | `Time.MILLISECOND` |

**Day Calculations:**

```java
public static boolean isSameDay(Date one, Date other)
public static int getDay(Date date)
public static int getDay(long time)
public static int getClientDay(Date date)
public static Date getDate(int day)
public static Date getClientDate(int day)
```

**Date Boundary Methods:**

```java
public static Date getDateStart()
public static Date getDateStart(Date date)
public static Date getDateEnd()
public static Date getDateEnd(Date date)
public static Date getWeekStart()
public static Date getWeekStart(Date date)
public static Date getWeekEnd()
public static Date getWeekEnd(Date date)
public static Date getMonthStart()
public static Date getMonthStart(Date date)
public static Date getMonthEnd()
public static Date getMonthEnd(Date date)
public static Date getYearStart()
public static Date getYearStart(Date date)
public static Date getYearEnd()
public static Date getYearEnd(Date date)
```

**Duration and Arithmetic:**

```java
public static Date addDuration(Date date, int duration)
public static Date addDuration(Date date, int duration, Time unit)
public static Date addDuration(Date date, double duration)
public static Date addDuration(Date date, double duration, String unit)
public static Date addDuration(Date date, double duration, Time unit)
public static Double getDuration(Date fromDate, Date toDate)
public static Double getDuration(Date fromDate, Date toDate, Time unit)
public static boolean isBetweenDates(Date fromDate, Date toDate, Date date)
```

#### Business Rules

1. **Server Timezone:** The system operates with a fixed server timezone offset of -2 hours (UTC-2)
2. **Day Calculation:** UTC days are calculated using the server timezone offset, while client days use raw milliseconds
3. **Nominal Time Units:** MONTH and QUARTER use nominal values (30 and 90 days respectively) rather than calendar-accurate calculations
4. **Week Start:** Weeks start on Sunday (based on `java.util.Date.getDay()` where Sunday = 0)

---

### 3. IdVersion

**Package:** `com.mybookingpal.utils.entity`

A simple value object that combines an identifier with a version timestamp. Used for optimistic locking and version tracking in distributed systems.

#### Fields

| Field | Type | Description | Access |
|-------|------|-------------|--------|
| `id` | `String` | Entity identifier | Private |
| `version` | `Date` | Version timestamp | Private |

#### Methods

```java
public String getId()
public void setId(String id)
public Date getVersion()
public void setVersion(Date version)
```

#### Business Rules

1. **Version Type:** Versions are tracked using `java.util.Date` objects representing timestamps
2. **String IDs:** Uses String identifiers, not Integer

---

### 4. IdName

**Package:** `com.mybookingpal.utils.entity`

A basic pair of an Integer identifier and a String name. This is the simplest identifier-name combination in the system.

#### Fields

| Field | Type | Description | Access |
|-------|------|-------------|--------|
| `id` | `Integer` | Integer identifier | Private |
| `name` | `String` | Display name | Private |

#### Methods

```java
public Integer getId()
public void setId(Integer id)
public String getName()
public void setName(String name)
```

#### Business Rules

1. **Integer IDs:** Uses Integer type for the identifier (distinct from `NameId` which uses String)

---

### 5. NameId

**Package:** `com.mybookingpal.utils.entity`

A foundational class providing a String identifier and name pair. This class serves as a base for other entities and includes multiple constructor options.

#### Fields

| Field | Type | Description | Access |
|-------|------|-------------|--------|
| `id` | `String` | String identifier | Protected |
| `name` | `String` | Display name | Protected |

#### Constructors

```java
public NameId()
```
Default constructor.

```java
public NameId(String id)
```
Creates a `NameId` where both `id` and `name` are set to the same value.

```java
public NameId(String name, String id)
```
Creates a `NameId` with distinct name and id values.

#### Methods

```java
public String getId()
public void setId(String id)
public String getName()
public void setName(String name)
```

#### Business Rules

1. **Protected Fields:** Both fields are protected, allowing direct access in subclasses
2. **String IDs:** Uses String type for identifiers (distinct from `IdName` which uses Integer)

---

### 6. NameIdAction

**Package:** `com.mybookingpal.utils.entity`

Extends `NameId` to provide a comprehensive parameter object for service actions including pagination, filtering, and state management. This is the primary parameter object for search and retrieval operations.

#### Inheritance

```
NameIdAction extends NameId
```

#### Additional Fields

| Field | Type | Default | Description | Access |
|-------|------|---------|-------------|--------|
| `numrows` | `int` | `Integer.MAX_VALUE` | Maximum number of rows to return | Private |
| `offsetrows` | `int` | `0` | Number of rows to skip (offset) | Private |
| `organizationId` | `String` | null | Organization filter | Protected |
| `state` | `String` | null | State filter | Protected |
| `type` | `String` | null | Type filter | Protected |
| `ids` | `String` | null | Comma-separated list of IDs | Protected |
| `productIds` | `String` | null | Comma-separated product IDs | Protected |
| `version` | `Date` | null | Version filter | Protected |
| `rank` | `Double` | null | Rank filter | Protected |
| `supplierId` | `String` | null | Supplier filter | Protected |
| `parentId` | `String` | null | Parent ID filter | Protected |
| `channelId` | `int` | `0` | Channel filter | Private |

#### Methods

```java
public int getNumrows()
public void setNumrows(int numrows)

public int getOffsetrows()
public void setOffsetrows(int offsetrows)

public String getOrganizationId()
public void setOrganizationId(String organizationId)

public String getState()
public void setState(String state)

public String getType()
public void setType(String type)

public String getIds()
public void setIds(String ids)

public String getProductIds()
public void setProductIds(String productIds)

public Date getVersion()
public void setVersion(Date version)

public Double getRank()
public void setRank(Double rank)

public String getSupplierId()
public void setSupplierId(String supplierId)

public String getParentId()
public void setParentId(String parentId)

public int getChannelId()
public void setChannelId(int channelId)
```

#### Business Rules

1. **Pagination Defaults:** By default, returns all rows (`Integer.MAX_VALUE`) with no offset (`0`)
2. **Comma-Separated Lists:** The `ids` and `productIds` fields expect comma-separated string values for multiple ID filtering
3. **Inherited Fields:** Inherits `id` and `name` from `NameId` base class

---

### 7. NameStateId

**Package:** `com.mybookingpal.utils.entity`

A value object combining an Integer identifier, name, and state. This class includes a Builder pattern for flexible object construction.

#### Fields

| Field | Type | Description | Access |
|-------|------|-------------|--------|
| `id` | `Integer` | Integer identifier | Private |
| `name` | `String` | Display name | Private |
| `state` | `String` | State/status value | Private |

#### Constructors

```java
public NameStateId()
```
Default constructor.

```java
private NameStateId(Builder builder)
```
Private constructor used by the Builder.

#### Methods

```java
public Integer getId()
public void setId(Integer id)

public String getName()
public void setName(String name)

public String getState()
public void setState(String state)
```

#### Builder Pattern

The `Builder` nested class provides a fluent API for constructing `NameStateId` instances:

```java
public static class Builder {
    private Integer id;
    private String name;
    private String state;

    public Builder id(Integer id) {
        this.id = id;
        return this;
    }

    public Builder name(String name) {
        this.name = name;
        return this;
    }

    public Builder state(String state) {
        this.state = state;
        return this;
    }

    public NameStateId build() {
        return new NameStateId(this);
    }
}
```

**Usage Example:**

```java
NameStateId item = new NameStateId.Builder()
    .id(123)
    .name("Product Name")
    .state("ACTIVE")
    .build();
```

#### Business Rules

1. **Integer IDs:** Uses Integer type for the identifier
2. **Builder Pattern:** Enforces the use of the Builder for complex constructions while maintaining simple setters for direct manipulation

---

### 8. BigDecimalExt

**Package:** `com.mybookingpal.utils.entity`

An extension of `java.math.BigDecimal` that provides convenience methods for financial calculations, specifically designed for monetary operations with proper rounding and comparison.

#### Constants

```java
public static final BigDecimalExt ZERO = new BigDecimalExt(BigDecimal.ZERO);
public static final BigDecimalExt ONE = new BigDecimalExt(BigDecimal.ONE);
public static final BigDecimalExt TEN = new BigDecimalExt(BigDecimal.TEN);
public static final BigDecimalExt ONE_HUNDRED = new BigDecimalExt(100);
```

#### Constructors

```java
public BigDecimalExt()
```
Creates a zero value.

```java
public BigDecimalExt(BigDecimal value)
```
Creates from an existing BigDecimal (uses plain string representation to avoid precision issues).

```java
public BigDecimalExt(String val)
```
Creates from a string representation.

```java
public BigDecimalExt(Integer value)
```
Creates from an Integer.

```java
public BigDecimalExt(Double value)
```
Creates from a Double with `MathContext.DECIMAL64` precision.

```java
public BigDecimalExt(long val)
```
Creates from a long with `MathContext.DECIMAL64` precision.

#### Arithmetic Methods

All arithmetic operations return `BigDecimalExt` instances and use `MathContext.DECIMAL64`:

```java
public BigDecimalExt add(BigDecimal augend)
public BigDecimalExt subtract(BigDecimal subtrahend)
public BigDecimalExt multiply(BigDecimal multiplicand)
public BigDecimalExt divide(BigDecimal divisor)
public BigDecimalExt divide(BigDecimal divisor, RoundingMode roundingMode)
```

#### Financial Operation Methods

```java
public BigDecimalExt divideByHundred()
```
Divides the value by 100 (useful for converting percentages to decimals).

```java
public BigDecimalExt multiplyByHundred()
```
Multiplies the value by 100 (useful for converting decimals to percentages).

```java
public BigDecimalExt round()
public BigDecimalExt roundUp()
public BigDecimalExt roundHalfUp()
```
Rounds the value to 2 decimal places using different rounding modes.

#### Comparison Methods

```java
public boolean compareWithDelta(BigDecimal value)
```
Compares with another BigDecimal using a delta of 0.001 (3 decimal places precision).

```java
public boolean greaterThanZero()
public boolean lessThanZero()
public boolean greaterThan(BigDecimalExt value)
public boolean lessThan(BigDecimalExt value)
```
Convenient comparison methods.

#### Utility Methods

```java
public static BigDecimalExt of(String val)
```
Factory method that returns `ZERO` for null or empty strings, otherwise creates a new instance.

```java
public BigDecimalExt min(BigDecimal value)
public BigDecimalExt max(BigDecimal value)
public BigDecimalExt negate()
public BigDecimalExt abs()
```

```java
@Override
public BigDecimalExt setScale(int newScale, int roundingMode)
@Override
public BigDecimalExt setScale(int newScale, RoundingMode roundingMode)
public BigDecimalExt divideToIntegralValue(BigDecimal divisor)
```

#### Business Rules

1. **Precision:** All operations use `MathContext.DECIMAL64` for consistent precision
2. **Rounding:** Default rounding for financial operations is to 2 decimal places (cents)
3. **Null Safety:** The `of()` factory method handles null/empty inputs gracefully
4. **String Construction:** When creating from BigDecimal, uses plain string to avoid scientific notation issues
5. **Delta Comparison:** `compareWithDelta()` uses 3 decimal places for floating-point comparison tolerance

---

### 9. Unit

**Package:** `com.mybookingpal.utils.entity`

Extends `NameId` to represent measurement units with type classification and state management. Contains comprehensive constants for standard UN/CEFACT measurement codes.

#### Inheritance

```
Unit extends NameId
```

#### Constants

**Type Constants:**

```java
public static final String TYPE = "type";

public static final String CREATED = "Created";
public static final String[] STATES = { CREATED };

public static final String AREA = "Area";
public static final String COUNT = "Count";
public static final String LENGTH = "Length";
public static final String MASS = "Mass";
public static final String TIME = "Time";
public static final String VOLUME = "Volume";
public static final String[] TYPES = { AREA, COUNT, LENGTH, MASS, TIME, VOLUME };
```

**UN/CEFACT Unit Code Constants:**

| Constant | Code | Description |
|----------|------|-------------|
| `ANN` | "ANN" | Year |
| `MON` | "MON" | Month |
| `SEC` | "SEC" | Second |
| `MIN` | "MIN" | Minute |
| `HUR` | "HUR" | Hour |
| `DAY` | "DAY" | Day |
| `WEE` | "WEE" | Week |
| `EA` | "EA" | Each (Count) |
| `KGM` | "KGM" | Kilogram (Mass) |
| `LTR` | "LTR" | Liter (Volume) |
| `MTR` | "MTR" | Meter (Length) |
| `MMT` | "MMT" | Millimeter (Length) |
| `KMT` | "KMT" | Kilometer (Length) |
| `INH` | "INH" | Inch (Length) |
| `FOT` | "FOT" | Foot (Length) |
| `YRD` | "YRD" | Yard (Length) |
| `SMI` | "SMI" | Mile (Statute) |
| `NMI` | "NMI" | Mile (Nautical) |

#### Fields

| Field | Type | Default | Description | Access |
|-------|------|---------|-------------|--------|
| `type` | `String` | null | Unit type classification | Protected |
| `state` | `String` | null | State value | Protected |
| `status` | `int` | `0` | Status indicator | Protected |

*(Inherits `id` and `name` from `NameId`)*

#### Methods

```java
public String getType()
public void setType(String type)

public String getState()
public void setState(String state)

public int getStatus()
public void setStatus(int status)
```

**Override:**

```java
@Override
public String toString()
```

Returns a string representation including type, state, status, name, and id.

#### Business Rules

1. **Fixed State:** The `getState()` method always returns `"Created"`, regardless of the underlying field value
2. **Default Status:** Units default to status `0`
3. **Type Classification:** Units are classified into types: Area, Count, Length, Mass, Time, Volume
4. **UN/CEFACT Compliance:** Unit codes follow UN/CEFACT standards for international trade

---

## Class Hierarchy

```
NameId
├── Unit
└── NameIdAction
```

## Usage Patterns

### Parameter Object Pattern

Several classes follow the Parameter Object pattern to encapsulate query parameters:

1. **Parameter**: Basic query parameters with date ranges and filters
2. **NameIdAction**: Extended parameter object with pagination and multi-criteria filtering

### Builder Pattern

**NameStateId** implements the Builder pattern for immutable-style construction:

```java
NameStateId entity = new NameStateId.Builder()
    .id(1)
    .name("Example")
    .state("ACTIVE")
    .build();
```

### Financial Calculations

**BigDecimalExt** provides safe monetary operations:

```java
// Creating values
BigDecimalExt price = BigDecimalExt.of("19.99");
BigDecimalExt taxRate = BigDecimalExt.of("0.08");

// Calculating
BigDecimalExt tax = price.multiply(taxRate).round();
BigDecimalExt total = price.add(tax);

// Comparisons
if (total.greaterThan(BigDecimalExt.of("20.00"))) {
    // Handle expensive items
}
```

### Time Calculations

The **Time** enum provides comprehensive date/time utilities:

```java
// Getting day boundaries
Date todayStart = Time.getDateStart();
Date todayEnd = Time.getDateEnd();

// Checking same day
boolean sameDay = Time.isSameDay(date1, date2);

// Adding duration
Date nextWeek = Time.addDuration(new Date(), 7, Time.DAY);

// Converting units
long milliseconds = Time.fromInt(5, Time.MINUTE);
```

---

## Dependencies

### External Dependencies

- `java.math.BigDecimal`
- `java.math.BigInteger`
- `java.math.MathContext`
- `java.math.RoundingMode`
- `java.util.Date`

### Internal Dependencies

- **Unit** extends **NameId**
- **NameIdAction** extends **NameId**
- **Time** uses **Unit** constants for unit code resolution

---

## Best Practices

1. **Use BigDecimalExt for Money**: Always use `BigDecimalExt` for financial calculations to avoid floating-point precision errors

2. **Prefer NameIdAction for Queries**: Use `NameIdAction` rather than `Parameter` for new query operations as it provides more comprehensive filtering options

3. **Avoid Deprecated Methods**: Do not use deprecated methods in `Parameter` class

4. **Use Builder for Complex Objects**: Utilize the `NameStateId.Builder` for creating complex entity objects

5. **Timezone Awareness**: Be aware that `Time` utilities use a fixed server timezone offset of UTC-2

6. **String IDs vs Integer IDs**: Choose `NameId` (String) or `IdName` (Integer) based on your identifier type requirements

---

## Data Flow Examples

### Query Execution Flow

```
Controller Layer
    ↓ creates
NameIdAction (sets filters, pagination)
    ↓ passes to
Service Layer
    ↓ uses parameters for
Repository/Data Access
    ↓ returns
List<Entities>
```

### Financial Calculation Flow

```
Input (String/Double)
    ↓
BigDecimalExt.of() or constructor
    ↓
Arithmetic operations (add, multiply, etc.)
    ↓
Rounding (round(), roundHalfUp())
    ↓
Comparison or Storage
```

### Date Processing Flow

```
Input Date
    ↓
Time utility methods (getDay, addDuration, etc.)
    ↓
Date boundaries (getDateStart, getDateEnd)
    ↓
Filtered/processed dates
```

---

## Migration Notes

### From Parameter to NameIdAction

When migrating from `Parameter` to `NameIdAction`:

1. Replace `fromDate`/`toDate` with explicit date filtering logic
2. Use `offsetrows` and `numrows` for pagination instead of handling it separately
3. Use `ids` field for comma-separated ID lists
4. Leverage additional filters: `state`, `type`, `organizationId`, `channelId`

### From BigDecimal to BigDecimalExt

When migrating from `BigDecimal` to `BigDecimalExt`:

1. Replace `BigDecimal.valueOf()` with `BigDecimalExt.of()` for string inputs
2. Replace manual rounding with `round()` or `roundHalfUp()`
3. Use convenience methods: `divideByHundred()`, `multiplyByHundred()`
4. Use `compareWithDelta()` for floating-point comparisons instead of `equals()`

---

## Summary

The `common-entities` domain provides essential data structures for the MyBookingPal system:

- **9 core classes** covering parameters, identifiers, time utilities, and financial calculations
- **Builder pattern** implementation in `NameStateId`
- **Comprehensive time utilities** in the `Time` enum
- **Safe monetary calculations** via `BigDecimalExt`
- **UN/CEFACT compliant** unit codes in `Unit`
- **Pagination support** through `NameIdAction`
- **State management** capabilities across multiple entities

These entities form the foundation for data transfer, query parameter handling, and business calculations throughout the enterprise system.