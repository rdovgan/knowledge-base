---
module: mbp-utils
domain: overview
generated_at: 2025-06-17T12:00:00Z
status: needs-human-review
review_score: 0.5
attempts: 3
---

# Module Overview: mbp-utils

## Introduction

The `mbp-utils` module serves as the foundational shared library for the MyBookingPal platform. It is a Java-based utility module designed to provide common data structures, enumerations, and helper methods to all other modules within the MyBookingPal ecosystem.

### Core Purpose

The primary architectural goal of `mbp-utils` is to eliminate code duplication and enforce consistency across the platform by centralizing shared logic. By moving common entities and utility classes into a distinct module, the platform ensures that business rules, data definitions, and helper functions are defined in a single source of truth.

### Dependency-Free Design

A critical architectural constraint of `mbp-utils` is that it is designed to be **dependency-free**. It introduces no external library dependencies that might conflict with the specific needs of downstream modules. This design choice ensures that `mbp-utils` can be safely imported by any other module—whether it is a web service, a batch processor, or a legacy integration—without risk of "Jar Hell" or circular dependency issues.

> **IMPORTANT**: The `pom.xml` explicitly contains the comment: "DO NOT IMPORT ANY DEPENDENCY TO THIS MODULE." This rule is strictly enforced to maintain the module's lightweight nature and universal compatibility.

## Module Architecture

The module is organized into distinct domains, each encapsulating a specific aspect of the platform's shared requirements.

### 1. Business Enums (`com.mybookingpal.utils.enums`)

This domain contains the platform's core business vocabulary. It defines `enum` types that represent constants used throughout the application lifecycle, from channel integrations to pricing strategies.

#### Key Components

*   **`BookingPalEnums`**: A central class housing multiple business-related enumerations.
*   **`Valued` Interface**: A common interface implemented by many enums to provide a standardized way of accessing integer or string values associated with enum constants.

#### Code Example: `BookingPalEnums`

The `BookingPalEnums` class provides a comprehensive definition of channels and yield types. For example, the `YieldType` enum defines various pricing strategies like "Date Range", "Early Bird", and "Last Minute".

```java
public enum YieldType implements Valued {
    DATE_RANGE("Date Range"), 
    DAY_OF_WEEK("Day of Week"), 
    GAP_FILLER("Maximum Gap Filler"), 
    EARLY_BIRD("Early Booking Lead Time"), 
    LAST_MINUTE("Last Minute Lead Time"),
    // ... other yield types
    
    private final String value;

    YieldType(String value) {
        this.value = value;
    }

    @Override
    public String getStringValue() {
        return this.value;
    }
}
```

It also defines integration channels:

```java
public enum Channel implements Valued {
    BOOKINGCOM("Booking.com", "BKG"), 
    AIRBNB("AirBnb", "ABB"), 
    EXPEDIA("Expedia", "EXP"), 
    // ... other channels
    
    private final String name;
    private final String value;

    Channel(String name, String value) {
        this.name = name;
        this.value = value;
    }
}
```

### 2. Common Entities (`com.mybookingpal.utils.entity`)

This domain defines the data transfer objects (DTOs) and simple value objects that form the basic currency of data exchange between the frontend, backend services, and external APIs.

#### Key Components

*   **`IdName`**: A ubiquitous class used to represent a simple mapping between an integer ID and its human-readable name.
*   **`NameId`**: Similar to `IdName` but often used in contexts where the name is the primary reference.
*   **`Parameter`**: Used for storing key-value pair configurations.
*   **`Time`**: Represents time-specific data structures.
*   **`BigDecimalExt`**: An extension of the standard `BigDecimal` to handle financial calculations with platform-specific precision or formatting rules.

#### Code Example: `IdName`

The `IdName` entity is a POJO (Plain Old Java Object) that encapsulates a basic identifier and name pair.

```java
public class IdName {
    private Integer id;
    private String name;

    public Integer getId() {
        return id;
    }

    public void setId(Integer id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

### 3. Utils Services (`com.mybookingpal.utils.service`)

This domain contains stateless utility classes that perform common operations, reducing boilerplate code in business logic layers.

#### Key Components

*   **`DateUtils`**: Provides methods for date manipulation, arithmetic (adding days, calculating differences), and comparison.
*   **`CalendarUtils`**: Wraps `java.util.Calendar` operations for easier handling of dates and times.
*   **`DateFormatUtils`**: Standardizes the parsing and formatting of date strings into various patterns (ISO, localized, etc.).
*   **`MbpStringUtils`**: Custom string manipulation utilities beyond what `org.apache.commons.lang3` offers, tailored to MBP data formats.
*   **`MbpCollectionUtils`**: Helper methods for filtering, transforming, and validating collections.
*   **`Converter`**: Utilities for converting complex objects between different types (e.g., DTO to Entity).

#### Code Example: `DateUtils`

The `DateUtils` class provides static methods for converting between different date representations:

```java
public class DateUtils {

