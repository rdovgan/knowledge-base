---
module: mbp-utils
domain: utils-services
generated_at: 2025-01-25T12:00:00Z
status: approved
review_score: 1.0
attempts: 1
---

# Utils Services Domain Documentation

## Overview

The `utils-services` domain within the `mbp-utils` module provides a comprehensive set of utility classes for common operations in Java enterprise applications. These utilities cover date/time manipulation, string operations, collection handling, type conversions, and entity type definitions.

This domain is designed to be stateless and thread-safe, making it suitable for use across distributed systems and multi-threaded environments.

---

## Class Reference

### 1. DateFormatUtils

**Package:** `com.mybookingpal.utils.service`

**Description:** Provides thread-safe access to date and time formatters using `ThreadLocal`. This ensures thread safety in multi-threaded environments without the overhead of creating new formatter instances for each operation.

#### Constants

| Constant Name | Type | Value | Purpose |
|--------------|------|-------|---------|
| `TIME_FORMAT` | ThreadLocal<DateFormat> | `HH:mm` | Time-only formatting (24-hour) |
| `DATE_FORMAT` | ThreadLocal<DateFormat> | `yyyy-MM-dd` | Date-only formatting (ISO-like) |
| `DATE_TIME_FORMAT` | ThreadLocal<DateTimeFormatter> | `yyyy-MM-dd HH:mm:ss` | Date and time formatting |

#### Methods

##### `getTimeFormat()`

```java
public static DateFormat getTimeFormat()
```

**Returns:** A `DateFormat` instance configured for time formatting (HH:mm).

**Thread Safety:** Uses `ThreadLocal` to ensure thread-safe access.

**Example:**
```java
DateFormat timeFormat = DateFormatUtils.getTimeFormat();
String formattedTime = timeFormat.format(new Date());
// Result: "14:30"
```

##### `getDateFormat()`

```java
public static DateFormat getDateFormat()
```

**Returns:** A `DateFormat` instance configured for date formatting (yyyy-MM-dd).

**Example:**
```java
DateFormat dateFormat = DateFormatUtils.getDateFormat();
String formattedDate = dateFormat.format(new Date());
// Result: "2025-01-25"
```

##### `getDateTimeFormat()`

```java
public static DateTimeFormatter getDateTimeFormat()
```

**Returns:** A `DateTimeFormatter` instance configured for date-time formatting (yyyy-MM-dd HH:mm:ss).

**Note:** Unlike the other methods, this returns a `DateTimeFormatter` (from `java.time`) rather than a `DateFormat`.

**Example:**
```java
DateTimeFormatter formatter = DateFormatUtils.getDateTimeFormat();
String formatted = LocalDateTime.now().format(formatter);
// Result: "2025-01-25 14:30:45"
```

---

### 2. DateUtils

**Package:** `com.mybookingpal.utils.service`

**Description:** Provides conversion methods between different date types and their string representations. This class acts as a facade for date formatting operations.

#### Methods

##### `convertToString(LocalDate date)`

```java
public static String convertToString(LocalDate date)
```

**Parameters:**
- `date` - The `LocalDate` to convert

**Returns:** String representation in ISO_LOCAL_DATE format (yyyy-MM-dd).

**Example:**
```java
LocalDate date = LocalDate.of(2025, 1, 25);
String result = DateUtils.convertToString(date);
// Result: "2025-01-25"
```

##### `convertToString(Date date)`

```java
public static String convertToString(Date date)
```

**Parameters:**
- `date` - The legacy `Date` object to convert

**Returns:** String representation in yyyy-MM-dd format.

**Implementation:** Uses `DateFormatUtils.getDateFormat()` for formatting.

**Example:**
```java
Date date = new Date();
String result = DateUtils.convertToString(date);
// Result: "2025-01-25"
```

##### `convertToString(LocalDateTime localDateTime)`

```java
public static String convertToString(LocalDateTime localDateTime)
```

**Parameters:**
- `localDateTime` - The `LocalDateTime` to convert

