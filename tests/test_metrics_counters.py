import pytest

from Adventorator.metrics import get_counter, reset_counters
from Adventorator.orchestrator import run_orchestrator
from Adventorator.schemas import LLMOutput, LLMProposal


class _FakeLLM:
    def __init__(self, out):
        self._out = out

    async def generate_json(self, msgs, system_prompt=None):
        return self._out


@pytest.mark.asyncio
async def test_metrics_happy_flow(monkeypatch):
    # Arrange: valid output
    out = LLMOutput(
        proposal=LLMProposal(action="ability_check", ability="DEX", suggested_dc=10, reason="ok"),
        narration="You move deftly.",
    )
    llm = _FakeLLM(out)

    # Minimal transcripts
    from Adventorator import repos

    async def _get_recent(*a, **k):
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", _get_recent)

    reset_counters()
    res = await run_orchestrator(
        scene_id=2,
        player_msg="I act (reject)",
        rng_seed=1,
        llm_client=llm,
    )
    assert not res.rejected
    # Assert counters
    assert get_counter("llm.request.enqueued") == 1
    assert get_counter("llm.response.received") == 1
    assert get_counter("orchestrator.format.sent") == 1


@pytest.mark.asyncio
async def test_metrics_rejection_path(monkeypatch):
    # Arrange: bad ability causes defense rejection
    out = LLMOutput(
        proposal=LLMProposal(action="ability_check", ability="XXX", suggested_dc=10, reason="bad"),
        narration="—",
    )
    llm = _FakeLLM(out)

    from Adventorator import repos

    async def _get_recent(*a, **k):
        return []

    monkeypatch.setattr(repos, "get_recent_transcripts", _get_recent)

    reset_counters()
    res = await run_orchestrator(
        scene_id=1,
        player_msg="I act",
        rng_seed=1,
        llm_client=llm,
    )
    assert res.rejected
    assert get_counter("llm.request.enqueued") == 1
    assert get_counter("llm.response.received") == 1
    assert get_counter("llm.defense.rejected") == 1
