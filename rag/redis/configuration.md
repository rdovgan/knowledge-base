---
module: redis
domain: configuration
generated_at: 2025-06-18T12:00:00Z
status: needs-human-review
review_score: 0.0
attempts: 3
---

# Redis Module — Configuration

## Overview

The Redis module uses a **static properties class pattern** for configuration — not Spring `@ConfigurationProperties` or YAML-driven binding. Each Redis deployment target (production main, Shiro auth, Special PM, MRT quote cluster, BP quote, test environments) has its own dedicated properties class with hardcoded connection parameters. These classes are consumed by `RedisClientManager`, a singleton factory that lazily initializes `IRedisClient` instances using double-checked locking.

> **Important:** Connection credentials are embedded directly in source code as `private static final` constants. There is no externalized configuration mechanism (no `application.yml`, no environment variables, no Spring profiles for properties resolution). Environment switching requires changing which properties class is referenced in the client implementation.

---

## Properties Classes — Complete Reference

All properties classes reside in the package `com.mybookingpal.redis.client`. Every accessor method has `protected` visibility, restricting access to subclasses within the same package (i.e., the client implementations and `RedisClientManager`).

### `Properties` — Main Production Redis

**File:** `com.mybookingpal.redis.client.Properties`

This is the primary production configuration. It defines connection parameters for two Redis deployments: the main application Redis and the Special PM Redis (with old/new server variants).

```java
package com.mybookingpal.redis.client;

public class Properties {

    private static final String REDIS_HOST = "redis.bookingpal.org";
    private static final String REDIS_PASS = "b!mS+mt9UFJ!8v]W";
    private static final int REDIS_PORT = 6379;

    private static final String SPECIAL_PM_REDIS_HOST = "redis-redawning.bookingpal.org";
    private static final String SPECIAL_PM_REDIS_HOST_NEW = "172.16.1.166";
    private static final String SPECIAL_PM_REDIS_PASS = "b!mS+mt9UFJ!8v]W";
    private static final int SPECIAL_PM_REDIS_PORT = 6379;

    protected static String getRedisHost() {
        return REDIS_HOST;
    }

    protected static String getRedisPassword() {
        return REDIS_PASS;
    }

    protected static int getRedisPort() {
        return REDIS_PORT;
    }

    protected static String getRedisHostSpecialPm(Boolean isNewServer) {
        if (isNewServer) {
            return SPECIAL_PM_REDIS_HOST_NEW;
        }
        return SPECIAL_PM_REDIS_HOST;
    }

    protected static String getRedisPasswordSpecialPm() {
        return SPECIAL_PM_REDIS_PASS;
    }

    protected static int getRedisPortSpecialPm() {
        return SPECIAL_PM_REDIS_PORT;
    }
}
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REDIS_HOST` | `redis.bookingpal.org` | Main production Redis host |
| `REDIS_PASS` | `b!mS+mt9UFJ!8v]W` | Main production Redis password |
| `REDIS_PORT` | `6379` | Main production Redis port |
| `SPECIAL_PM_REDIS_HOST` | `redis-redawning.bookingpal.org` | Special PM old server host |
| `SPECIAL_PM_REDIS_HOST_NEW` | `172.16.1.166` | Special PM new server host (internal IP) |
| `SPECIAL_PM_REDIS_PASS` | `b!mS+mt9UFJ!8v]W` | Special PM Redis password (same as main) |
| `SPECIAL_PM_REDIS_PORT` | `6379` | Special PM Redis port |

**Business Rule:** The Special PM host is selected at runtime via the `isNewServer` boolean parameter. When `true`, the internal IP `172.16.1.166` is used; when `false`, the DNS hostname `redis-redawning.bookingpal.org` is used. Both share the same password and port.

---

### `ShiroProperties` — Authentication Redis

**File:** `com.mybookingpal.redis.client.ShiroProperties`

Dedicated configuration for the Shiro authentication caching layer. Uses a separate Redis instance at a different hostname to isolate auth session data from application caching.