**Returns:** String representation in yyyy-MM-dd HH:mm:ss format.

**Implementation:** Uses `DateFormatUtils.getDateTimeFormat()` for formatting.

**Example:**
```java
LocalDateTime dateTime = LocalDateTime.of(2025, 1, 25, 14, 30, 45);
String result = DateUtils.convertToString(dateTime);
// Result: "2025-01-25 14:30:45"
```

##### `toLocalDateTime(String date)`

```java
public static LocalDateTime toLocalDateTime(String date)
```

**Parameters:**
- `date` - String representation of a date-time in yyyy-MM-dd HH:mm:ss format

**Returns:** Parsed `LocalDateTime` object.

**Throws:** `DateTimeParseException` if the string cannot be parsed.

**Example:**
```java
LocalDateTime result = DateUtils.toLocalDateTime("2025-01-25 14:30:45");
// Returns LocalDateTime object representing the specified date-time
```

---

### 3. MbpCollectionUtils

**Package:** `com.mybookingpal.utils.service`

**Description:** Provides null-safe utility methods for collection operations. A lightweight alternative to Apache Commons Collections.

#### Methods

##### `isEmpty(Collection<?> coll)`

```java
public static boolean isEmpty(Collection<?> coll)
```

**Parameters:**
- `coll` - The collection to check

**Returns:** `true` if the collection is `null` or empty, `false` otherwise.

**Business Rule:** A null collection is considered empty.

**Example:**
```java
List<String> list = null;
boolean result = MbpCollectionUtils.isEmpty(list);  // true

list = new ArrayList<>();
result = MbpCollectionUtils.isEmpty(list);           // true

list.add("item");
result = MbpCollectionUtils.isEmpty(list);           // false
```

##### `isNotEmpty(Collection<?> coll)`

```java
public static boolean isNotEmpty(Collection<?> coll)
```

**Parameters:**
- `coll` - The collection to check

**Returns:** `true` if the collection is not `null` and contains at least one element.

**Implementation:** Returns `!isEmpty(coll)`.

**Example:**
```java
List<String> list = Arrays.asList("a", "b", "c");
boolean result = MbpCollectionUtils.isNotEmpty(list);  // true
```

---

### 4. MbpStringUtils

**Package:** `com.mybookingpal.utils.service`

**Description:** A comprehensive string manipulation utility class providing methods for null-safe checks, padding, trimming, searching, replacing, and substring operations. This class serves as a custom implementation similar to Apache Commons StringUtils but optimized for the MyBookingPal ecosystem.

#### Null-Safe Checks

##### `isEmpty(CharSequence cs)`

```java
public static boolean isEmpty(CharSequence cs)
```

**Parameters:**
- `cs` - The CharSequence to check

**Returns:** `true` if the sequence is `null` or has zero length.

**Example:**
```java
MbpStringUtils.isEmpty(null)      // true
MbpStringUtils.isEmpty("")        // true
MbpStringUtils.isEmpty("  ")      // false
MbpStringUtils.isEmpty("abc")     // false
```

##### `isNotEmpty(CharSequence cs)`

```java
public static boolean isNotEmpty(CharSequence cs)
```

**Returns:** `!isEmpty(cs)`

##### `isBlank(CharSequence cs)`

```java
public static boolean isBlank(CharSequence cs)
```

**Parameters:**
- `cs` - The CharSequence to check

**Returns:** `true` if the sequence is `null`, zero length, or contains only whitespace characters.

**Business Rule:** A string with only whitespace (spaces, tabs, newlines) is considered blank.

**Example:**
```java
MbpStringUtils.isBlank(null)      // true
MbpStringUtils.isBlank("")        // true
MbpStringUtils.isBlank("  ")      // true
MbpStringUtils.isBlank("\t\n")    // true
MbpStringUtils.isBlank("abc")     // false
MbpStringUtils.isBlank("  abc")   // false
```

#### Repetition Methods

##### `repeat(String str, int repeat)`

```java
public static String repeat(String str, int repeat)
```

