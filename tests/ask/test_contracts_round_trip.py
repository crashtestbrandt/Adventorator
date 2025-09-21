from Adventorator.schemas import AffordanceTag, AskReport, IntentFrame


def test_ask_report_round_trip_minimal():
    report = AskReport(
        raw_text="attack the goblin",
        intent=IntentFrame(action="attack", actor_ref=None, target_ref="goblin"),
        tags=[AffordanceTag(key="action.attack")],
    )
    s = report.to_json()
    same = AskReport.from_json(s)
    assert same == report
    # ensure exclude_none removed nulls
    assert "null" not in s


def test_ask_report_round_trip_full():
    report = AskReport(
        raw_text="quickly shoot the nearest guard",
        intent=IntentFrame(
            action="shoot", actor_ref="char:123", target_ref="npc:guard_12", modifiers=["quickly"]
        ),
        tags=[
            AffordanceTag(key="action.shoot", confidence=1.0),
            AffordanceTag(key="target.npc", value="npc:guard_12", confidence=0.9),
        ],
    )
    s = report.to_json()
    same = AskReport.from_json(s)
    assert same == report
