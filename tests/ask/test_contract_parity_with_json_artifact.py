from pathlib import Path

from Adventorator.schemas import AskReport


def test_askreport_schema_parity_with_contract():
    # Generate Pydantic JSON schema and compare structure with contract artifact
    model_schema = AskReport.model_json_schema()

    # Load contract JSON
    contract_path = Path("contracts/ask/v1/ask-report.v1.json")
    assert contract_path.exists(), "Contract artifact missing"
    import json

    with contract_path.open("r", encoding="utf-8") as f:
        contract = json.load(f)

    # Validate key structural elements match
    props = contract["properties"]
    assert set(props.keys()) == {"version", "raw_text", "intent", "tags"}

    # Intent properties
    intent_props = props["intent"]["properties"]
    assert set(intent_props.keys()) == {"action", "actor_ref", "target_ref", "modifiers"}

    # Ensure additionalProperties are disallowed in Pydantic model schemas
    # Pydantic v2 uses 'additionalProperties': False when extra='forbid'
    assert model_schema.get("additionalProperties", False) is False
    # Check nested models also set additionalProperties to False
    # Find IntentFrame definition by scanning definitions/components
    defs = model_schema.get("$defs") or model_schema.get("definitions") or {}
    found_intent = False
    for _, d in defs.items():
        expected = {"action", "actor_ref", "target_ref", "modifiers"}
        if isinstance(d, dict) and set(d.get("properties", {}).keys()) == expected:
            assert d.get("additionalProperties", False) is False
            found_intent = True
            break
    assert found_intent, "IntentFrame definition not found in generated schema"