```java
package com.mybookingpal.redis.client;

public class ShiroProperties {

    private static final String REDIS_HOST = "redis-shiro.bookingpal.org";
    private static final String REDIS_PASS = "b!mS+mt9UFJ!8v]W";
    private static final int REDIS_PORT = 6379;

    protected static String getRedisHost() {
        return REDIS_HOST;
    }

    protected static String getRedisPassword() {
        return REDIS_PASS;
    }

    protected static int getRedisPort() {
        return REDIS_PORT;
    }
}
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REDIS_HOST` | `redis-shiro.bookingpal.org` | Shiro auth Redis host |
| `REDIS_PASS` | `b!mS+mt9UFJ!8v]W` | Shiro auth Redis password |
| `REDIS_PORT` | `6379` | Shiro auth Redis port |

---

### `PropertiesForTest` — Demo/Test Environment

**File:** `com.mybookingpal.redis.client.PropertiesForTest`

Mirror of `Properties` for the demo/test environment. Note the different host and port (`6380` vs `6379`), and critically, the Special PM host resolves to the **same** demo Redis — there is no old/new server distinction in test.

```java
package com.mybookingpal.redis.client;

public class PropertiesForTest {

    private static final String REDIS_HOST = "redis-demo.bookingpal.org";
    private static final String REDIS_PASS = "c&8p8v+[3XRF$mMy";
    private static final int REDIS_PORT = 6380;

    private static final String SPECIAL_PM_REDIS_HOST = "redis-demo.bookingpal.org";
    private static final String SPECIAL_PM_REDIS_PASS = "c&8p8v+[3XRF$mMy";
    private static final int SPECIAL_PM_REDIS_PORT = 6380;

    protected static String getRedisHost() {
        return REDIS_HOST;
    }

    protected static String getRedisPassword() {
        return REDIS_PASS;
    }

    protected static int getRedisPort() {
        return REDIS_PORT;
    }

    protected static String getRedisHostSpecialPm() {
        return SPECIAL_PM_REDIS_HOST;
    }

    protected static String getRedisPasswordSpecialPm() {
        return SPECIAL_PM_REDIS_PASS;
    }

    protected static int getRedisPortSpecialPm() {
        return SPECIAL_PM_REDIS_PORT;
    }
}
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REDIS_HOST` | `redis-demo.bookingpal.org` | Demo environment Redis host |
| `REDIS_PASS` | `c&8p8v+[3XRF$mMy` | Demo environment Redis password |
| `REDIS_PORT` | `6380` | Demo environment Redis port |
| `SPECIAL_PM_REDIS_HOST` | `redis-demo.bookingpal.org` | Demo Special PM (same as main) |
| `SPECIAL_PM_REDIS_PASS` | `c&8p8v+[3XRF$mMy` | Demo Special PM password |
| `SPECIAL_PM_REDIS_PORT` | `6380` | Demo Special PM port |

**Difference from Production:** `getRedisHostSpecialPm()` takes **no** `isNewServer` parameter — the old/new server distinction does not exist in test.

---

### `ClusterPropertiesForTest` — Test Cluster (AWS ElastiCache)

**File:** `com.mybookingpal.redis.client.ClusterPropertiesForTest`

Configuration for connecting to an AWS ElastiCache Redis Cluster in the test environment. Extends the basic host/port/password with cluster-specific parameters.

```java
package com.mybookingpal.redis.client;

public class ClusterPropertiesForTest {

    private static final String REDIS_HOST = "clustercfg.redis-cluster-with-auth.tzltk6.use1.cache.amazonaws.com";
    private static final String REDIS_PASS = "kdKY3YTFtAypk8yb";
    private static final int REDIS_PORT = 6379;
    private static final int MAX_ATTEMPTS = 5;
    private static final int CONNECTION_TIMEOUT = 5000;
    private static final boolean SSL_CONNECTION = true;

    protected static String getRedisHost() {
        return REDIS_HOST;
    }

    protected static String getRedisPassword() {
        return REDIS_PASS;
    }

    protected static int getRedisPort() {
        return REDIS_PORT;
    }

    protected static int getMaxAttempts() {
        return MAX_ATTEMPTS;
    }

    protected static int getConnectionTimeout() {
        return CONNECTION_TIMEOUT;
    }

    protected static boolean isSsl() {
        return SSL_CONNECTION;
    }
}
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REDIS_HOST` | `clustercfg.redis-cluster-with-auth.tzltk6.use1.cache.amazonaws.com` | AWS ElastiCache cluster config endpoint |
| `REDIS_PASS` | `kdKY3YTFtAypk8yb` | Cluster auth password |
| `REDIS_PORT` | `6379` | Cluster port |
| `MAX_ATTEMPTS` | `5` | Max retry attempts for cluster topology refresh |
| `CONNECTION_TIMEOUT` | `5000` | Connection timeout in milliseconds |
| `SSL_CONNECTION` | `true` | Enable SSL/TLS for in-transit encryption |

