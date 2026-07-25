# Foundation Layer Module Documentation

**Project:** AI Trading Operating System (AITOS)

**Layer:** Foundation

**Version:** 1.0.0

**Status:** Frozen

---

# Module Overview

The Foundation Layer is organized into small, single-responsibility modules. Each module provides reusable infrastructure services and remains independent of higher application layers.

---

# 1. constants.py

## Purpose

Defines system-wide immutable constants shared across the application.

## Responsibilities

- System metadata
- Default configuration values
- File extensions
- Encoding constants
- Timezone constants
- Logging defaults
- Version constants

## Dependencies

- Python Standard Library only

## Public Exports

- `SYSTEM_NAME`
- `SYSTEM_SHORT_NAME`
- `API_VERSION`
- `EVENT_SCHEMA_VERSION`
- `DEFAULT_TEXT_ENCODING`
- `DEFAULT_TIMEZONE`
- `DEFAULT_LOGGER_NAME`
- `DEFAULT_LOG_FORMAT`
- `DEFAULT_DATE_FORMAT`
- `DEFAULT_CONFIG_FILENAME`
- File extension constants

---

# 2. enums.py

## Purpose

Provides strongly typed enumerations used throughout the system.

## Responsibilities

- Standardized states
- Log levels
- Environments
- Health status
- Exit codes
- Severity levels
- Plugin lifecycle states

## Dependencies

- Python `enum`

## Public Enums

- `LogLevel`
- `Environment`
- `PluginState`
- `ComponentState`
- `HealthStatus`
- `ExitCode`
- `Severity`
- `SortOrder`
- `Enablement`
- `SingletonStatus`

---

# 3. exceptions.py

## Purpose

Provides a unified exception hierarchy for the Foundation Layer.

## Responsibilities

- Common base exception
- Configuration errors
- Validation errors
- Plugin errors
- Serialization errors
- Resource errors
- Logger errors

## Public Exceptions

- `FoundationError`
- `ConfigurationError`
- `ValidationError`
- `PluginError`
- `SerializationError`
- `DeserializationError`
- `LoggerError`
- `ResourceError`
- `TimeoutError`
- `UnsupportedOperationError`

---

# 4. config_manager.py

## Purpose

Centralized configuration loading and access.

## Responsibilities

- Load YAML configuration
- Dot-notation key lookup
- Required configuration validation
- Singleton configuration access
- Export configuration

## Public Interface

`ConfigManager`

### Key Methods

- `load()`
- `get()`
- `require()`
- `contains()`
- `as_dict()`
- `clear()`

---

# 5. logger.py

## Purpose

Provides standardized application logging.

## Responsibilities

- Structured logging
- File logging
- Console logging
- Log level management
- Exception logging

## Public Interfaces

- `ILogger`
- `ProductionLogger`

---

# 6. base_event.py

## Purpose

Defines the immutable base class for all system events.

## Responsibilities

- Event identity
- Event metadata
- Correlation identifiers
- UTC timestamps
- Serialization support

## Public Interface

`BaseEvent`

---

# 7. base_plugin.py

## Purpose

Defines the contract for all plugins.

## Responsibilities

- Plugin lifecycle
- Health reporting
- State management

## Public Interface

`BasePlugin`

### Lifecycle

- Created
- Initialized
- Running
- Stopped
- Failed

---

# 8. models/base_model.py

## Purpose

Provides a common immutable base model.

## Responsibilities

- UUID generation
- UTC creation timestamp
- Serialization
- Equality

## Public Interface

`BaseModel`

---

# 9. models/version.py

## Purpose

Represents semantic version information.

## Responsibilities

- Semantic version parsing
- Comparison
- Validation
- String formatting

## Public Interface

`Version`

---

# 10. models/metadata.py

## Purpose

Stores immutable metadata shared across Foundation components.

## Responsibilities

- Tags
- Attributes
- Owner information
- Descriptions

## Public Interface

`Metadata`

---

# 11. utils/validation.py

## Purpose

Provides reusable validation helpers.

## Responsibilities

- Required values
- Identifier validation
- UUID validation
- Event name validation
- Semantic version validation
- Collection validation

## Public Functions

- `require_not_none()`
- `require_not_empty()`
- `require_positive()`
- `require_non_negative()`
- `require_unique()`
- `validate_uuid()`
- `validate_identifier()`
- `validate_event_name()`
- `validate_semantic_version()`

---

# 12. utils/serialization.py

## Purpose

Provides JSON serialization utilities.

## Responsibilities

- Object serialization
- Object deserialization
- File persistence
- Deep cloning

## Public Functions

- `to_json()`
- `from_json()`
- `write_json()`
- `read_json()`
- `clone()`

---

# 13. utils/time.py

## Purpose

Provides standardized UTC-based time utilities.

## Responsibilities

- UTC timestamps
- ISO-8601 conversion
- Unix timestamp conversion
- Duration calculations
- Expiration checks

## Public Functions

- `utc_now()`
- `utc_today()`
- `to_iso8601()`
- `from_iso8601()`
- `unix_timestamp()`
- `from_unix_timestamp()`
- `elapsed()`
- `seconds_between()`
- `is_expired()`
- `add_duration()`
- `subtract_duration()`

---

# 14. utils/id_generator.py

## Purpose

Generates unique identifiers for Foundation components.

## Responsibilities

- UUID generation
- Event IDs
- Correlation IDs
- Trace IDs
- Session IDs
- Request IDs
- Plugin IDs

## Public Functions

- `generate_uuid()`
- `generate_event_id()`
- `generate_correlation_id()`
- `generate_trace_id()`
- `generate_session_id()`
- `generate_request_id()`
- `generate_plugin_id()`

---

# Module Dependency Rules

- Modules may depend only on the Python Standard Library or approved Foundation modules.
- Circular dependencies are prohibited.
- No module may depend on Communication, Data, Intelligence, Execution, Analytics, or Dashboard layers.
- Public interfaces are considered frozen and must not be modified without Chief Architect approval.

---

# Summary

The Foundation Layer consists of fourteen focused modules providing reusable infrastructure for the AI Trading Operating System. Each module adheres to SOLID principles, uses strong typing, and exposes a stable public API for downstream layers.