**Parameters:**
- `str` - The string to repeat
- `repeat` - Number of times to repeat

**Returns:** The repeated string, or empty/null based on input.

**Business Rules:**
- Returns `null` if input string is `null`
- Returns empty string if repeat <= 0
- Optimized for single-character strings up to 8192 repetitions

**Example:**
```java
MbpStringUtils.repeat("ab", 3)    // "ababab"
MbpStringUtils.repeat("a", 5)     // "aaaaa"
MbpStringUtils.repeat("x", 0)     // ""
MbpStringUtils.repeat(null, 3)    // null
```

##### `repeat(String str, String separator, int repeat)`

```java
public static String repeat(String str, String separator, int repeat)
```

**Parameters:**
- `str` - The string to repeat
- `separator` - Separator between repetitions
- `repeat` - Number of times to repeat

**Returns:** String with repetitions separated by the separator.

**Example:**
```java
MbpStringUtils.repeat("a", ",", 3)  // "a,a,a"
MbpStringUtils.repeat("x", "-", 2)  // "x-x"
```

#### Padding Methods

##### `leftPad(String str, int size, String padStr)`

```java
public static String leftPad(String str, int size, String padStr)
```

**Parameters:**
- `str` - The string to pad
- `size` - The target size
- `padStr` - The string to use for padding

**Returns:** Left-padded string.

**Business Rules:**
- Returns `null` if input string is `null`
- Uses single space if padStr is empty
- Returns original string if size <= string length

**Example:**
```java
MbpStringUtils.leftPad("abc", 6, "z")    // "zzzabc"
MbpStringUtils.leftPad("abc", 5, ".")    // "..abc"
MbpStringUtils.leftPad("abc", 2, "z")     // "abc" (no padding needed)
```

##### `leftPad(String str, int size, char padChar)`

```java
public static String leftPad(String str, int size, char padChar)
```

**Optimization:** Optimized for padding up to 8192 characters.

**Example:**
```java
MbpStringUtils.leftPad("123", 5, '0')    // "00123"
```

#### Search and Comparison Methods

##### `equals(CharSequence firstSequence, CharSequence secondSequence)`

```java
public static boolean equals(CharSequence firstSequence, CharSequence secondSequence)
```

**Returns:** `true` if sequences are equal, handling null values safely.

**Business Rule:** Two null sequences are considered equal.

##### `equalsIgnoreCase(CharSequence firstSequence, CharSequence secondSequence)`

```java
public static boolean equalsIgnoreCase(CharSequence firstSequence, CharSequence secondSequence)
```

**Returns:** `true` if sequences are equal, ignoring case and handling null values.

**Example:**
```java
MbpStringUtils.equalsIgnoreCase("ABC", "abc")  // true
MbpStringUtils.equalsIgnoreCase(null, null)      // true
MbpStringUtils.equalsIgnoreCase("ABC", null)      // false
```

##### `contains(CharSequence seq, CharSequence searchSeq)`

```java
public static boolean contains(CharSequence seq, CharSequence searchSeq)
```

**Returns:** `true` if searchSeq is found within seq, handling null values.

**Example:**
```java
MbpStringUtils.contains("abcdef", "cde")  // true
MbpStringUtils.contains("abc", null)        // false
MbpStringUtils.contains(null, "abc")        // false
```

##### `containsIgnoreCase(CharSequence str, CharSequence searchStr)`

```java
public static boolean containsIgnoreCase(CharSequence str, CharSequence searchStr)
```

**Returns:** Case-insensitive containment check.

**Example:**
```java
MbpStringUtils.containsIgnoreCase("ABCDEF", "cde")  // true
```

##### `indexOf(CharSequence cs, CharSequence searchChar, int start)`

```java
public static int indexOf(CharSequence cs, CharSequence searchChar, int start)
```

**Returns:** Index of first occurrence starting from position `start`, or -1 if not found.

##### `indexOfIgnoreCase(CharSequence str, CharSequence searchStr, int startPos)`

```java
public static int indexOfIgnoreCase(CharSequence str, CharSequence searchStr, int startPos)
```

