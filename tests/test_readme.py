"""README stays plain UTF-8 without mojibake."""

from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"



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
    assert f"**Reveal** ({config.AI_SOLVER_COST} coins)" in coins
    assert "red" in coins                           # prices you can't afford
    assert "levels 1 and 2" in coins
    assert f"pays {config.CLEAR_REWARD} coins" in coins
    assert "clearing a level pays nothing" not in coins
    # Seeing a full answer costs only its price: coins stay, the clear still pays.
    assert "only cost" in coins
    assert "are kept" in coins
    assert "clear reward is still paid" in coins
    assert "taken back" not in coins
    assert "receives no clear reward" not in coins
    assert "do not pay out" not in coins


def test_readme_documents_unbound():
    text = README.read_text(encoding="utf-8")
    rules = text.split("## Run", 1)[0]
    unbound = rules.split("**Unbound**", 1)[1]
    assert "never goes out of bounds" in unbound
    assert "twice the map" not in unbound and "±20 m" not in unbound
    assert "Diverged" in unbound
    assert "every life" in unbound
    assert "outside the map" in unbound and "level start" in unbound
    assert "shield" in unbound.lower()


def test_readme_documents_the_daily_challenge():
    text = README.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "\n## Daily Challenge" in text
    daily = text.split("## Daily Challenge", 1)[1].split("\n## ", 1)[0]
    for name in ("DAILY_LEVEL_ID", "DAILY_GENERATOR_VERSION", "DAILY_UTC_OFFSET_HOURS",
                 "DAILY_TIME_LIMIT", "DAILY_LIVES", "DAILY_MAX_ATTEMPTS"):
        assert name in daily
    assert "same for every player" in daily
    assert "Taiwan time" in daily and "UTC+8" in daily
    assert "answer first" in daily
    assert "once per day" in daily
    assert "Clear reward already collected today" in daily
    coins = text.split("## Coins", 1)[1].split("\n## ", 1)[0]
    assert "Daily Challenge" in coins
