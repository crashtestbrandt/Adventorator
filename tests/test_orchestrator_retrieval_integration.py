from __future__ import annotations

import types

import pytest

from Adventorator.db import session_scope
from Adventorator.models import Campaign, ContentNode, NodeType, Scene, Transcript
from Adventorator.orchestrator import run_orchestrator


class FakeLLM:
    async def generate_json(self, messages):
        # Minimal object mimicking LLMOutput type with the required fields
        class Proposal(types.SimpleNamespace):
            def model_dump(self):
                return {
                    "action": "ability_check",
                    "ability": "DEX",
                    "suggested_dc": 10,
                    "reason": "sneaking past guards",
                }

        class Out(types.SimpleNamespace):
            proposal = Proposal(
                action="ability_check",
                ability="DEX",
                suggested_dc=10,
                reason="sneak",
            )
            narration = "You move quietly along the wall."

        return Out()


@pytest.mark.asyncio
async def test_orchestrator_uses_retrieval_player_only(db):
    # Prepare scene and transcripts
    async with session_scope() as s:
        camp = Campaign(name="C1")
        s.add(camp)
        await s.flush()
        sc = Scene(campaign_id=camp.id, channel_id=123)
        s.add(sc)
        await s.flush()
        s.add(
            ContentNode(
                campaign_id=camp.id,
                node_type=NodeType.location,
                title="Guard Post",
                player_text="Two guards watch the corridor.",
                gm_text="They are sleepy and DC 8 to distract.",
                tags=["guards"],
            )
        )
        s.add(
            Transcript(
                campaign_id=camp.id,
                scene_id=sc.id,
                channel_id=123,
                author="player",
                author_ref="u1",
                content="I sneak past.",
                meta={},
            )
        )

    class Settings(types.SimpleNamespace):
        class Retrieval(types.SimpleNamespace):
            enabled = True
            provider = "none"
            top_k = 2

        retrieval = Retrieval()

    out = await run_orchestrator(
        scene_id=1,
        player_msg="I sneak past",
        llm_client=FakeLLM(),
        allowed_actors=["Player"],
        settings=Settings(),
    )

    assert not out.rejected
    assert "Check:" in out.mechanics
    # Narration is from FakeLLM, but context building shouldn't crash with retrieval