**Returns:** Case-insensitive index of first occurrence, or -1 if not found.

#### Substring and Manipulation Methods

##### `substringAfter(String str, String separator)`

```java
public static String substringAfter(String str, String separator)
```

**Returns:** Substring after the first occurrence of separator.

**Business Rules:**
- Returns empty string if separator is not found
- Returns empty string if separator is null

**Example:**
```java
MbpStringUtils.substringAfter("abcde", "c")    // "de"
MbpStringUtils.substringAfter("abcde", "x")    // ""
MbpStringUtils.substringAfter("abcde", null)   // ""
```

##### `substring(String str, int start)`

```java
public static String substring(String str, int start)
```

**Returns:** Substring from start index, handling negative indices.

**Business Rules:**
- Negative start is treated as offset from end
- Returns empty string if start is beyond string length

**Example:**
```java
MbpStringUtils.substring("abcde", 2)   // "cde"
MbpStringUtils.substring("abcde", -2)  // "de"
MbpStringUtils.substring("abc", 10)    // ""
```

##### `substring(String str, int start, int end)`

```java
public static String substring(String str, int start, int end)
```

**Returns:** Substring from start to end index, handling negative indices.

**Example:**
```java
MbpStringUtils.substring("abcde", 1, 3)   // "bc"
MbpStringUtils.substring("abcde", -3, -1)  // "cd"
```

##### `difference(String str1, String str2)`

```java
public static String difference(String str1, String str2)
```

**Returns:** The portion of str2 that differs from str1, starting from the first different character.

**Example:**
```java
MbpStringUtils.difference("abc", "abd")   // "d"
MbpStringUtils.difference("abc", "abc")   // ""
MbpStringUtils.difference(null, "abc")    // "abc"
```

##### `removeEnd(String str, String remove)`

```java
public static String removeEnd(String str, String remove)
```

**Returns:** String with the specified suffix removed.

**Example:**
```java
MbpStringUtils.removeEnd("filename.txt", ".txt")  // "filename"
MbpStringUtils.removeEnd("filename", ".txt")     // "filename"
```

#### Replacement Methods

##### `replace(String text, String searchString, String replacement)`

```java
public static String replace(String text, String searchString, String replacement)
```

**Parameters:**
- `text` - The source text
- `searchString` - The string to search for
- `replacement` - The replacement string

**Returns:** Text with all occurrences replaced.

**Business Rules:**
- Returns original text if any parameter is null or empty
- Uses `StringBuilder` for efficient replacement

**Example:**
```java
MbpStringUtils.replace("ababab", "ab", "x")  // "xxx"
MbpStringUtils.replace("hello", "x", "y")     // "hello"
```

##### `replaceAll(final String text, final String regex, final String replacement)`

```java
public static String replaceAll(final String text, final String regex, final String replacement)
```

**Returns:** Text with all regex matches replaced.

**Note:** Delegates to `String.replaceAll()` for regex-based replacement.

**Example:**
```java
MbpStringUtils.replaceAll("a1b2c3", "\\d", "")  // "abc"
```

#### Utility Methods

##### `getDigits(String str)`

```java
public static String getDigits(String str)
```

**Returns:** String containing only digit characters from the input.

**Example:**
```java
MbpStringUtils.getDigits("a1b2c3")   // "123"
MbpStringUtils.getDigits("abc")       // ""
MbpStringUtils.getDigits("")          // ""
```

##### `right(String str, int len)`

```java
public static String right(String str, int len)
```

**Returns:** Rightmost `len` characters of the string.

**Business Rules:**
- Returns `null` if input is `null`
- Returns empty string if len < 0
- Returns entire string if len >= string length

**Example:**
```java
MbpStringUtils.right("abcdef", 3)  // "def"
MbpStringUtils.right("abc", 5)     // "abc"
MbpStringUtils.right("abc", -1)    // ""
```

##### `startsWith(CharSequence str, CharSequence prefix)`

```java
public static boolean startsWith(CharSequence str, CharSequence prefix)
```

