"""hook-analyzer, offline, on fake example data. The AI call is replaced.

    python3 -m pytest skills/fulfilment/hook-analyzer -q
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

for _up in Path(__file__).resolve().parents:
    _kit = [k for k in (_up / "skills/_kit", _up / "core/skills/_kit") if (k / "skillkit.py").exists()]
    if _kit:
        sys.path.insert(0, str(_kit[0]))
        break
import skill_fakes as fakes  # noqa: E402
import pytest  # noqa: E402
import skillkit  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hook_analyzer_under_test", str(SKILL / "scripts/hook_analyzer.py"))
ha = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ha)

TODAY = date(2026, 11, 11)
ANSWER = {"score": 6, "verdict": "Clear, but slow.", "what_works": ["It names one problem."],
          "what_to_fix": ["The greeting delays the point."], "rewrite": "Your gums bleed? Stop doing this.",
          "other_rewrites": ["One brushing mistake makes gums bleed."]}


@pytest.fixture
def ai(monkeypatch):
    calls = []

    def fake_ask(prompt, system="", schema=None, **kw):
        calls.append({"prompt": prompt, "schema": schema})
        return dict(ANSWER)

    monkeypatch.setattr(skillkit, "ask_ai", fake_ask)
    return calls


def make_db() -> fakes.FakeDB:
    return fakes.FakeDB({
        "videos": [{"id": "v1", "video_title": "Bleeding gums", "client_id": "c-acme", "platform": "TikTok",
                    "stage": "20 - Editing", "notes": "Client wants it short.", "feedback_notes": "Cut at 0:12."}],
        "documents": [{"id": "d1", "client_id": "c-acme", "board": "videos", "card_id": "v1", "field_key": "caption",
                       "body_md": "Hi everyone! Do your gums bleed when you brush? Here is the one mistake to stop."}],
    })


def test_card_check_with_save_adds_to_notes_only(ai, capsys):
    db, slack = make_db(), fakes.FakeSlack()
    assert ha.main(["--card", "v1", "--save"], db=db, today=TODAY) == 0
    card = db.tables["videos"][0]
    assert card["notes"].startswith("Client wants it short.\n\nHook check, 2026-11-11: 6/10. Clear, but slow.")
    assert "Rewrite: Your gums bleed? Stop doing this." in card["notes"]
    assert card["feedback_notes"] == "Cut at 0:12."           # the editor's notes are left alone
    assert db.writes == [("update", "videos", "v1")]           # one write, to the card only
    assert slack.posts == []                                   # it posts nothing
    assert "Do your gums bleed" in ai[0]["prompt"] and "TikTok" in ai[0]["prompt"]
    assert ai[0]["schema"]["required"][0] == "score"
    assert "Score: 6/10" in capsys.readouterr().out


def test_without_save_nothing_is_written(ai):
    db = make_db()
    assert ha.main(["--card", "v1"], db=db, today=TODAY) == 0
    assert db.writes == []


def test_opening_strips_timestamps_and_keeps_the_first_words():
    srt = "1\n00:00:00,000 --> 00:00:02,000\nStop brushing like this.\n\n2\n00:00:02,000 --> 00:00:04,000\nHere is why."
    assert ha.opening(srt, 40) == "Stop brushing like this. Here is why."
    assert ha.opening("[00:01] one two three four five", 3) == "one two three"


def test_score_is_kept_between_1_and_10(monkeypatch):
    monkeypatch.setattr(skillkit, "ask_ai", lambda *a, **k: dict(ANSWER, score=14))
    assert ha.check("Do your gums bleed when you brush?")["score"] == 10


def test_empty_caption_is_a_clean_failure_and_nothing_is_spent(ai, capsys):
    db = make_db()
    db.tables["documents"] = []
    assert ha.main(["--card", "v1", "--save"], db=db, today=TODAY) == 2
    assert "no opening to check" in capsys.readouterr().out
    assert ai == [] and db.writes == []


def test_unknown_card_and_save_without_card_stop_plainly(ai, capsys):
    assert ha.main(["--card", "nope"], db=make_db(), today=TODAY) == 2
    assert "No video card has the id nope" in capsys.readouterr().out
    assert ha.main(["--text", "Do your gums bleed?", "--save"], today=TODAY) == 2
    assert "--save needs --card" in capsys.readouterr().out
    assert ai == []
