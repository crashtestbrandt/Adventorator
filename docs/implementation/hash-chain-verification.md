# Hash Chain Verification Guide

This guide demonstrates how to use the hash chain verification functionality implemented in STORY-CDA-CORE-001C.

## Overview

The hash chain verification system ensures tamper-evident event history by validating that each event's `prev_event_hash` correctly links to the previous event's computed envelope hash.

## API Reference

### verify_hash_chain(events)

Verifies hash chain integrity for a list of events.

```python
from Adventorator.events.envelope import verify_hash_chain, HashChainMismatchError

# Get events from database (must be from same campaign)
events = await get_campaign_events_for_verification(session, campaign_id=123)

try:
    result = verify_hash_chain(events)
    print(f"Verification: {result['status']}")
    print(f"Verified {result['verified_count']} of {result['chain_length']} events")
except HashChainMismatchError as e:
    print(f"Hash mismatch at ordinal {e.ordinal}")
    print(f"Expected: {e.expected_hash.hex()[:16]}")
    print(f"Actual: {e.actual_hash.hex()[:16]}")
```

**Returns:** Dict with keys:
- `status`: "success" if verification passes
- `verified_count`: Number of events successfully verified
- `chain_length`: Total number of events in the input

**Raises:** `HashChainMismatchError` when corruption is detected

### get_campaign_events_for_verification(session, campaign_id)

Convenience function to retrieve all events for a campaign in the correct order.

```python
from Adventorator import repos

async with session_scope() as session:
    events = await repos.get_campaign_events_for_verification(
        session, 
        campaign_id=123
    )
    result = verify_hash_chain(events)
```

## Observability

### Metrics

- **events.hash_mismatch**: Counter incremented when corruption is detected
- **events.applied**: Counter for successfully persisted events

### Structured Logging

Hash mismatches generate structured logs with event `event.chain_mismatch`:

```json
{
  "stage": "event",
  "event": "chain_mismatch", 
  "campaign_id": 123,
  "replay_ordinal": 42,
  "event_type": "attack",
  "expected_hash": "a1b2c3d4e5f67890",
  "actual_hash": "deadbeefcafebabe"
}
```

## Fault Injection Testing

For testing hash chain verification:

```python
# Create normal events
events = [event1, event2, event3]

# Inject corruption
events[1].prev_event_hash = b"corrupted_hash_test" + b"\x00" * 13

# Verify detection
with pytest.raises(HashChainMismatchError):
    verify_hash_chain(events)

assert get_counter("events.hash_mismatch") == 1
```

## Performance Characteristics

- Verification of 100 events completes in <5 seconds
- Memory usage scales linearly with event count
- Automatically sorts events by replay_ordinal for robust verification

## Genesis Event Handling

The first event in any campaign chain (replay_ordinal=0) links to the genesis hash:

```python
from Adventorator.events.envelope import GENESIS_PREV_EVENT_HASH

# First event should link to genesis
assert first_event.prev_event_hash == GENESIS_PREV_EVENT_HASH
```

## Error Scenarios

Common verification failures:

1. **Database corruption**: Hardware/software failure modifying stored hashes
2. **Implementation bugs**: Incorrect hash computation during event creation  
3. **Race conditions**: Concurrent modifications bypassing chain locks
4. **Migration issues**: Schema changes affecting hash computation

All failures trigger immediate alerts via the `events.hash_mismatch` metric.