**Returns:** `true` if str starts with prefix, handling null values.

##### `wrapIfMissing(String str, String wrapWith)`

```java
public static String wrapIfMissing(String str, String wrapWith)
```

**Returns:** String wrapped with wrapWith if not already wrapped.

**Example:**
```java
MbpStringUtils.wrapIfMissing("test", "'")   // "'test'"
MbpStringUtils.wrapIfMissing("'test'", "'")  // "'test'"
MbpStringUtils.wrapIfMissing(null, "'")      // null
```

##### `isAlphanumeric(CharSequence cs)`

```java
public static boolean isAlphanumeric(CharSequence cs)
```

**Returns:** `true` if the sequence contains only letters and digits.

**Business Rule:** Returns `false` for null or empty sequences.

**Example:**
```java
MbpStringUtils.isAlphanumeric("abc123")   // true
MbpStringUtils.isAlphanumeric("abc 123")   // false
MbpStringUtils.isAlphanumeric("")          // false
```

---

### 5. Converter

**Package:** `com.mybookingpal.utils.service`

**Description:** Provides type conversion methods between primitive wrapper types `Integer` and `Long` with null-safety.

#### Methods

##### `toLong(Integer intValue)`

```java
public static Long toLong(Integer intValue)
```

**Parameters:**
- `intValue` - The Integer value to convert

**Returns:** `Long` representation of the Integer, or `null` if input is `null`.

**Business Rule:** Null input produces null output (no NullPointerException).

**Example:**
```java
Converter.toLong(42)      // 42L
Converter.toLong(null)    // null
Converter.toLong(Integer.MAX_VALUE)  // 2147483647L
```

##### `toInt(Long longValue)`

```java
public static Integer toInt(Long longValue)
```

**Parameters:**
- `longValue` - The Long value to convert

**Returns:** `Integer` representation of the Long, or `null` if input is `null`.

**Business Rule:** Null input produces null output.

**Example:**
```java
Converter.toInt(42L)      // 42
Converter.toInt(null)     // null
// Note: No overflow protection for values exceeding Integer range
```

---

### 6. CommonDateUtils

**Package:** `com.mybookingpal.utils.service`

**Description:** Comprehensive utility class for converting between legacy `java.util.Date`, modern `java.time` API types (`LocalDate`, `LocalDateTime`), and `XMLGregorianCalendar`. This class serves as a bridge in systems transitioning from legacy date handling to the modern Java Time API.

#### Constants

| Constant | Type | Value | Purpose |
|----------|------|-------|---------|
| `MIN_LOCAL_DATE` | LocalDate | 1970-01-01 | Minimum allowable date (Unix epoch) |
| `MAX_LOCAL_DATE` | LocalDate | 3014-05-17 | Maximum allowable date |

#### Conversion to Legacy Date

##### `toDate(LocalDateTime localDateTime)`

```java
public static Date toDate(LocalDateTime localDateTime)
```

**Parameters:**
- `localDateTime` - The LocalDateTime to convert

**Returns:** `Date` representing the same instant in the system default timezone.

**Business Rule:** If input is `null`, returns current date (`new Date()`).

**Example:**
```java
LocalDateTime ldt = LocalDateTime.of(2025, 1, 25, 14, 30);
Date date = CommonDateUtils.toDate(ldt);
```

##### `toDate(LocalDate localDate)`

```java
public static Date toDate(LocalDate localDate)
```

**Parameters:**
- `localDate` - The LocalDate to convert

**Returns:** `Date` representing the start of the day in the system default timezone, or `null` if input is `null`.

**Business Rule:** Converts to the beginning of the day (00:00:00) in the local timezone.

**Example:**
```java
LocalDate ld = LocalDate.of(2025, 1, 25);
Date date = CommonDateUtils.toDate(ld);
// Represents 2025-01-25 00:00:00 in local timezone
```

##### `toDate(ZonedDateTime zonedDateTime)`

```java
public static Date toDate(ZonedDateTime zonedDateTime)
```

