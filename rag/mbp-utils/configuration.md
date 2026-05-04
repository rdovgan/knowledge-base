---
module: mbp-utils
Domain: configuration
generated_at: 2023-10-27T10:00:00Z
status: approved
review_score: 1.0
attempts: 1
---

# Configuration Domain

The **Configuration** domain for the `mbp-utils` module encompasses the build settings, Maven project object model (POM) configuration, and architectural constraints governing the module's compilation and distribution. Unlike other domains focused on Java logic, this domain defines the structural environment in which the utility code exists and is compiled.

## Overview

The `mbp-utils` module is designed as a foundational library for the MyBookingPal platform. Its primary configuration goal is to provide a lightweight, dependency-free JAR that can be safely imported into any other module within the ecosystem without risking version conflicts or circular dependencies.

### Key Characteristics

*   **Packaging**: JAR (Java Archive)
*   **Java Version**: Java 8 (Source and Target compatibility)
*   **Dependency Policy**: Strictly **Zero Dependencies**. No external libraries are imported.
*   **Build Tool**: Apache Maven

## Maven Coordinates

The module is identified by the following Group, Artifact, and Version (GAV) coordinates within the internal Maven repository.

| Element | Value |
| :--- | :--- |
| **GroupId** | `com.mybookingpal` |
| **ArtifactId** | `utils` |
| **Version** | `1.0-SNAPSHOT` |

## Build Configuration

The build process is managed via Maven. The configuration explicitly targets Java 8 to ensure compatibility across the various legacy and modern services in the MyBookingPal infrastructure.

### Compiler Plugin

The `maven-compiler-plugin` is configured to enforce Java 8 bytecode compatibility.

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <source>8</source>
        <target>8</target>
    </configuration>
</plugin>
```

## Architectural Constraints: Zero Dependency Policy

The most critical configuration rule for `mbp-utils` is the prohibition of external dependencies.

### The Rule

> **DO NOT IMPORT ANY DEPENDENCY TO THIS MODULE.**

### Rationale

As stated in the project documentation:

> *"Current module was implemented to move entities and utils classes that often used, to one place. It will be included in each mbp module."*

If this module were to import a third-party library (e.g., Jackson, Apache Commons, Guava), it would force that dependency onto every consuming module. This could lead to:

1.  **Jar Hell**: Conflicts if different modules require different versions of the same transitive dependency.
2.  **Bloat**: Unnecessary libraries loaded into memory for services that don't use them.
3.  **Circular Dependencies**: If other utility libraries depend on this one, and this one depends on them.

Therefore, any code added to `mbp-utils` must rely **only** on the Java Standard Library (JDK).

### Code Example: Empty Dependencies Section

The `pom.xml` intentionally lacks a `<dependencies>` section. If a developer attempts to add one, it violates the core configuration contract.

```xml
<!-- THIS MODULE WAS IMPLEMENTED TO MOVE ENTITIES OR UTILS CLASSES TO ONE PLACE. 
     IT WILL BE INCLUDED IN EACH MBP MODULE. 
     DO NOT IMPORT ANY DEPENDENCY TO THIS MODULE. -->
<project>
    <!-- ... GAV coordinates ... -->
    
    <!-- Note: No <dependencies> section exists here -->

</project>
```

## Repository Management

The module is not distributed via Maven Central. Instead, it utilizes a custom internal Nexus repository hosted by MyBookingPal.

### Repositories

The build process is configured to resolve artifacts (and potentially plugins, though typically defined in settings.xml) from the internal `s3mbp-group`.

*   **ID**: `mybookingpal-nexus`
*   **Name**: MyBookingPal Nexus
*   **URL**: `https://repo.mybookingpal.com/repository/s3mbp-group/`

```xml
<repositories>
    <repository>
        <id>mybookingpal-nexus</id>
        <name>MyBookingPal Nexus</name>
        <url>https://repo.mybookingpal.com/repository/s3mbp-group/</url>
    </repository>
</repositories>
```

## Distribution Management

The module is configured to deploy snapshot builds to the internal Nexus snapshot repository.

### Snapshot Repository

| Property | Value |
| :--- | :--- |
| **ID** | `mybookingpal-nexus` |
| **URL** | `https://repo.mybookingpal.com/repository/s3mbp-snapshot/` |

```xml
<distributionManagement>
    <snapshotRepository>
        <id>mybookingpal-nexus</id>
        <url>https://repo.mybookingpal.com/repository/s3mbp-snapshot/</url>
    </snapshotRepository>
</distributionManagement>
```

## Full `pom.xml` Reference

Below is the complete source of the configuration file as it exists in the repository.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
		 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
		 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
	<modelVersion>4.0.0</modelVersion>

	<groupId>com.mybookingpal</groupId>
	<artifactId>utils</artifactId>
	<version>1.0-SNAPSHOT</version>
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
	<packaging>jar</packaging>
	<!-- THIS MODULE WAS IMPLEMENTED TO MOVE ENTITIES OR UTILS CLASSES TO ONE PLACE. IT WILL BE INCLUDED IN EACH MBP MODULE.
	 DO NOT IMPORT ANY DEPENDENCY TO THIS MODULE. -->
	<repositories>
		<repository>
			<id>mybookingpal-nexus</id>
			<name>MyBookingPal Nexus</name>
			<url>https://repo.mybookingpal.com/repository/s3mbp-group/</url>
		</repository>
	</repositories>
	<distributionManagement>
		<snapshotRepository>
			<id>mybookingpal-nexus</id>
			<url>https://repo.mybookingpal.com/repository/s3mbp-snapshot/</url>
		</snapshotRepository>
	</distributionManagement>

</project>
```

## Verification and Enforcement

To verify the configuration:

1.  **Dependency Check**: Run `mvn dependency:tree`. The output should show only `org.apache.maven:plugins` and nothing else under `com.mybookingpal:utils`.
2.  **Code Review**: All Pull Requests adding code to this module must verify that no `import` statements reference packages outside of `java.*` or `javax.*` (and specifically `com.mybookingpal.utils` for internal organization).