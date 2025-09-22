from hypothesis import given
from hypothesis import strategies as st

from Adventorator.ask_nlu import parse_and_tag
from Adventorator.schemas import AskReport

alpha_space = st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu")) | st.just(" "), min_size=0, max_size=40)


@given(alpha_space)
def test_parse_and_tag_deterministic_alpha_inputs(s: str):
    # Ensure function is deterministic for simple alpha/space inputs
    intent1, tags1 = parse_and_tag(s)
    intent2, tags2 = parse_and_tag(s)

    assert intent1 == intent2
    assert [t.model_dump() for t in tags1] == [t.model_dump() for t in tags2]

    # Ensure AskReport round-trip is stable
    r1 = AskReport(raw_text=s, intent=intent1, tags=tags1)
    same = AskReport.from_json(r1.to_json())
    assert same.intent == intent1
    assert [t.model_dump() for t in same.tags] == [t.model_dump() for t in tags1]