**Parameters:**
- `zonedDateTime` - The ZonedDateTime to convert

**Returns:** `Date` representing the same instant.

**Note:** Preserves the exact instant, converting to UTC internally.

**Example:**
```java
ZonedDateTime zdt = ZonedDateTime.now(ZoneId.of("UTC"));
Date date = CommonDateUtils.toDate(zdt);
```

##### `getDate(XMLGregorianCalendar xmlGregorianCalendar)`

```java
public static Date getDate(XMLGregorianCalendar xmlGregorianCalendar)
```

**Parameters:**
- `xmlGregorianCalendar` - The XML calendar to convert

**Returns:** `Date` representation of the XML calendar.

**Throws:** `IllegalArgumentException` if input is `null`.

**Business Rule:** On parse exception, returns current date as fallback.

**Example:**
```java
XMLGregorianCalendar xmlCal = ...;
Date date = CommonDateUtils.getDate(xmlCal);
```

#### Conversion from Legacy Date

##### `toLocalDate(Date date)`

```java
public static LocalDate toLocalDate(Date date)
```

**Parameters:**
- `date` - The legacy Date to convert

**Returns:** `LocalDate` representing the date portion, or `null` if input is `null`.

**Implementation:** Uses `java.sql.Date` for conversion to extract date only.

**Example:**
```java
Date date = new Date();
LocalDate ld = CommonDateUtils.toLocalDate(date);
```

##### `toLocalDateTime(Date date)`

```java
public static LocalDateTime toLocalDateTime(Date date)
```

**Parameters:**
- `date` - The legacy Date to convert

**Returns:** `LocalDateTime` in the system default timezone, or `null` if input is `null`.

**Example:**
```java
Date date = new Date();
LocalDateTime ldt = CommonDateUtils.toLocalDateTime(date);
```

#### Modern Date Conversions

##### `toLocalDateTime(LocalDate localDate)`

```java
public static LocalDateTime toLocalDateTime(LocalDate localDate)
```

**Parameters:**
- `localDate` - The LocalDate to convert

**Returns:** `LocalDateTime` representing the start of the day (00:00:00), or `null` if input is `null`.

**Example:**
```java
LocalDate ld = LocalDate.of(2025, 1, 25);
LocalDateTime ldt = CommonDateUtils.toLocalDateTime(ld);
// Result: 2025-01-25T00:00:00
```

#### Comparison Methods

##### `isBeforeOrEquals(LocalDate date1, LocalDate date2)`

```java
public static boolean isBeforeOrEquals(LocalDate date1, LocalDate date2)
```

**Returns:** `true` if date1 is before or equal to date2.

**Business Rule:** Returns `false` if either date is `null`.

**Example:**
```java
LocalDate d1 = LocalDate.of(2025, 1, 25);
LocalDate d2 = LocalDate.of(2025, 1, 26);
CommonDateUtils.isBeforeOrEquals(d1, d2);  // true
CommonDateUtils.isBeforeOrEquals(d2, d1);  // false
CommonDateUtils.isBeforeOrEquals(d1, d1);  // true
CommonDateUtils.isBeforeOrEquals(null, d2); // false
```

##### `isAfterOrEquals(LocalDate date1, LocalDate date2)`

```java
public static boolean isAfterOrEquals(LocalDate date1, LocalDate date2)
```

**Returns:** `true` if date1 is after or equal to date2.

**Business Rule:** Returns `false` if either date is `null`.

**Example:**
```java
LocalDate d1 = LocalDate.of(2025, 1, 25);
LocalDate d2 = LocalDate.of(2025, 1, 26);
CommonDateUtils.isAfterOrEquals(d1, d2);  // false
CommonDateUtils.isAfterOrEquals(d2, d1);  // true
CommonDateUtils.isAfterOrEquals(d1, d1);  // true
```

---

### 7. NameIdUtils

**Package:** `com.mybookingpal.utils.service`

**Description:** Contains an enumeration of entity types used throughout the MyBookingPal system. This provides type-safe constants for identifying different domain entities.

