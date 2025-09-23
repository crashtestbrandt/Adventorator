# Knowledge Base (KB) Integration

## Overview

The KB (Knowledge Base) integration provides read-only entity resolution for the `/ask` command flow. It leverages existing repository data to resolve entity references and suggest alternatives, with built-in caching and metrics.

## Feature Flags

The KB integration requires two feature flags to be enabled:

```toml
[features]
improbability_drive = true
ask = { enabled = true, kb_lookup = true }
```

### Flag Hierarchy
- `features.improbability_drive` - Master flag for the ImprobabilityDrive epic
- `features.ask.kb_lookup` - Specific flag for KB entity resolution

When either flag is disabled, the KB integration is completely bypassed with no side effects.

## Configuration

KB behavior is configured under the `[ask.kb]` section:

```toml
[ask.kb]
timeout_s = 0.05              # Per-query timeout in seconds
max_candidates = 5            # Maximum candidates returned per query
cache_ttl_s = 60             # Cache entry time-to-live in seconds
cache_max_size = 1024        # Maximum number of cached entries
max_terms_per_call = 20      # Maximum terms processed in bulk operations
```

### Configuration Defaults

All configuration values have safe defaults that preserve performance:

- **timeout_s**: 0.05s - Very short timeout to avoid blocking user interactions
- **max_candidates**: 5 - Reasonable number of alternatives without overwhelming users
- **cache_ttl_s**: 60s - Balance between freshness and performance 
- **cache_max_size**: 1024 - Sufficient for typical usage patterns
- **max_terms_per_call**: 20 - Prevents abuse while supporting realistic bulk operations

## Data Sources

The KB adapter queries existing repository data in a deterministic order:

1. **Character names** (primary source for canonical entities)
   - Exact matches become canonical IDs (`character:<id>`)
   - Partial matches become candidates

2. **Campaign names** (secondary source)
   - Used when character matches don't fill the candidate limit
   - Exact matches can become canonical if no character match found

### Deterministic Behavior

- Results are sorted with exact matches first, then alphabetically
- Given the same seed data, results are always identical
- Cache keys are normalized (case-insensitive, whitespace-trimmed)

## Cache Behavior

### TTL-Based Eviction
- Entries expire after `cache_ttl_s` seconds
- Expired entries are lazily removed on access
- Manual eviction occurs when cache reaches size limit

### Size-Based Eviction
- When cache reaches `cache_max_size`, oldest entries are evicted
- LRU (Least Recently Used) eviction policy
- Eviction events are tracked via `kb.cache.evicted` metric

### Cache Keys
Cache keys include the normalized term and limit parameter:
```
single:<normalized_term>:<limit>
```

Different limits create separate cache entries to ensure correct result counts.

## Metrics

The KB integration emits several metrics for observability:

### Counter Metrics
- `kb.lookup.hit` - Cache hits
- `kb.lookup.miss` - Cache misses  
- `kb.lookup.timeout` - Query timeouts
- `kb.cache.evicted` - Cache evictions
- `kb.lookup.integration_error` - Integration errors (non-fatal)

### Usage Patterns
- **High hit ratio**: Indicates good cache effectiveness
- **High timeout rate**: May indicate need to increase `timeout_s` or investigate DB performance
- **High eviction rate**: May indicate need to increase `cache_max_size` or `cache_ttl_s`

## API

### Single Entity Resolution
```python
from Adventorator.kb.adapter import resolve_entity

result = await resolve_entity("gandalf", limit=5, timeout_s=0.1)
print(f"Canonical: {result.canonical_id}")
print(f"Candidates: {[c.label for c in result.candidates]}")
```

### Bulk Resolution
```python
from Adventorator.kb.adapter import bulk_resolve

results = await bulk_resolve(
    ["gandalf", "frodo", "guard"], 
    limit=3, 
    timeout_s=0.05,
    max_terms=10
)
```

### Result Structure
```python
@dataclass(frozen=True)
class KBResolution:
    canonical_id: str | None      # Exact match ID or None
    candidates: list[Candidate]   # Alternative matches
    reason: str | None           # Human-readable explanation
    source: str                  # Always "repo" for this implementation

@dataclass(frozen=True) 
class Candidate:
    id: str      # Entity identifier (e.g., "character:123")
    label: str   # Human-readable label
```

## Integration with /ask Flow

When enabled, the KB integration runs after NLU parsing:

1. Extract entity terms from `intent.target_ref` and non-action tags
2. Perform bulk KB resolution with configured limits/timeouts
3. Log results for observability
4. Include resolution summary in debug output (when `nlu_debug=true`)

The integration never fails the user flow - errors are logged and metrics recorded, but the command continues normally.

## Rollback Procedure

To disable KB integration:

### Immediate Disable
```toml
[features.ask]
kb_lookup = false
```

### Complete Disable
```toml
[features]
improbability_drive = false
```

### Verification Steps
1. Restart service after config change
2. Run `/ask` command and verify no KB-related metrics increment
3. Check logs for absence of "kb_lookup" events
4. Verify normal `/ask` functionality preserved

## Troubleshooting

### High Timeout Rate
- **Symptom**: `kb.lookup.timeout` metric increasing
- **Solutions**: 
  - Increase `timeout_s` (careful not to block user interactions)
  - Investigate database query performance
  - Reduce `max_candidates` to limit query complexity

### Cache Ineffectiveness  
- **Symptom**: Low hit ratio (`kb.lookup.hit` / total lookups)
- **Solutions**:
  - Increase `cache_ttl_s` if data freshness allows
  - Increase `cache_max_size` if memory permits
  - Check for inconsistent entity term normalization

### Integration Errors
- **Symptom**: `kb.lookup.integration_error` metric increasing
- **Solutions**:
  - Check logs for specific error details
  - Verify database connectivity and schema
  - Ensure proper async session handling

## Performance Considerations

### Query Patterns
- Character name lookups use ILIKE for fuzzy matching
- Queries are limited by `max_candidates` to prevent large result sets
- Bulk operations respect `max_terms_per_call` to prevent resource exhaustion

### Memory Usage
- Cache size is bounded by `cache_max_size` entries
- Each cache entry contains small result objects
- Typical memory usage: ~1KB per cached entry

### Database Impact
- Read-only queries with LIMIT clauses
- No transactions or locks
- Queries timeout quickly to prevent blocking

## Testing

### Unit Tests
- `tests/kb/test_kb_resolution.py` - Determinism and ordering
- `tests/kb/test_kb_cache.py` - Cache behavior and metrics
- `tests/kb/test_kb_limits.py` - Timeout and bounds enforcement

### Test Fixtures
- `tests/kb/fixtures/golden_resolution.json` - Expected results for deterministic testing

### Manual Testing
1. Enable feature flags in config
2. Use `/ask` with entity terms that exist in your database
3. Enable `nlu_debug=true` to see KB resolution results
4. Monitor metrics via `/metrics` endpoint

## Future Enhancements

### Planned Improvements
- Write operations for KB mutation (future epic)
- External service integration (beyond repo-backed data)
- Enhanced entity types and relationship resolution
- Machine learning-based relevance scoring

### Configuration Extensions
Additional knobs may be added for:
- Custom entity type priorities
- Advanced caching strategies  
- Query optimization parameters
- Integration with retrieval systems