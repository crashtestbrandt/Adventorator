# Edge package fixture

This fixture bundles manifest, entity, and edge content to exercise the edge ingestion readiness tests.

```
edge_package/
├── package.manifest.json
├── entities/
│   ├── location.grand_library.json
│   ├── npc.edge_liaison.json
│   └── organization.archive_guild.json
└── edges/
    └── edges.json
```

The manifest enables both entity and edge importer phases. Entity files provide deterministic stable IDs used by the sample edges
in `edges/edges.json`. The edge records reference the taxonomy declared in `contracts/edges/edge-type-taxonomy-v1.json` and include
both attribute mappings and a temporal validity example.
