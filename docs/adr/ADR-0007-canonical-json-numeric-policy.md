# ADR-0007 Canonical JSON & Numeric Policy

## Status
Proposed (2025-09-21)

## Metadata
Depends On: ADR-0006  
Traceability: Referenced by [ARCH-CDA-001](../architecture/ARCH-CDA-001-campaign-data-architecture.md)

## Context
Hash stability requires canonical byte representation. JSON introduces ambiguity (key order, Unicode normalization, null handling, numeric formats).

## Decision
Canonicalization rules:
- UTF-8 NFC normalization.
- Sort object keys lexicographically (byte order).
- Omit null fields.
- Integers only (signed 64-bit). No floats in event payloads.
- Fixed-point (scale 100) if decimal semantics required (store integer).
- No scientific notation.
- Booleans lowercase; arrays preserve order.
- Large integers > 2^53-1 disallowed in mutation fields (must be strings in non-semantic props).
- Hash: SHA-256 over canonical serialization.

## Rationale
Ensure stable, cross-platform hashing and eliminate numeric / Unicode ambiguity that would undermine ledger hash chain guarantees.

## Consequences
Pros:
- Stable hashing cross-platform.
- Protects against subtle drift.

Cons:
- Additional encoder complexity.
- Need explicit conversion for user-supplied floats.

## References
- ADR-0006 Event Envelope & Hash Chain
- RFC 8785 (JSON Canonicalization Scheme) — inspiration; simplified subset applied

## Test Vectors
10 fixtures stored under `tests/canonical_json/` (Unicode composition, large int edge, nested ordering).

## Enforcement
- Encoder utility used everywhere events hashed.
- CI ensures diff against golden vectors.

## Follow-Up
- Add linter preventing raw `json.dumps` in critical paths.