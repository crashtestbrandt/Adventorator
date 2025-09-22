# Idempotency Key V2 Composition Order Documentation

## Overview

This document defines the composition order for idempotency key v2 as implemented in STORY-CDA-CORE-001D.

## Acceptance Criteria Specification

The idempotency key v2 follows this exact composition order:

```
SHA256(plan_id || campaign_id || event_type || tool_name || ruleset_version || canonical(args_json))[:16]
```

## Implementation Details

### Field Order (Fixed)

1. **plan_id** - Unique plan identifier (nullable, empty string if null)
2. **campaign_id** - Campaign identifier (integer, converted to string)  
3. **event_type** - Event type string (e.g., "tool.execute")
4. **tool_name** - Name of the tool being executed (nullable, empty string if null)
5. **ruleset_version** - Version of ruleset being used (nullable, empty string if null)
6. **args_json** - Canonical JSON-serializable arguments (nullable, empty dict if null)

### Binary Framing

Each field uses length-prefixed binary framing to avoid delimiter collision:

```
For each field:
  - field_label (UTF-8 bytes)
  - field_value_length (4-byte big-endian unsigned integer)
  - field_value (UTF-8 bytes)
```

### Example

```python
compute_idempotency_key_v2(
    plan_id="plan-123",           # "plan-123"
    campaign_id=456,              # "456" 
    event_type="tool.execute",    # "tool.execute"
    tool_name="dice_roll",        # "dice_roll"
    ruleset_version="dnd5e-v1.0", # "dnd5e-v1.0"
    args_json={"sides": 20}       # '{"sides":20}' (canonical JSON)
)
```

### Differences from V1

The v2 composition **removes** these fields from v1:
- `execution_request_id` - Prevented true retry collapse
- `replay_ordinal` - Prevented true retry collapse  
- `payload` - Replaced with `args_json` for input focus

The v2 composition **adds** these fields:
- `tool_name` - Enables tool-specific idempotency
- `ruleset_version` - Enables version-specific idempotency
- `args_json` - Input arguments instead of output payload

## Canonical JSON Processing

The `args_json` field uses the canonical JSON encoder from `Adventorator.canonical_json`:

- UTF-8 NFC Unicode normalization
- Lexicographic key ordering  
- Null field elision
- Integer-only numeric policy (rejects floats/NaN)
- Compact separators

## Testing & Validation

### Composition Order Tests

Tests verify the implementation matches the acceptance criteria:

```python
def test_composition_order_matches_spec():
    # Manually compute expected key using spec order
    # Compare with actual implementation
    assert actual_key == expected_key
```

### Determinism Tests

Tests verify same inputs always produce same keys:

```python
def test_deterministic_behavior():
    key1 = compute_idempotency_key_v2(**args)
    key2 = compute_idempotency_key_v2(**args)
    assert key1 == key2
```

### Sensitivity Tests

Tests verify different inputs produce different keys:

```python
def test_input_sensitivity():
    # Change each field and verify key changes
    for field in ["plan_id", "campaign_id", "event_type", "tool_name", "ruleset_version", "args_json"]:
        # Modify field and verify key differs
```

## Collision Resistance

16-byte keys provide 2^128 possible values:
- Fuzz testing with 10k+ iterations shows zero collisions
- Expected collision probability negligible for practical use
- Birthday paradox threshold much higher than expected usage

## Migration from V1

Migration strategy preserves existing events:

1. **No rewrite** - Legacy events keep legacy keys
2. **Feature flag** - Shadow computation for validation period
3. **Executor integration** - Query by v2 key for new operations
4. **Gradual rollout** - Remove shadow logic after stabilization

## Implementation Location

- **Function**: `compute_idempotency_key_v2()` in `src/Adventorator/events/envelope.py`
- **Tests**: `tests/test_idempotency_key_v2.py`
- **Fuzz Tests**: `tests/test_collision_fuzz.py`
- **Retry Tests**: `tests/test_retry_storm_harness.py`

## Usage Example

```python
from Adventorator.events.envelope import compute_idempotency_key_v2

# Compute key for tool execution
key = compute_idempotency_key_v2(
    plan_id="plan-abc123",
    campaign_id=12345,
    event_type="tool.execute",
    tool_name="dice_roll",
    ruleset_version="dnd5e-v1.1",
    args_json={
        "sides": 20,
        "count": 1,
        "modifier": 3,
        "advantage": False
    }
)

# Use key for idempotency check
existing_event = query_by_idempotency_key(campaign_id, key)
if existing_event:
    return existing_event  # Idempotent reuse
else:
    return create_new_event(...)  # New execution
```