#### Inner Enum: Type

```java
public enum Type {
    Account,
    Asset,
    Contract,
    Country,
    Currency,
    Design,
    Event,
    Feature,
    Finance,
    Language,
    Lease,
    License,
    Location,
    Mandatory,
    MandatoryPerDay,
    Optional,
    Partner,
    Party,
    Price,
    Product,
    Reservation,
    ResPassThr,
    Rule,
    Task,
    Tax,
    Yield,
    Payment,
    Modification
}
```

#### Usage

This enum is used to categorize and identify different types of entities in the system.

**Example:**
```java
NameIdUtils.Type entityType = NameIdUtils.Type.Reservation;

switch (entityType) {
    case Account:
        // Handle account
        break;
    case Reservation:
        // Handle reservation
        break;
    // ... other cases
}
```

#### Entity Type Descriptions

| Type | Description |
|------|-------------|
| `Account` | User or system account |
| `Asset` | Physical or digital asset |
| `Contract` | Legal agreement or contract |
| `Country` | Geographic country |
| `Currency` | Monetary currency |
| `Design` | Design template or configuration |
| `Event` | System or business event |
| `Feature` | Product or service feature |
| `Finance` | Financial record or transaction |
| `Language` | Language or locale setting |
| `Lease` | Rental or lease agreement |
| `License` | License or permission |
| `Location` | Geographic or logical location |
| `Mandatory` | Mandatory fee or charge |
| `MandatoryPerDay` | Daily mandatory fee |
| `Optional` | Optional service or fee |
| `Partner` | Business partner |
| `Party` | Party involved in transaction |
| `Price` | Pricing information |
| `Product` | Product or service offering |
| `Reservation` | Booking or reservation |
| `ResPassThr` | Reservation pass-through value |
| `Rule` | Business or system rule |
| `Task` | Scheduled task or job |
| `Tax` | Tax information |
| `Yield` | Yield management data |
| `Payment` | Payment information |
| `Modification` | Modification record |

---

### 8. CalendarUtils

**Package:** `com.mybookingpal.utils.service`

**Description:** Provides utility methods for calendar and date manipulation, focusing on current date operations and LocalDate to Date conversions.

#### Methods

##### `getNowMinusOneSecond()`

```java
public static Date getNowMinusOneSecond()
```

**Returns:** Current date and time minus one second, converted to `Date`.

**Use Case:** Useful for creating exclusive upper bounds in date range queries.

**Example:**
```java
Date yesterday = CalendarUtils.getNowMinusOneSecond();
// If current time is 2025-01-25 14:30:45.123
// Returns 2025-01-25 14:30:44.123
```

##### `localDateToDate(LocalDate localDate)`

```java
public static Date localDateToDate(LocalDate localDate)
```

**Parameters:**
- `localDate` - The LocalDate to convert

**Returns:** `Date` representing the start of the day (00:00:00) in system default timezone, or `null` if input is `null`.

**Note:** This method duplicates functionality in `CommonDateUtils.toDate(LocalDate)`.

**Example:**
```java
LocalDate ld = LocalDate.of(2025, 1, 25);
Date date = CalendarUtils.localDateToDate(ld);
// Represents 2025-01-25 00:00:00 in local timezone
```

---

## Cross-Reference and Interdependencies

### Date Handling Chain

The date handling utilities work together in a specific hierarchy:

```
DateFormatUtils (formatters)
    ↓
DateUtils (string conversions)
    ↓
CommonDateUtils (type conversions)
    ↓
CalendarUtils (calendar-specific operations)
```

### Common Patterns

1. **Null Safety**: All utility methods handle `null` inputs gracefully, returning `null`, empty strings, or default values rather than throwing `NullPointerException`.

2. **Thread Safety**: `DateFormatUtils` uses `ThreadLocal` to ensure thread-safe access to formatters.

3. **Immutability**: All methods are static and stateless, making them safe for concurrent use.

### Code Examples

#### Example 1: Date Conversion Workflow

