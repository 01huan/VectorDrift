"""README stays plain UTF-8 without mojibake."""

from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def test_readme_has_no_bom():
    assert not README.read_bytes().startswith(b"\xef\xbb\xbf")


def test_readme_failure_rules_are_readable():
    text = README.read_text(encoding="utf-8")
    assert "??" not in text
    for rule in ("**Time up**", "**Abort / Out of bounds / Diverged**",
                 "**Invalid mathematical result**", "**Infinite force**"):
        assert f"* ​{rule}​:" in text
    assert "x = ±π/2" in text


def test_readme_documents_the_coin_rules():
    from vector_drift import config
    text = README.read_text(encoding="utf-8")
    assert "\n## Coins" in text.replace("\r\n", "\n")
    coins = text.split("## Coins", 1)[1].split("\n## ", 1)[0]
    assert f"{config.HINT_ANSWER_COST} coins" in coins
    assert f"Reveal ({config.AI_SOLVER_COST} coins)" in coins
    assert "levels 1 and 2" in coins
    assert "taken back" in coins
    assert f"pays {config.CLEAR_REWARD} coins" in coins
    assert "clearing a level pays nothing" not in coins
