---
module: mbp-utils
domain: security
generated_at: 2023-10-27T10:30:00Z
status: approved
review_score: 0.95
attempts: 2
---

# Security Domain Documentation

This document provides a comprehensive overview of the security utilities within the `mbp-utils` module. It covers two primary sub-domains: **Password Hashing** using the BCrypt algorithm and **Credit Card Data Masking** for PII (Personally Identifiable Information) protection.

## Table of Contents

1. [Password Hashing (BCrypt)](#password-hashing-bcrypt)
2. [Credit Card Masking](#credit-card-masking)
3. [Dependencies](#dependencies)

---

## Password Hashing (BCrypt)

**Class:** `com.mybookingpal.utils.security.BCrypt`

### Overview

The `BCrypt` class implements the OpenBSD-style Blowfish password hashing scheme as described in "A Future-Adaptable Password Scheme" by Niels Provos and David Mazieres. This system is designed to thwart off-line password cracking using a computationally-intensive hashing algorithm based on Bruce Schneier's Blowfish cipher.

The work factor of the algorithm is parameterized, allowing it to be increased as computers get faster.

### Key Constants

| Constant Name | Value | Description |
| --- | --- | --- |
| `GENERATE_SALT_DEFAULT_LOG2_ROUNDS` | `10` | The default logarithm of the number of rounds (2^10 iterations). |
| `BCRYPT_SALT_LEN` | `16` | The required length of the salt in bytes (128 bits). |
| `BLOWFISH_NUM_ROUNDS` | `16` | The number of rounds for the Blowfish cipher. |

### Public API

#### Hashing Passwords

**Method:** `hashPassword(String password, String salt)`

Hashes a plaintext password using the OpenBSD bcrypt scheme.

*   **Parameters:**
    *   `password`: The plaintext password to hash.
    *   `salt`: The salt to hash with (typically generated using `BCrypt.generateSalt()`). The salt format usually looks like `$2a$10$...`.
*   **Returns:** The hashed password string.
*   **Throws:** `IllegalArgumentException` if the salt version is invalid.

*Note:* The method `hashpw(String password, String salt)` exists but is **deprecated**.

#### Generating Salts

**Method:** `generateSalt(int numberOfRounds)`

Generates a salt for use with the `hashPassword` method.

*   **Parameters:**
    *   `numberOfRounds`: The log2 of the number of rounds of hashing to apply (the work factor increases as 2^log_rounds). Valid range is 4 to 31.
*   **Returns:** An encoded salt value string.

**Method:** `generateSalt()`

Generates a salt using the default number of rounds (`10`).

*Note:* The methods `gensalt(int numberOfRounds)` and `gensalt()` exist but are **deprecated**.

#### Checking Passwords

**Method:** `checkPassword(String plaintext, String hashed)`

Checks that a plaintext password matches a previously hashed one.

*   **Parameters:**
    *   `plaintext`: The plain text password to verify.
    *   `hashed`: The previously-hashed password.
*   **Returns:** `true` if the passwords match, `false` otherwise.

*Note:* The method `checkpw(String plaintext, String hashed)` exists but is **deprecated**.

### Internal Algorithm Details

The implementation relies on a custom Base64 encoding/decoding scheme specific to bcrypt (not compatible with standard MIME Base64) and a Feistel network structure for the Blowfish cipher.

1.  **Base64 Encoding:** Uses a custom alphabet starting with `./` followed by `A-Za-z0-9`.
2.  **Key Expansion:** The `enhanceKeySchedule` method prepares the cipher by processing both the salt and password.
3.  **Hashing Loop:** The core `cryptRaw` method initializes the key, runs the enhanced key schedule, and then performs `2^log_rounds` iterations of alternating between keying with the password and keying with the salt.
4.  **Output:** The final state of the cipher is encoded into the resulting hash string.

### Usage Examples

```java
// Hashing a password for the first time
String plainPassword = "mySecretPassword";
String salt = BCrypt.generateSalt(12); // Stronger salt
String hashedPassword = BCrypt.hashPassword(plainPassword, salt);

// Verifying a password
boolean isMatch = BCrypt.checkPassword("mySecretPassword", hashedPassword);
if (isMatch) {
    System.out.println("It matches");
} else {
    System.out.println("It does not match");
}
```

---

## Credit Card Masking

The credit card masking functionality is located in the `com.mybookingpal.utils.security.creditcard` package. It provides utilities to sanitize logs, debug output, or any text strings containing sensitive credit card information (PAN, CVC, Expiry Date) by replacing sensitive digits with masking characters (`*`).

### Component Overview

1.  **`CreditCardMaskingUtil`**: The main utility class containing the masking logic.
2.  **Keyword Enums**: Define the specific string keys used to identify sensitive fields within text (e.g., JSON, XML, logs).

### Keyword Enums

These enums are used by the masking utility to locate sensitive values associated with specific keys in a text block.

#### CardNumberKeyWord

Defines keys associated with the Primary Account Number (PAN).

| Enum Constant | String Value |
| --- | --- |
| `CARDNUMBER` | `"cardNumber"` |
| `CC_NUMBER` | `"cc_number"` |
| `CARD_NUMBER` | `"card_number"` |
| `MASKED_NUMBER` | `"maskedNumber"` |
| `CREDIT_CARD_NUMBER` | `"creditCardNumber"` |
| `NUMBER` | `"<number>"` |

#### CvcKeyWord

Defines keys associated with the Card Verification Code (CVC/CVV).

| Enum Constant | String Value |
| --- | --- |
| `SERIESCODE` | `"seriesCode"` |
| `CC_CVC` | `"cc_cvc"` |
| `CVV` | `"cvv"` |
| `CC_SECURITY_CODE` | `"cc_security_code"` |
| `CREDIT_CARD_CID` | `"creditCardCid"` |
| `CARDCODE` | `"cardcode"` |
| `CVC` | `"cvc"` |

#### ExpiryDateKeyWord

Defines keys associated with the card expiration date.

| Enum Constant | String Value |
| --- | --- |
| `EXPIREDATE` | `"expireDate"` |
| `CC_EXPIRATION_DATE` | `"cc_expiration_date"` |
| `EXPIRATION` | `"expiration"` |
| `CARD_MONTH` | `"card_month"` |
| `CREDIT_CARD_EXPIRATION_MONTH` | `"creditCardExpirationMonth"` |
| `CARD_YEAR` | `"card_year"` |
| `CREDIT_CARD_EXPIRATION_YEAR` | `"creditCardExpirationYear"` |
| `CARDMONTH` | `"cardmonth"` |
| `CARDYEAR` | `"cardyear"` |
| `EXPIRE_MONTH` | `"expire_month"` |
| `EXPIRE_YEAR` | `"expire_year"` |

### CreditCardMaskingUtil

**Class:** `com.mybookingpal.utils.security.creditcard.CreditCardMaskingUtil`

#### Constants

| Constant | Value | Description |
| --- | --- | --- |
| `MASKING_CHAR` | `"*"` | The character used to replace sensitive data. |
| `NUMBERS_REGEX` | `"[0-9/]"` | Regex identifying digits and slashes to be masked. |
| `CREDIT_CARD_NUMBER_REGEX` | Complex Pattern | Matches 13-19 digit credit card numbers (with optional spaces/hyphens). |

#### Public Methods

##### maskCreditCardInformation(String text)

The primary entry point for masking all types of credit card data in a string.

*   **Behavior:**
    1.  Checks for blank input.
    2.  Replaces Unicode escape sequences (e.g., `\u0020`) with actual characters to ensure patterns are matched correctly.
    3.  Attempts to mask: Credit Card Numbers, CVCs, and Expiry Dates.
    4.  **Error Handling:** If any exception occurs during the specific masking steps, it falls back to a fail-safe method `maskCardNumberWithoutKeyWord(text)` to ensure no sensitive data leaks.

##### maskCreditCardNumber(String text)

Masks credit card numbers identified by the `CardNumberKeyWord` enum.

*   **Logic:**
    *   Iterates through defined keywords.
    *   If a keyword is found in the text, it invokes internal masking logic.
    *   **Special Rule:** Only the **last 4 digits** of the card number are preserved. All preceding digits are replaced by `*`.
    *   **Formatting:** Spaces within the number sequence are removed. Dashes present in the matched sequence are replaced by the continuous masked string (e.g., dashes do not appear in the final output).
    *   **Recursive Masking:** If the card number appears elsewhere in the text without the keyword, that instance is also masked using the same pattern.

```java
// Example Input:
String input = "cardNumber=4111-1111-1111-1111";
// Example Output:
String output = CreditCardMaskingUtil.maskCreditCardNumber(input);
// Result: "cardNumber=************1111"
// Note: Dashes are removed in the output.
```

```java
// Example Input with spaces:
String input = "cardNumber=4111 1111 1111 1111";
// Example Output:
String output = CreditCardMaskingUtil.maskCreditCardNumber(input);
// Result: "cardNumber=************1111"
```

##### maskCvc(String text)

Masks CVC/CVV codes identified by the `CvcKeyWord` enum.

*   **Logic:**
    *   Locates keywords (e.g., `cvv=`).
    *   Replaces all digits immediately following the keyword with `*`.
    *   **Special Rule:** If the value found is `"0"`, it is not masked.

```java
// Example Input:
String input = "cvv=123";
// Example Output:
String output = CreditCardMaskingUtil.maskCvc(input);
// Result: "cvv=***"
```

##### maskExpiryDate(String text)

Masks expiry dates identified by the `ExpiryDateKeyWord` enum.

*   **Logic:**
    *   Locates keywords.
    *   Masks digits (and slashes `/` as per `NUMBERS_REGEX`) following the keyword.
    *   **Special Rule:** If the value found is `"0"`, it is not masked.

```java
// Example Input:
String input = "expireDate=12/25";
// Example Output:
String output = CreditCardMaskingUtil.maskExpiryDate(input);
// Result: "expireDate=****"
```

##### maskCardNumberWithoutKeyWord(String text)

A fail-safe method that masks valid credit card number patterns found in the text *without* requiring an associated keyword.

*   **Logic:**
    *   Uses the `CREDIT_CARD_NUMBER_PATTERN` to find candidates.
    *   Checks surrounding characters to ensure the match is not part of a larger alphanumeric sequence (false positive prevention).
    *   Masks all digits except the last 4.

### Internal Logic & Business Rules

This section details the internal behaviors of the utility class used to enforce masking policies.

1.  **Unicode Normalization:** The method `replaceUnicodeCharacterToNormal` decodes unicode escapes (e.g., `\u003d` becomes `=`) before processing. This is crucial for logs that might encode special characters.

2.  **Quote Wrapping:** If the masked value is separated from the keyword by a colon (`:`) or equals sign (`=`), and the value wasn't originally quoted, the utility wraps the masked asterisks in double quotes.
    *   Input: `cvv=123` → Output: `cvv="***"`

3.  **Keyword Search & Masking:** The utility employs a private helper method `maskByKeyWord` to process specific fields. This method uses a case-insensitive regex to locate the keyword and the subsequent numeric values. The logic is as follows:
    *   **Pattern:** `(?i){keyword}([^a-zA-Z0-9*]*[a-zA-Z]?[0-9])+\s*`
    *   `(?i)`: Case insensitive match for the keyword.
    *   `([^a-zA-Z0-9*]*...)`: Allows for separators like `=`, `:`, spaces after the keyword.
    *   `[a-zA-Z]?`: Tolerates accidental single letters in the number sequence.
    *   `\s*`: Consumes trailing spaces.

4.  **Zero Value Exclusion:** If the detected number value is strictly `"0"`, it is returned unmasked. This prevents masking of flag values that might look like IDs.

---

## Dependencies

The `CreditCardMaskingUtil` relies on `com.mybookingpal.utils.service.MbpStringUtils` for various string manipulations such as:
*   Checking for blank strings (`isBlank`)
*   Replacing substrings (`replace`, `replaceAll`)
*   Padding strings (`leftPad`)
*   Substring extraction (`substring`, `substringAfter`)
*   Alphanumeric checks

---

## Summary

The `mbp-utils` security module provides robust mechanisms for protecting sensitive data. The `BCrypt` implementation ensures secure password storage using industry-standard adaptive hashing, while the `CreditCardMaskingUtil` offers granular, regex-backed sanitization of credit card data to prevent leakage in logs and outputs. The use of Enums for keyword configuration makes the masking logic easily extensible for new field names.