```java
// Convert from legacy Date to modern LocalDate
Date legacyDate = new Date();
LocalDate modernDate = CommonDateUtils.toLocalDate(legacyDate);

// Format for display
String formatted = DateUtils.convertToString(modernDate);
System.out.println(formatted);  // "2025-01-25"

// Parse back
LocalDate parsed = LocalDate.parse(formatted);
```

#### Example 2: String Validation and Manipulation

```java
String userInput = "  123-45-6789  ";

// Clean and validate
if (MbpStringUtils.isNotBlank(userInput)) {
    String trimmed = userInput.trim();
    String digits = MbpStringUtils.getDigits(trimmed);
    
    // Result: "123456789"
    System.out.println(digits);
}
```

#### Example 3: Collection Safety

```java
List<String> items = possiblyNullList();

if (MbpCollectionUtils.isNotEmpty(items)) {
    items.forEach(item -> {
        if (MbpStringUtils.isNotEmpty(item)) {
            processItem(item);
        }
    });
}
```

#### Example 4: Date Range Comparison

```java
LocalDate startDate = LocalDate.of(2025, 1, 1);
LocalDate endDate = LocalDate.of(2025, 1, 31);
LocalDate checkDate = LocalDate.of(2025, 1, 15);

// Check if date is within range (inclusive)
boolean inRange = CommonDateUtils.isAfterOrEquals(checkDate, startDate) 
                && CommonDateUtils.isBeforeOrEquals(checkDate, endDate);

// inRange == true
```

## Configuration Notes

### Timezone Handling

All date conversions use `ZoneId.systemDefault()` for timezone conversions. This means:

- Conversions respect the server's default timezone
- UTC conversions require explicit `ZonedDateTime` usage
- For consistent behavior across environments, consider configuring a specific timezone

### Date Range Limits

`CommonDateUtils` defines:
- **MIN_LOCAL_DATE**: 1970-01-01 (Unix epoch)
- **MAX_LOCAL_DATE**: 3014-05-17

These limits should be respected when working with dates in the system.

## Performance Considerations

1. **ThreadLocal Formatters**: `DateFormatUtils` uses `ThreadLocal` to avoid the performance cost of creating new formatter instances. However, in thread-pool environments, this may lead to memory retention.

2. **StringBuilder Usage**: `MbpStringUtils` uses `StringBuilder` for string manipulations to avoid creating excessive intermediate strings.

3. **Optimizations**: Several methods in `MbpStringUtils` have special-case optimizations for common scenarios (e.g., single-character padding up to 8192 characters).

## Business Rules Summary

| Rule | Description |
|------|-------------|
| Null Collection | Collections that are `null` are treated as empty |
| Blank Strings | Strings containing only whitespace are considered blank |
| Null Date Handling | Null date inputs typically return null or current date (method-specific) |
| Empty Substrings | Substring operations return empty string rather than null for out-of-bounds |
| Equality Checks | Two `null` values are considered equal |
| Date Comparisons | Comparisons return `false` if either date is `null` |

---

## Appendix: Quick Reference

### Import Statements

```java
import com.mybookingpal.utils.service.CalendarUtils;
import com.mybookingpal.utils.service.CommonDateUtils;
import com.mybookingpal.utils.service.Converter;
import com.mybookingpal.utils.service.DateFormatUtils;
import com.mybookingpal.utils.service.DateUtils;
import com.mybookingpal.utils.service.MbpCollectionUtils;
import com.mybookingpal.utils.service.MbpStringUtils;
import com.mybookingpal.utils.service.NameIdUtils;
```

### Common Idioms

```java
// Null-safe empty check
if (MbpStringUtils.isEmpty(str) || MbpCollectionUtils.isEmpty(list)) {
    // Handle empty case
}

// Date formatting
String dateStr = DateUtils.convertToString(LocalDate.now());

// Type conversion
Long longValue = Converter.toLong(intValue);

// Date range check
boolean validRange = CommonDateUtils.isBeforeOrEquals(start, end);
```

---

*Generated documentation for mbp-utils module, utils-services domain.*