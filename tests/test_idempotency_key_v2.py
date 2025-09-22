"""Tests for idempotency key v2 implementation (STORY-CDA-CORE-001D)."""

import hashlib
from Adventorator.events.envelope import compute_idempotency_key_v2


class TestIdempotencyKeyV2Determinism:
    """Test deterministic behavior of the v2 idempotency key."""

    def test_deterministic_same_inputs(self):
        """Same inputs should always produce same key."""
        args = {
            "plan_id": "plan-123",
            "campaign_id": 456,
            "event_type": "tool.execute",
            "tool_name": "dice_roll",
            "ruleset_version": "dnd5e-v1.0",
            "args_json": {"sides": 20, "count": 1},
        }
        
        key1 = compute_idempotency_key_v2(**args)
        key2 = compute_idempotency_key_v2(**args)
        
        assert key1 == key2
        assert len(key1) == 16
        assert isinstance(key1, bytes)

    def test_null_values_handled(self):
        """Null values should be handled consistently."""
        key1 = compute_idempotency_key_v2(
            plan_id=None,
            campaign_id=123,
            event_type="test.event",
            tool_name=None,
            ruleset_version=None,
            args_json=None,
        )
        
        key2 = compute_idempotency_key_v2(
            plan_id="",
            campaign_id=123, 
            event_type="test.event",
            tool_name="",
            ruleset_version="",
            args_json={},
        )
        
        assert len(key1) == 16
        # Note: None vs empty dict should produce the same key for idempotency
        # since None gets converted to {} and {} stays {} in canonical JSON
        # This ensures that missing args_json behaves the same as empty args_json
        assert key1 == key2

    def test_composition_order_enforced(self):
        """Changing input order should not affect key (fixed parameter order)."""
        # This tests that parameter order doesn't matter since we use kwargs
        kwargs = {
            "args_json": {"damage": "1d6"},
            "campaign_id": 789,
            "event_type": "spell.cast",
            "plan_id": "plan-456", 
            "ruleset_version": "dnd5e-v1.1",
            "tool_name": "spell_checker",
        }
        
        key1 = compute_idempotency_key_v2(**kwargs)
        
        # Create same call with different parameter order (dict iteration is deterministic in Python 3.7+)
        key2 = compute_idempotency_key_v2(
            tool_name="spell_checker",
            plan_id="plan-456",
            args_json={"damage": "1d6"},
            event_type="spell.cast",
            ruleset_version="dnd5e-v1.1",
            campaign_id=789,
        )
        
        assert key1 == key2

    def test_different_inputs_different_keys(self):
        """Different inputs should produce different keys."""
        base_args = {
            "plan_id": "plan-123",
            "campaign_id": 456,
            "event_type": "tool.execute", 
            "tool_name": "dice_roll",
            "ruleset_version": "dnd5e-v1.0",
            "args_json": {"sides": 20, "count": 1},
        }
        
        base_key = compute_idempotency_key_v2(**base_args)
        
        # Test each parameter change produces different key
        for param, new_value in [
            ("plan_id", "plan-456"),
            ("campaign_id", 999),
            ("event_type", "tool.validate"),
            ("tool_name", "other_tool"),
            ("ruleset_version", "dnd5e-v2.0"),
            ("args_json", {"sides": 6, "count": 2}),
        ]:
            modified_args = base_args.copy()
            modified_args[param] = new_value
            modified_key = compute_idempotency_key_v2(**modified_args)
            
            assert modified_key != base_key, f"Changing {param} should produce different key"


class TestIdempotencyKeyV2CompositionOrder:
    """Test that the internal composition order matches acceptance criteria."""

    def test_composition_order_mismatch_detection(self):
        """Test can detect if internal order doesn't match specification.
        
        The acceptance criteria specify:
        SHA256(plan_id || campaign_id || event_type || tool_name || ruleset_version || canonical(args_json))[:16]
        """
        args = {
            "plan_id": "test-plan",
            "campaign_id": 123,
            "event_type": "test.action",
            "tool_name": "test_tool", 
            "ruleset_version": "v1.0",
            "args_json": {"test": "value"},
        }
        
        actual_key = compute_idempotency_key_v2(**args)
        
        # Manually compute what the key should be based on acceptance criteria order
        from Adventorator.canonical_json import canonical_json_bytes
        
        components = [
            ("plan_id", args["plan_id"].encode("utf-8")),
            ("campaign_id", str(args["campaign_id"]).encode("utf-8")),
            ("event_type", args["event_type"].encode("utf-8")),
            ("tool_name", args["tool_name"].encode("utf-8")),
            ("ruleset_version", args["ruleset_version"].encode("utf-8")),
            ("args_json", canonical_json_bytes(args["args_json"])),
        ]
        
        framed = []
        for label, value in components:
            framed.append(label.encode("utf-8"))
            framed.append(len(value).to_bytes(4, "big", signed=False))
            framed.append(value)
        
        expected_key = hashlib.sha256(b"".join(framed)).digest()[:16]
        
        assert actual_key == expected_key, "Implementation order must match acceptance criteria"


class TestBackwardCompatibility:
    """Test that v2 keys are distinct from v1 keys."""

    def test_v1_v2_keys_different(self):
        """V1 and V2 keys should be different for equivalent inputs."""
        from Adventorator.events.envelope import compute_idempotency_key
        
        # Create overlapping parameters
        campaign_id = 123
        event_type = "test.event"
        plan_id = "plan-456"
        payload = {"test": "data"}
        
        v1_key = compute_idempotency_key(
            campaign_id=campaign_id,
            event_type=event_type,
            execution_request_id="req-123",
            plan_id=plan_id,
            payload=payload,
            replay_ordinal=1,
        )
        
        v2_key = compute_idempotency_key_v2(
            plan_id=plan_id,
            campaign_id=campaign_id,
            event_type=event_type,
            tool_name="test_tool",
            ruleset_version="v1.0",
            args_json=payload,
        )
        
        assert v1_key != v2_key, "V1 and V2 should produce different keys"
        assert len(v1_key) == len(v2_key) == 16