---

### `MrtQuoteClusterProperties` — Marriott Quote Production Cluster

**File:** `com.mybookingpal.redis.client.MrtQuoteClusterProperties`

Production configuration for the Marriott (MRT) channel quote caching cluster. Structurally identical to `ClusterPropertiesForTest` but points to the production ElastiCache cluster with different credentials.

```java
package com.mybookingpal.redis.client;

public class MrtQuoteClusterProperties {

    private static final String REDIS_HOST = "clustercfg.redis-prod-cluster-with-auth.tzltk6.use1.cache.amazonaws.com";
    private static final String REDIS_PASS = "myP3hSULTMg7&$]2";
    private static final int REDIS_PORT = 6379;
    private static final int MAX_ATTEMPTS = 5;
    private static final int CONNECTION_TIMEOUT = 5000;
    private static final boolean SSL_CONNECTION = true;

    protected static String getRedisHost() {
        return REDIS_HOST;
    }

    protected static String getRedisPassword() {
        return REDIS_PASS;
    }

    protected static int getRedisPort() {
        return REDIS_PORT;
    }

    protected static int getMaxAttempts() {
        return MAX_ATTEMPTS;
    }

    protected static int getConnectionTimeout() {
        return CONNECTION_TIMEOUT;
    }

    protected static boolean isSsl() {
        return SSL_CONNECTION;
    }
}
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REDIS_HOST` | `clustercfg.redis-prod-cluster-with-auth.tzltk6.use1.cache.amazonaws.com` | Production ElastiCache cluster config endpoint |
| `REDIS_PASS` | `myP3hSULTMg7&$]2` | Production cluster auth password |
| `REDIS_PORT` | `6379` | Production cluster port |
| `MAX_ATTEMPTS` | `5` | Max retry attempts |
| `CONNECTION_TIMEOUT` | `5000` | Connection timeout in milliseconds |
| `SSL_CONNECTION` | `true` | SSL/TLS enabled |

---

### `BpQuoteProperties` — BookingPal Quote Redis

**File:** `com.mybookingpal.redis.client.BpQuoteProperties`

Configuration for the BookingPal (BP) channel quote caching. Uses a single-node ElastiCache replica endpoint (not a cluster). This is the simplest properties class — only host, password, and port.

```java
package com.mybookingpal.redis.client;

public class BpQuoteProperties {

    private static final String REDIS_HOST = "replica.redis-prod-bp-product-quote.tzltk6.use1.cache.amazonaws.com";
    private static final String REDIS_PASS = "fMKJ2nv8kDedyezc";
    private static final int REDIS_PORT = 6379;

    protected static String getRedisHost() {
        return REDIS_HOST;
    }

    protected static String getRedisPassword() {
        return REDIS_PASS;
    }

    protected static int getRedisPort() {
        return REDIS_PORT;
    }
}
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REDIS_HOST` | `replica.redis-prod-bp-product-quote.tzltk6.use1.cache.amazonaws.com` | BP quote ElastiCache replica endpoint |
| `REDIS_PASS` | `fMKJ2nv8kDedyezc` | BP quote Redis password |
| `REDIS_PORT` | `6379` | BP quote Redis port |

**Note:** The endpoint uses `replica.` prefix indicating read-replica connectivity. No SSL or cluster parameters are defined — the `BpQuoteLettuceClient` handles SSL independently.

---

## RedisClientManager — Configuration Consumer

**File:** `com.mybookingpal.redis.client.RedisClientManager`

This is the central factory that transforms properties into live `IRedisClient` instances. It uses the **double-checked locking** pattern (DCL) with `synchronized` blocks for thread-safe lazy initialization.

### Static Client Instances

