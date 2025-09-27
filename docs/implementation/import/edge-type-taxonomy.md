# Edge type taxonomy

This taxonomy captures the approved edge types for STORY-CDA-IMPORT-002C readiness and documents the attributes that must be
present on each edge prior to ingestion.

| Edge type | Description | Required attributes | Optional attributes | Temporal validity |
| --- | --- | --- | --- | --- |
| `npc.resides_in.location` | NPC lives or is stationed at a specific location. | `relationship_context` | `duty_schedule` | Optional |
| `organization.controls.location` | Organization exerts operational control over a location. | `charter_clause`, `oversight` | *(none)* | Required |

The JSON representation used by tests and tooling is stored at
[`contracts/edges/edge-type-taxonomy-v1.json`](../../../contracts/edges/edge-type-taxonomy-v1.json). The `validity_required` field in that
artifact drives readiness tests that assert whether the optional `validity` block must be present for a given edge type.

The rules team has confirmed that these types cover the initial edge ingestion scope for campaign topology packages and provide
sufficient metadata to seed downstream graph services.
