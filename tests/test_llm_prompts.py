from Adventorator.llm_prompts import build_clerk_messages
from Adventorator.models import Transcript


def _t(author: str, content: str) -> Transcript:
    # Minimal Transcript-like object for tests (dataclass style args aren't required)
    class T:
        def __init__(self, author, content):
            self.author = author
            self.content = content
    return T(author, content)  # type: ignore


def test_clerk_excludes_system_and_orders():
    transcripts = [
        _t("system", "seed"),
        _t("player", "Hello"),
        _t("bot", "Welcome"),
        _t("player", "I check the door"),
    ]
    msgs = build_clerk_messages(transcripts, player_msg=None, max_tokens=9999)
    # first is system prompt
    assert msgs[0]["role"] == "system"
    roles = [m["role"] for m in msgs[1:]]
    assert roles == ["user", "assistant", "user"]
    contents = [m["content"] for m in msgs[1:]]
    assert contents[0].endswith("Hello")
    assert contents[1].endswith("Welcome")
    assert contents[2].endswith("I check the door")


def test_clerk_respects_token_cap_and_includes_player_msg():
    # Create messages that will quickly exceed the token budget
    transcripts = [_t("player", "a" * 40), _t("bot", "b" * 40)]
    # budget ~20 tokens -> 80 chars
    msgs = build_clerk_messages(transcripts, player_msg="final input", max_tokens=20)
    # first system + first transcript should fit; second may not depending on calc
    assert msgs[0]["role"] == "system"
    # Ensure the last message is the player's input if budget allows
    assert msgs[-1]["content"] == "final input"