| Field | Type | Properties Source | Client Implementation |
|-------|------|-------------------|---------------------|
| `redisClient` | `IRedisClient` | `Properties` | `LettuceClient` |
| `shiroRedisClient` | `IRedisClient` | `ShiroProperties` | `ShiroJedisClient` |
| `specialPmClient` | `IRedisClient` | `Properties` | `SpecialPmClient` |
| `mrtQuoteRedisClient` | `IRedisClient` | `MrtQuoteClusterProperties` | `MrtQuoteLettuceClusterClient` |
| `bpQuoteRedisClient` | `IRedisClient` | `BpQuoteProperties` | `BpQuoteLettuceClient` |

### Factory Methods

#### `getRedisClient()`
Creates a `LettuceClient` using `Properties.getRedisHost()`, `Properties.getRedisPassword()`, `Properties.getRedisPort()`. Used for general-purpose Redis operations.

#### `getShiroRedisClient()`
Creates a `ShiroJedisClient` using `ShiroProperties` values. Note this uses **Jedis** (not Lettuce) — the only client that does so in production.

#### `getSpecialPmClient(Boolean isNewServer)`
Creates a `SpecialPmClient` with the `isNewServer` flag passed through to `Properties.getRedisHostSpecialPm(isNewServer)`. **Caveat:** The `specialPmClient` field is static and only initialized once. If first called with `isNewServer=false`, subsequent calls with `isNewServer=true` will return the client connected to the old server. The first call wins.

#### `getMrtQuoteRedisClient()`
Creates a `MrtQuoteLettuceClusterClient` passing all six parameters from `MrtQuoteClusterProperties`: host, password, port, maxAttempts, connectionTimeout, and SSL flag.

#### `getBpQuoteRedisClient()`
Creates a `BpQuoteLettuceClient` passing host, password, and port from `BpQuoteProperties`.

#### `getClientByChannel(String channel)`
Channel-based routing for quote caching:
- If `channel` equals `"MRT"` (case-insensitive) - returns `getMrtQuoteRedisClient()`
- For any other value - returns `getBpQuoteRedisClient()`

This is the **single entry point** for quote caching consumers that operate across channels.

#### `close()`
Gracefully closes all five client instances. Each close is wrapped in its own try-catch to ensure one failure does not prevent closing the others. Errors are logged but not re-thrown.

---

## Configuration Data Flow

```
Properties Classes              RedisClientManager
                                
Properties                 -->  getRedisClient()
                                -> LettuceClient
                                
ShiroProperties             -->  getShiroRedisClient()
                                -> ShiroJedisClient
                                
Properties (Special PM)    -->  getSpecialPmClient(bool)
                                -> SpecialPmClient
                                
MrtQuoteClusterProperties  -->  getMrtQuoteRedisClient()
                                -> MrtQuoteLettuceClusterClient
                                
BpQuoteProperties           -->  getBpQuoteRedisClient()
                                -> BpQuoteLettuceClient
                                
                                getClientByChannel(str)
                                -> MRT -> MRT client
                                -> other -> BP client
                                
                                close()
                                -> closes all 5 clients

PropertiesForTest           (unused by manager - used by test clients)
ClusterPropertiesForTest   (unused by manager - used by test clients)
```

**Key Observation:** `PropertiesForTest` and `ClusterPropertiesForTest` are **not consumed by `RedisClientManager`**. They are used directly by the test client classes (`JedisTestClient`, `LettuceClusterTestClient`, `SpecialPmTestClient`) which are separate from the production client hierarchy.

---

## Build Configuration (pom.xml)

### Maven Coordinates

| Element | Value |
|---------|-------|
| GroupId | `com.mybookingpal` |
| ArtifactId | `redis` |
| Version | `${module.version}` (default `1.0-SNAPSHOT`) |
| Java Version | 8 (source and target) |
| Packaging | `jar` |

### Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| `redis.clients:jedis` | `2.9.0` | Jedis client (used by `JedisClient`, `ShiroJedisClient`) |
| `io.lettuce:lettuce-core` | `5.1.2.RELEASE` | Lettuce client (used by `LettuceClient`, `BpQuoteLettuceClient`, `MrtQuoteLettuceClusterClient`) |
| `com.fasterxml.jackson.core:jackson-databind` | `2.8.11` | JSON serialization for `RedisObjectSerializer` |
| `log4j:log4j` | `1.2.17` | Logging implementation |
| `org.slf4j:slf4j-log4j12` | `1.7.30` | SLF4J binding to Log4j |

