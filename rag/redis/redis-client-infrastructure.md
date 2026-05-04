---
module: redis
domain: Redis Client Infrastructure
generated_at: 2025-06-18T12:00:00Z
status: draft
---

# Redis Client Infrastructure Module

## Overview

The Redis Client Infrastructure module provides a unified abstraction layer over Redis operations within the `com.mybookingpal.redis.client` package. It implements a **Strategy Pattern** where a single interface (`IRedisClient`) is fulfilled by multiple concrete implementations using different underlying Redis driver libraries (Jedis and Lettuce). A centralized factory (`RedisClientManager`) manages client instantiation based on environment (production vs. test) and business context (general caching, quote caching, PM-specific caching, Shiro session management).

## Architecture

```
                    ┌──────────────────┐
                    │  IRedisClient    │  (Interface)
                    └────────┬─────────┘
                             │
           ┌─────────────────┼────────────────────┐
           │                 │                    │
  ┌────────┴────────┐  ┌────┴───────────┐  ┌────┴───────────────────┐
  │  JedisClient    │  │ LettuceClient  │  │ MrtQuoteLettuceCluster │
  │                 │  │                │  │       Client           │
  └────────┬────────┘  └────────────────┘  └────────────────────────┘
           │                                         │
  ┌────────┴────────┐                  ┌─────────────┴──────────────┐
  │ JedisTestClient │                  │ LettuceClusterTestClient  │
  └─────────────────┘                  └────────────────────────────┘

                    ┌──────────────────────┐
                    │ RedisClientManager   │  (Factory)
                    └──────────────────────┘
```

## Interface: `IRedisClient`

**Package:** `com.mybookingpal.redis.client`  
**Type:** Interface

This is the central contract for all Redis operations in the system. Every Redis interaction — whether for caching, queuing, or key scanning — routes through this interface.

### Method Reference

| Return Type | Method Signature | Description |
|-------------|-----------------|-------------|
| `boolean` | `isAvailable()` | Checks whether the Redis connection is available. |
| `void` | `storeValueToRedisHash(String key, String field, String value)` | Stores a single field-value pair in a Redis hash. |
| `void` | `storeValueToRedisHashWithExpire(String key, String field, String value, Integer seconds)` | Stores a field-value pair in a hash and sets a TTL on the hash key. |
| `void` | `storeValueToRedis(String key, String value)` | Stores a simple string key-value pair. |
| `void` | `storeValueToRedisWithExpire(String key, String value, Integer seconds)` | Stores a string key-value pair with a TTL. |
| `Long` | `incrementValueInRedis(String key)` | Atomically increments a counter key. Returns `null` on failure. |
| `void` | `expire(String key, Integer seconds)` | Sets a TTL on an existing key. |
| `String` | `getValueFromRedisHash(String key, String field)` | Retrieves a single field from a Redis hash. Returns `null` on failure. |
| `String` | `getValueFromRedis(String key)` | Retrieves a simple string value. Returns empty string `""` on failure in some implementations. |
| `Map<String, String>` | `getValueFromRedisHash(String key)` | Retrieves all field-value pairs from a Redis hash. |
| `void` | `clearValuesInCache(String key, String[] fields)` | Removes specific fields from a hash. |
| `void` | `clearValueInCache(String key, String field)` | Removes a single field from a hash. |
| `void` | `clearValueInCache(String key)` | Deletes a key entirely (note: behavior differs between implementations — see below). |
| `Collection<String>` | `findKeys(String pattern)` | **@Deprecated**. Finds keys by glob pattern using `KEYS` command. Creates load on Redis. |
| `void` | `enqueue(String key, String value)` | Pushes a value to the tail of a Redis list (RPUSH). |
| `String` | `dequeue(String key)` | Pops a value from the head of a Redis list (LPOP). |
| `List<String>` | `scan(String keyPattern)` | Iterates keys using `SCAN` with a match pattern and batch size of 50. |
| `void` | `storeMapToRedisHashWithExpire(String key, Map<String, String> fieldValueMap, Integer seconds)` | Bulk-stores a map into a hash and sets a TTL. |

### Important Behavioral Note: `clearValueInCache(String key)`

There is a **deliberate behavioral inconsistency** between the two main implementations:

- **`JedisClient`** calls `jedis.del(key)` — deletes the key entirely regardless of data type.
- **`LettuceClient`** calls `connection.sync().hdel(key)` — only removes fields from a hash, and with no field arguments this is effectively a no-op or error-prone call.

This is a known asymmetry that consumers must be aware of.

---

## Implementation: `JedisClient`

**Package:** `com.mybookingpal.redis.client`  
**Extends:** Implements `IRedisClient`  
**Driver:** Jedis (thread-safe via `JedisPool`)

This is the **primary production client** for general-purpose Redis operations. It uses a statically initialized `JedisPool` with a carefully tuned pool configuration.

