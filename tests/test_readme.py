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
