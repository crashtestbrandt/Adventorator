# Phase 6 Implementation Plan (content ingestion & retrieval)

**Goal:** Ingest adventure content into normalized nodes and retrieve safe, player-visible context to augment the orchestrator—no GM-only leaks.

**Milestones (small PRs)**
1) Data model and flags
- Add content nodes with player vs GM fields and tags.
- Add feature flags to config for retrieval provider and top_k.

````python
# ...existing code...
from sqlalchemy import String, Text, Enum
from sqlalchemy.dialects.postgresql import JSONB
import enum

class NodeType(str, enum.Enum):
    location = "location"
    npc = "npc"
    encounter = "encounter"
    lore = "lore"

class ContentNode(Base):
    __tablename__ = "content_nodes"
    id = sa.Column(sa.Integer, primary_key=True)
    campaign_id = sa.Column(sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False, index=True)
    node_type = sa.Column(Enum(NodeType), nullable=False, index=True)
    title = sa.Column(String(200), nullable=False)
    player_text = sa.Column(Text, nullable=False)     # safe for players
    gm_text = sa.Column(Text, nullable=True)          # NEVER surfaced to players
    tags = sa.Column(JSONB, nullable=True)            # ["underdark","trap","level-1"]
    # Optional: store sparse metadata for retrieval filtering
# ...existing code...
````

````python
# ...existing code...
from typing import Literal
from pydantic import BaseModel

class RetrievalConfig(BaseModel):
    enabled: bool = False
    provider: Literal["pgvector", "qdrant", "none"] = "none"
    top_k: int = 4

class Features(BaseModel):
    # ...existing code...
    retrieval: RetrievalConfig = RetrievalConfig()
# ...existing code...
````

- Add Alembic migration for content_nodes (id, campaign_id, node_type, title, player_text, gm_text, tags).

2) Retriever interface and provider stubs
- Keep provider-agnostic interface now; plug pgvector/Qdrant later. Start with keyword BM25/LIKE fallback to unblock end-to-end tests.

````python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ContentSnippet:
    id: int
    node_type: str
    title: str
    text: str  # player-visible only

class BaseRetriever:
    async def retrieve(self, campaign_id: int, query: str, k: int = 4) -> List[ContentSnippet]:
        raise NotImplementedError

class SqlFallbackRetriever(BaseRetriever):
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def retrieve(self, campaign_id: int, query: str, k: int = 4) -> List[ContentSnippet]:
        from .models import ContentNode  # import at use-site for tests
        async with self._session_maker() as s:
            q = (
                await s.execute(
                    sa.select(ContentNode)
                    .where(ContentNode.campaign_id == campaign_id)
                    .where(sa.or_(
                        ContentNode.title.ilike(f"%{query[:128]}%"),
                        ContentNode.player_text.ilike(f"%{query[:128]}%"),
                    ))
                    .limit(k)
                )
            ).scalars().all()
        return [ContentSnippet(id=n.id, node_type=n.node_type.value, title=n.title, text=n.player_text) for n in q]

def build_retriever(cfg, session_maker) -> BaseRetriever:
    if not cfg.features.retrieval.enabled or cfg.features.retrieval.provider == "none":
        return SqlFallbackRetriever(session_maker)
    # TODO: return PgVectorRetriever or QdrantRetriever based on cfg
    return SqlFallbackRetriever(session_maker)
````

3) Orchestrator integration (redaction by construction)
- Inject retriever and load top-k snippets. Only player_text is ever concatenated into prompts. Keep behind feature flag.

````python
# ...existing code...
from .retrieval import build_retriever
# ...existing code...

async def run_orchestrator(scene_id: int, player_msg: str, sheet_info_provider, llm_client=None, allowed_actors=None, config=None):
    # ...existing code...
    # Retrieve campaign_id for scene, then fetch retrieval snippets if enabled
    retrieval_snippets = []
    if config and getattr(config.features, "retrieval", None):
        retriever = build_retriever(config, db.session_scope)  # db import at module top if present
        # campaign_id resolved earlier in your plumbing
        retrieval_snippets = await retriever.retrieve(campaign_id, player_msg, k=config.features.retrieval.top_k)

    # Build LLM context bundle: recent turns + character sheet + retrieval_snippets
    # Only include snippet.text (player_text) — NEVER gm_text.
    # ...existing code that builds prompts...
````

4) Import pipeline (minimal)
- Add a simple CLI to import Markdown into ContentNode with a required node_type and visibility split. Start with a conservative parser.

````python
import asyncio, argparse
from pathlib import Path
from src.Adventorator.db import session_scope
from src.Adventorator.models import ContentNode, NodeType

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-id", type=int, required=True)
    ap.add_argument("--node-type", type=str, choices=[t.value for t in NodeType], required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--file", type=Path, required=True, help="Markdown file with player-visible content")
    args = ap.parse_args()

    text = args.file.read_text(encoding="utf-8")
    async with session_scope() as s:
        s.add(ContentNode(
            campaign_id=args.campaign_id,
            node_type=NodeType(args.node_type),
            title=args.title,
            player_text=text,
            gm_text=None,
            tags=[],
        ))

if __name__ == "__main__":
    asyncio.run(main())
````

5) Safety guardrails
- Redaction by schema: never pass gm_text to the LLM or to players.
- Enforce max prompt size and snippet count; filter by campaign_id and optional node_type.
- Add unit tests that assert no gm_text can be surfaced (positive/negative tests).

Tests to add
- tests/test_retrieval_sql_fallback.py: retrieval returns only player_text; respects campaign_id; truncates long queries.
- tests/test_orchestrator_retrieval_integration.py: when retrieval is enabled, snippets are included in context and LLM is fed only redacted text.
- tests/test_import_content.py: basic ingestion populates ContentNode.

Decision points for provider
- Start with SqlFallbackRetriever to validate UX and safety.
- If Postgres is primary in Phase 5, add pgvector with cosine distance; else add Qdrant client. Keep via the retriever interface to avoid API bleed into handlers/orchestrator.

Operational notes
- Feature flag: config.features.retrieval.enabled; opt-in only.
- Metrics: count retrieval.calls, retrieval.hits, retrieval.latency_ms in metrics.py.
- Logging: structured logs at boundaries (ingest, retrieve, orchestrator prompt build) with request_id.

Phase 6 acceptance
- Top-k includes relevant node in canned tests.
- Zero GM-only leakage (unit test enforces).
- Degraded mode: if vector DB down, fallback to SQL retriever or last session summary only (already available via transcripts).