### Connection Pool Configuration

The pool is built by the `buildPoolConfig()` method with the following settings:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `maxTotal` | `128` | Maximum number of connections in the pool. |
| `maxIdle` | `128` | Maximum idle connections retained. |
| `minIdle` | `16` | Minimum idle connections kept warm. |
| `testOnBorrow` | `true` | Validates connections before handing them out. |
| `testOnReturn` | `true` | Validates connections when returned. |
| `testWhileIdle` | `true` | Validates idle connections in the background. |
| `minEvictableIdleTimeMillis` | `60000` (60s) | Idle connections evicted after 60 seconds. |
| `timeBetweenEvictionRunsMillis` | `30000` (30s) | Eviction check runs every 30 seconds. |
| `numTestsPerEvictionRun` | `3` | Number of connections tested per eviction run. |
| `blockWhenExhausted` | `true` | Threads block (instead of fail) when pool is exhausted. |

### Connection Details

```java
private static JedisPool jedisPool = new JedisPool(
    poolConfig,
    Properties.getRedisHost(),
    Properties.getRedisPort(),
    1000,                          // 1-second connection timeout
    Properties.getRedisPassword()
);
```

### Error Handling Strategy

`JedisClient` uses a **silent swallow** pattern for most operations. Exceptions are caught and ignored:

```java
@Override
public void storeValueToRedis(String key, String value) {
    try (Jedis jedis = getConnection()) {
        jedis.set(key, value);
    } catch (Exception ignored) {
    }
}
```

Exceptions are only logged (via `LOG.error`) for read operations (`getValueFromRedisHash`, `getValueFromRedis`). This means write failures are invisible to callers — a deliberate design choice for resilience but one that makes debugging cache misses difficult.

### `scan()` Implementation

Unlike `LettuceClient` which performs a single scan call, `JedisClient.scan()` iterates through all cursors until the scan is complete:

```java
@Override
public List<String> scan(String keyPattern) {
    try (Jedis jedis = getConnection()) {
        List<String> keys = new ArrayList<>();
        ScanParams scanParam = new ScanParams();
        String cursor = ScanParams.SCAN_POINTER_START;
        scanParam.match(keyPattern);
        scanParam.count(50);
        do {
            ScanResult<String> ret = jedis.scan(cursor, scanParam);
            List<String> result = ret.getResult();
            if (result != null && result.size() > 0) {
                keys.addAll(result);
            }
            cursor = ret.getStringCursor();
        } while (!cursor.equals(ScanParams.SCAN_POINTER_START));
        return keys;
    } catch (Exception ignored) {
    }
    return null;
}
```

> **Key difference from LettuceClient:** The Jedis version performs a **full iteration** over all matching keys, while the Lettuce version performs only a **single scan iteration** with `ScanCursor.FINISHED`. This means `LettuceClient.scan()` may return incomplete results for large keyspaces.

### `findKeys()` Return Type Discrepancy

`JedisClient.findKeys()` returns `Set<String>` (from `jedis.keys()`), which is technically incompatible with the interface's declared return type of `Collection<String>`. This compiles due to Java's covariant return types with generics, but consumers should be aware the actual runtime type is a `Set`.

---

## Implementation: `LettuceClient`

**Package:** `com.mybookingpal.redis.client`  
**Extends:** Implements `IRedisClient`  
**Driver:** Lettuce (non-cluster, single connection)

This client uses Lettuce's **synchronous API** over a single `StatefulRedisConnection`. Connection is lazily initialized on first use.

### Connection Initialization

```java
protected StatefulRedisConnection<String, String> getConnection() {
    if (connection == null) {
        RedisURI redisUri = RedisURI.Builder
                .redis(Properties.getRedisHost(), Properties.getRedisPort())
                .withPassword(Properties.getRedisPassword())
                .withSsl(false)
                .build();
        RedisClient redisClient = RedisClient.create(redisUri);
        connection = redisClient.connect();

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            if (connection != null) {
                connection.close();
            }
        }));
    }
    return connection;
}
```

**Key characteristics:**
- SSL is hardcoded to `false`.
- A JVM shutdown hook is registered to close the connection gracefully.
- The `getConnection()` method is `protected`, enabling subclasses to override it for different connection targets (e.g., cluster connections).
- **No connection pooling** — a single shared connection is used for all operations. This is suitable for low-concurrency or single-threaded usage but may become a bottleneck under load.

### Error Handling Strategy

Unlike `JedisClient`, `LettuceClient` logs **all** exceptions at ERROR level:

```java
} catch (Exception e) {
    LOG.error("Error during communication with redis occurred. ", e);
    return null; // or empty collection
}
```

This provides better observability at the cost of more verbose logs during outages.

---

## Implementation: `JedisTestClient`

**Package:** `com.mybookingpal.redis.client`  
**Extends:** `JedisClient`