### Maven Profiles

| Profile ID | Module Version | Intended Use |
|-----------|---------------|--------------|
| `demo` | `1.0.demo-SNAPSHOT` | Demo environment deployment |
| `demo_stable` | `1.0.demo_stable-SNAPSHOT` | Stabilized demo deployment |
| `prod` | `1.0-SNAPSHOT` | Production deployment (default) |
| `prod_readonly` | `1.0-SNAPSHOT` | Production read-only instance |
| `test_demo` | `1.0.test_demo-SNAPSHOT` | Test demo environment |

> **Important:** Maven profiles only control the **artifact version string** — they do **not** switch which properties class is used. The choice between `Properties` and `PropertiesForTest` is determined by which client class is instantiated (production vs. test client classes), not by Maven profile activation.

### Repository and Distribution

- **Repository:** `https://repo.mybookingpal.com/repository/s3mbp-group/`
- **Distribution:** Snapshots published to `https://repo.mybookingpal.com/repository/s3mbp-snapshot/`

---

## Environment Comparison Matrix

| Property | Production | Demo/Test |
|----------|-----------|-----------|
| Main Redis Host | `redis.bookingpal.org` | `redis-demo.bookingpal.org` |
| Main Redis Port | `6379` | `6380` |
| Main Redis Password | `b!mS+mt9UFJ!8v]W` | `c&8p8v+[3XRF$mMy` |
| Shiro Redis Host | `redis-shiro.bookingpal.org` | *(not separated)* |
| Special PM Old Host | `redis-redawning.bookingpal.org` | `redis-demo.bookingpal.org` |
| Special PM New Host | `172.16.1.166` | *(N/A)* |
| Special PM Port | `6379` | `6380` |
| MRT Cluster Host | `clustercfg.redis-prod-cluster-with-auth...` | `clustercfg.redis-cluster-with-auth...` |
| MRT Cluster SSL | `true` | `true` |
| MRT Cluster Timeout | `5000ms` | `5000ms` |
| BP Quote Host | `replica.redis-prod-bp-product-quote...` | *(not separated)* |

---

## Configuration Properties Hierarchy

The properties classes fall into three tiers based on the parameters they expose:

### Tier 1: Basic (Host + Password + Port)
- `Properties` (main + Special PM subset)
- `ShiroProperties`
- `PropertiesForTest`
- `BpQuoteProperties`

### Tier 2: Extended Basic (Host + Password + Port + Special PM with old/new)
- `Properties` — full interface includes `getRedisHostSpecialPm(Boolean)`

### Tier 3: Cluster (Host + Password + Port + MaxAttempts + ConnectionTimeout + SSL)
- `MrtQuoteClusterProperties`
- `ClusterPropertiesForTest`

There is **no shared base class or interface** among these properties classes. Each is fully independent with its own copy of the constant definitions and accessor methods.

---

## Known Limitations and Design Notes

1. **No externalized configuration:** All connection parameters are compile-time constants. Changing a Redis host or password requires a code change, recompilation, and redeployment.

2. **Credentials in source code:** Passwords are stored as string literals in Java source files. These are visible in version control, build artifacts, and decompiled class files.

3. **`specialPmClient` singleton caveat:** Since `specialPmClient` is a static field initialized once via DCL, the `isNewServer` parameter only has effect on the first call. Subsequent calls ignore the parameter.

4. **No Spring integration:** Despite being a `com.mybookingpal` module, the configuration uses no Spring annotations (`@Component`, `@ConfigurationProperties`, `@Value`). `RedisClientManager` is a plain Java singleton with static methods.

5. **Test properties disconnected from manager:** `PropertiesForTest` and `ClusterPropertiesForTest` are consumed only by dedicated test client classes, not by `RedisClientManager`. This means there is no single switch to flip between production and test configurations at the manager level.

6. **No connection pool configuration exposed:** Connection pool settings (if any) are embedded within the client constructors, not in the properties classes.