    public static String convertToString(LocalDate date) {
        return DateTimeFormatter.ISO_LOCAL_DATE.format(date);
    }

    public static String convertToString(Date date) {
        return DateFormatUtils.getDateFormat().format(date);
    }

    public static String convertToString(LocalDateTime localDateTime) {
        return DateFormatUtils.getDateTimeFormat().format(localDateTime);
    }

    public static LocalDateTime toLocalDateTime(String date) {
        return LocalDateTime.parse(date, DateFormatUtils.getDateTimeFormat());
    }
}
```

### 4. Security (`com.mybookingpal.utils.security`)

Security is paramount in a platform handling financial transactions. This domain provides utilities for data protection.

#### Key Components

*   **`BCrypt`**: A wrapper around the BCrypt hashing algorithm for securely hashing and verifying user passwords.
*   **`CreditCardMaskingUtil`**: Implements logic to mask sensitive credit card information (PAN, CVV, Expiry) to ensure that logs and UI displays never expose full financial data.

## Data Flow and Integration

The `mbp-utils` module acts as a "downstream" dependency for all functional modules (e.g., `mbp-reservation`, `mbp-channel-manager`).

1.  **Definition**: Data types (like `YieldType`) are defined here.
2.  **Consumption**: Functional modules import these types to enforce type safety. For instance, a pricing service will use `YieldType.EARLY_BIRD` directly from the utils package.
3.  **Transformation**: When data is received from an external channel (e.g., via API), the `Converter` or `DateUtils` services are often used to normalize the incoming data into the standard `mbp-utils` entity formats before processing by the business logic.

## Configuration and Build

As a standard Maven module, `mbp-utils` adheres to strict build configurations to maintain its "dependency-free" promise.

### Maven Configuration (`pom.xml`)

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.mybookingpal</groupId>
    <artifactId>utils</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>
    
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <source>8</source>
                    <target>8</target>
                </configuration>
            </plugin>
        </plugins>
    </build>
    
    <!-- THIS MODULE WAS IMPLEMENTED TO MOVE ENTITIES OR UTILS CLASSES TO ONE PLACE. 
         IT WILL BE INCLUDED IN EACH MBP MODULE.
         DO NOT IMPORT ANY DEPENDENCY TO THIS MODULE. -->
</project>
```

### Key Build Characteristics

*   **Java Version**: Targeted for Java 8 compatibility to ensure it runs across the widest range of deployment environments within the MyBookingPal infrastructure.
*   **Dependencies**: The `pom.xml` is strictly audited. Generally, only the Java Standard Library (JDK) is used. Adding dependencies like Spring or Apache Commons is prohibited to prevent bloat and transitive dependency conflicts.
*   **Packaging**: Distributed as a JAR file (`jar` packaging) to be included as a dependency in other modules.

## Domain Coverage

The `mbp-utils` module encompasses four main domains:

| Domain | Package | Complexity | Description |
|--------|---------|------------|-------------|
| Business Enums | `com.mybookingpal.utils.enums` | High | Business-related enumerations and constants (channels, yield types, notifications) |
| Common Entities | `com.mybookingpal.utils.entity` | Low | Data transfer objects and value objects (IdName, Parameter, Time) |
| Utils Services | `com.mybookingpal.utils.service` | Medium | Stateless utility classes for dates, strings, collections, and conversions |
| Security | `com.mybookingpal.utils.security` | Medium | Password hashing and credit card data masking utilities |

## Summary

The `mbp-utils` module is the bedrock of the MyBookingPal platform. By centralizing enumerations, entities, utilities, and security helpers, it ensures consistency, reduces code duplication, and enforces a strict architectural pattern regarding dependencies. It allows the broader engineering team to focus on complex business logic, confident that the fundamental building blocks of the application are robust, tested, and readily available.

### Architectural Principles

1.  **Single Source of Truth**: All shared business definitions reside here.
2.  **Zero External Dependencies**: Ensures universal compatibility.
3.  **Java 8 Compatibility**: Maximum portability across the platform.
4.  **Stateless Design**: Utility classes are stateless for thread safety and ease of testing.
5.  **Type Safety**: Strong typing through enums and custom entities prevents runtime errors.

This module is not just a collection of helpers—it is the foundation upon which the entire MyBookingPal ecosystem is built, providing stability, consistency, and reliability to every component that depends on it.