A thin subclass that overrides the connection source to point to a test Redis instance using `PropertiesForTest` instead of `Properties`.

```java
private static JedisPool testJedisPool = new JedisPool(
    poolConfig,
    PropertiesForTest.getRedisHost(),
    PropertiesForTest.getRedisPort(),
    1000,
    PropertiesForTest.getRedisPassword()
);

@Override
protected Jedis getConnection() {
    return testJedisPool.getResource();
}
```

**Notes:**
- Inherits the same pool configuration from the parent's `poolConfig` (static, shared).
- Uses a **separate** `JedisPool` instance so test connections don't interfere with production.
- The parent class's `jedisPool` field is never used when this class is active.

---

## Implementation: `LettuceClusterTestClient`

**Package:** `com.mybookingpal.redis.client`  
**Extends:** `MrtQuoteLettuceClusterClient`

This is a **disabled stub** for cluster-based Redis in test environments. The `getConnection()` method immediately throws a `RuntimeException`:

```java
@Override
protected StatefulRedisClusterConnection<String, String> getConnection() {
    throw new RuntimeException("Sorry, the connection is unavailable");
}
```

The original implementation is commented out in the source. It was intended to connect to a cluster using `ClusterPropertiesForTest` settings, but has been deliberately disabled. Any operation on this client will fail with the above exception.

> **Warning:** If `RedisClientManager.getQuoteClient(false)` is called, it returns this client. All subsequent Redis operations will throw `RuntimeException`. This appears to be intentional — quote caching is disabled in non-production environments.

---

## Factory: `RedisClientManager`

**Package:** `com.mybookingpal.redis.client`  
**Type:** Static utility class (no instantiation)

This class serves as the **central factory** for obtaining Redis client instances. All clients are lazily initialized and stored in static fields, making them effectively singletons per JVM.

### Client Registry

| Static Field | Production Type | Test Type | Purpose |
|--------------|----------------|-----------|---------|
| `redisClient` | `JedisClient` | `JedisTestClient` | General-purpose Redis operations. |
| `redisClientSpecialPmNew` | `SpecialPmClient(true)` | `SpecialPmTestClient` | PM-specific caching (new version). |
| `redisClientSpecialPm` | `SpecialPmClient()` | `SpecialPmTestClient` | PM-specific caching (legacy version). |
| `redisQuoteClient` | `MrtQuoteLettuceClusterClient` | `LettuceClusterTestClient` | Quote caching (default channel). |
| `mrtRedisQuoteClient` | `MrtQuoteLettuceClusterClient` | *(falls through to test)* | Quote caching for Marriott channel. |
| `bpRedisQuoteClient` | `BpQuoteLettuceClient` | *(falls through to test)* | Quote caching for BookingPal channel. |
| `lettuceClusterTestClient` | N/A | `LettuceClusterTestClient` | Shared test cluster client. |
| `shiroRedisClient` | `ShiroJedisClient` | `JedisTestClient` | Apache Shiro session storage. |

### Factory Methods

#### `getRedisClient(boolean isProduction)`

Returns the general-purpose Redis client.

```java
public static IRedisClient getRedisClient(boolean isProduction) {
    if (redisClient == null) {
        if (isProduction) {
            redisClient = new JedisClient();
        } else {
            redisClient = new JedisTestClient();
        }
    }
    return redisClient;
}
```

#### `getRedisClientSpecialPm(boolean isProduction)` / `getRedisClientSpecialPmNew(boolean isProduction)`

Returns PM-specific clients. The `New` variant passes `true` to `SpecialPmClient` constructor, suggesting a configuration difference (likely different Redis database index or host).

#### `getQuoteClient(boolean isProduction)`

Returns the default quote client. In production, uses `MrtQuoteLettuceClusterClient` (Lettuce cluster). In test, returns the disabled `LettuceClusterTestClient`.

#### `getQuoteClient(boolean isProduction, String channelAbbreviation)`

Channel-aware quote client factory. Supports routing by channel abbreviation:

| Abbreviation | Constant | Production Client |
|-------------|----------|-------------------|
| `"MRT"` | `MARRIOTT_ABBREVIATION` | `MrtQuoteLettuceClusterClient` |
| `"BP"` | `BOOKINGPAL_ABBREVIATION` | `BpQuoteLettuceClient` |
| Any other value | — | Throws `IllegalArgumentException` |

In non-production, all channels fall through to the shared `LettuceClusterTestClient` (which is disabled).

