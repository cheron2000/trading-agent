# Security Policy — AI Trading OS v1.0.1

## Supported Versions

| Version | Supported |
|---|---|
| v1.0.1 | ✅ Active |
| v1.0.0 | ⚠️ Upgrade to v1.0.1 (security patch) |

---

## Security Architecture

### 1. Path Traversal Protection (CWE-22)

All file I/O operations resolve paths with `Path(...).resolve()` before use, preventing `../` traversal attacks.

| File | Protection |
|---|---|
| `foundation/logger.py` | `Path(log_file).resolve()` before `FileHandler` |
| `foundation/utils/serialization.py` | `.resolve()` in `write_json` and `read_json` |
| `foundation/utils/validation.py` | `_safe_resolve()` helper — checks resolved path stays inside base dir |
| `foundation/config_manager.py` | `.resolve()` + `TypeError/ValueError` guard |
| `data/providers/market_provider.py` | `.resolve()` in `_load_fixture` |

### 2. ReDoS Protection (CWE-1333)

All regular expressions in `foundation/utils/validation.py` use bounded quantifiers — no nested `+` or `*` that could cause catastrophic backtracking.

| Pattern | Bound |
|---|---|
| `_IDENTIFIER_PATTERN` | `{0,127}` — max 128-char identifiers |
| `_EVENT_NAME_PATTERN` | `{0,63}` per segment, `{1,8}` segments max |
| `_SEMVER_PATTERN` | `{0,9}` on version numbers, `{0,127}` on metadata |

### 3. Exception Logging (CWE-396)

No exceptions are silently swallowed. All `except` blocks either re-raise or log with `_log.exception(...)` / `_log.warning(...)` including context (job_id, symbol).

### 4. LLM Prompt Injection Protection

- `PromptBuilder` uses only sorted numeric feature values — no raw external text reaches the LLM prompt
- `LLMAgent` parses strict JSON only — never regex-scrapes free text
- Any deviation from the expected JSON schema raises `ValueError` immediately

### 5. Immutable Event Models

All cross-layer event models use `@dataclass(frozen=True, slots=True)` — events cannot be mutated in-flight by any subscriber.

### 6. Tamper-Evident Trade Journal

`TradeJournal` uses SHA-256 hash chains. Any modification to a past entry breaks all subsequent hashes, detectable via `verify_integrity()`.

### 7. Read-Only Configuration

`ConfigManager` wraps all loaded config in `MappingProxyType` — config values cannot be overwritten at runtime.

### 8. Live Trading Hard Block

`OrderManager(live_mode=True)` raises `NotImplementedError` by design. Real-money execution is impossible until this guard is explicitly removed after paper trading validation and compliance sign-off.

### 9. Secrets Never Committed

`.gitignore` blocks: `.env`, `*.env`, `secrets.yaml`, `credentials.json`, `*.pem`, `*.key`

### 10. YAML Safe Load

`ConfigManager` uses `yaml.safe_load()` — never `yaml.load()` — preventing arbitrary Python object deserialization.

### 11. Supply Chain

All dependencies are pinned to exact versions in `requirements.txt`. No unpinned `>=` ranges.

---

## Known Gaps & Roadmap

| Gap | Severity | Planned Fix |
|---|---|---|
| No EventBus rate limiting | MEDIUM | Phase 2 — add per-source publisher throttle |
| No EventBus subscription authentication | MEDIUM | Phase 2 — add allowlist for subscriber patterns |
| No secrets vault integration | HIGH (future) | Required before any live broker adapter is wired |
| Symbol string not validated against allowlist | LOW | Add `_FIXTURE_SYMBOLS` allowlist check in `RiskEngine` |

---

## Reporting a Vulnerability

Open a GitHub issue tagged `security`. Do **not** include exploit code or credentials in public issues.

---

## Vulnerability History

| Version | CVE/CWE | Severity | Status |
|---|---|---|---|
| v1.0.1 | CWE-22 Path Traversal × 5 | HIGH | ✅ Fixed |
| v1.0.1 | CWE-396 Swallowed Exception | HIGH | ✅ Fixed |
| v1.0.1 | CWE-1333 ReDoS | MEDIUM | ✅ Fixed |
