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


def test_reset_counters_handles_failures(monkeypatch):
    from Adventorator import metrics

    metrics.inc_counter("example")
    metrics.observe_histogram("latency", 42)

    original_cb = getattr(metrics, "_reset_plan_cache_cb", None)

    def _boom():
        raise RuntimeError("callback fail")

    def _restore_callback():
        metrics._reset_plan_cache_cb = original_cb  # noqa: SLF001

    metrics.register_reset_plan_cache_callback(_boom)

    def _plan_reset():
        raise RuntimeError("plan reset fail")

    monkeypatch.setattr(
        "Adventorator.action_validation.plan_registry.reset",
        _plan_reset,
    )

    class _BadRateLimiter(dict):
        def clear(self):  # type: ignore[override]
            raise RuntimeError("rl clear fail")

    monkeypatch.setattr(
        "Adventorator.commands.plan._rl",
        _BadRateLimiter({"user": 1}),
        raising=False,
    )

    try:
        metrics.reset_counters()
    finally:
        _restore_callback()
        metrics.reset_counters()

    assert metrics.get_counter("example") == 0
    assert metrics.get_counters() == {}


def test_observe_histogram_overflow_bucket():
    from Adventorator import metrics

    metrics.reset_counters()
    metrics.observe_histogram("latency", 10_000, buckets=[1, 5, 10])

    counters = metrics.get_counters()
    try:
        assert counters["histo.latency.gt_10"] == 1
        assert counters["histo.latency.sum"] == 10_000
        assert counters["histo.latency.count"] == 1
    finally:
        metrics.reset_counters()


@pytest.mark.asyncio
async def test_event_apply_latency_timing(db):
    """Test that event apply operations record latency histogram."""
    from Adventorator import metrics, repos

    metrics.reset_counters()

    # Setup campaign/scene
    camp = await repos.get_or_create_campaign(db, 1, name="Latency Test")
    scene = await repos.ensure_scene(db, camp.id, 300)

    # Append an event (should record latency)
    await repos.append_event(
        db,
        scene_id=scene.id,
        actor_id="latency_actor",
        type="latency_test",
        payload={"test": "latency_measurement"},
        request_id="latency_req",
    )

    # Check that latency histogram was recorded
    counters = metrics.get_counters()

    # Should have latency histogram entries
    latency_keys = [k for k in counters.keys() if k.startswith("histo.event.apply.latency_ms")]
    assert len(latency_keys) > 0, (
        f"Expected latency histogram entries, got: {list(counters.keys())}"
    )

    # Should have count and sum
    assert "histo.event.apply.latency_ms.count" in counters
    assert "histo.event.apply.latency_ms.sum" in counters
    assert counters["histo.event.apply.latency_ms.count"] == 1
    assert counters["histo.event.apply.latency_ms.sum"] > 0  # Should be positive

    # Should also have events.applied counter incremented
    assert counters["events.applied"] == 1