```java
public static IRedisClient getQuoteClient(boolean isProduction, String channelAbbreviation) {
    if (isProduction) {
        switch (channelAbbreviation) {
            case MARRIOTT_ABBREVIATION:
                if (mrtRedisQuoteClient == null) {
                    mrtRedisQuoteClient = new MrtQuoteLettuceClusterClient();
                }
                return mrtRedisQuoteClient;
            case BOOKINGPAL_ABBREVIATION:
                if (bpRedisQuoteClient == null) {
                    bpRedisQuoteClient = new BpQuoteLettuceClient();
                }
                return bpRedisQuoteClient;
            default:
                throw new IllegalArgumentException();
        }
    } else {
        if (lettuceClusterTestClient == null) {
            lettuceClusterTestClient = new LettuceClusterTestClient();
        }
        return lettuceClusterTestClient;
    }
}
```

#### `getShiroRedisClient(boolean isProduction)`

Returns a client for Apache Shiro session management. Production uses `ShiroJedisClient`; test uses `JedisTestClient`.

#### `getRedisClient()` *(Deprecated)*

Legacy no-arg factory that always creates a `JedisClient`. Marked `@Deprecated`.

### Thread Safety

`RedisClientManager` uses **check-then-act** initialization without synchronization. In a multi-threaded startup scenario, multiple instances of the same client type could theoretically be created, with only the last one retained. In practice, this is unlikely to cause issues since Spring typically initializes beans on a single thread, but it is a latent race condition.

---

## Business Rules and Data Flows

### Queue Operations (FIFO)

The `enqueue`/`dequeue` methods implement a simple FIFO queue using Redis lists:

- **`enqueue(key, value)`** → `RPUSH` (append to tail)
- **`dequeue(key)`** → `LPOP` (remove from head)

This is a standard Redis queue pattern suitable for low-throughput task queues. It is **not** resilient to consumer crashes (no acknowledgment mechanism).

### TTL Semantics

Methods suffixed with `WithExpire` set the TTL **after** the write operation using a separate `EXPIRE` call. This means there is a small race window between the write and the TTL assignment where the key exists without expiration. For atomic TTL assignment, the underlying Redis `SETEX` or `HSET` + `EXPIRE` pipeline would be needed, but this implementation uses two separate commands.

### Key Scanning

Two approaches are provided:

1. **`findKeys(pattern)`** — Uses `KEYS` command. **Deprecated** because it blocks the Redis server for the duration of the scan. Should never be used in production.
2. **`scan(keyPattern)`** — Uses `SCAN` with `COUNT 50`. However, as noted above, the `LettuceClient` implementation only performs a single iteration and may miss keys.

---

## Driver Comparison: Jedis vs. Lettuce

| Aspect | JedisClient | LettuceClient |
|--------|-------------|---------------|
| Connection model | Pool (`JedisPool`, 128 max) | Single shared connection |
| Thread safety | Pool-based, inherently safe | Single connection, synchronized by Lettuce |
| Error handling | Silent swallow (writes); logged (reads) | All errors logged at ERROR level |
| SSL support | Not configured in pool constructor | Hardcoded to `false` |
| Shutdown | Pool handles via finalizer | Explicit shutdown hook |
| `scan()` completeness | Full cursor iteration | Single iteration only |
| `clearValueInCache(key)` | `DEL` key | `HDEL` with no fields (no-op) |
| `findKeys()` return type | `Set<String>` | `List<String>` |

---

## Referenced Types (Not in Source Files)

The following types are referenced but not part of the provided source files. They are documented here for completeness based on usage:

| Class | Purpose |
|-------|---------|
| `Properties` | Provides `getRedisHost()`, `getRedisPort()`, `getRedisPassword()` for production. |
| `PropertiesForTest` | Provides `getRedisHost()`, `getRedisPort()`, `getRedisPassword()` for test environments. |
| `ClusterPropertiesForTest` | Provides cluster-specific test configuration (referenced in commented-out code). |
| `SpecialPmClient` | PM-specific Redis client (production). Constructor accepts boolean flag. |
| `SpecialPmTestClient` | PM-specific Redis client (test). |
| `MrtQuoteLettuceClusterClient` | Lettuce cluster client for Marriott quote caching. Parent of `LettuceClusterTestClient`. |
| `BpQuoteLettuceClient` | Lettuce client for BookingPal quote caching. |
| `ShiroJedisClient` | Jedis-based client for Shiro session management. |

---

## Summary

The Redis Client Infrastructure provides a practical but imperfect abstraction over Redis. The primary concerns for developers are:

1. **Silent error swallowing** in `JedisClient` write operations can mask connectivity issues.
2. **Behavioral inconsistency** in `clearValueInCache(String key)` between Jedis (`DEL`) and Lettuce (`HDEL` with no fields).
3. **Incomplete `scan()`** in `LettuceClient` — only a single cursor iteration.
4. **Disabled test cluster client** — `LettuceClusterTestClient` throws on every operation; quote caching is effectively off in non-production.
5. **Race condition** in `RedisClientManager`'s lazy initialization (no synchronization).
6. **No connection pooling** in `LettuceClient` — potential bottleneck under concurrent load.