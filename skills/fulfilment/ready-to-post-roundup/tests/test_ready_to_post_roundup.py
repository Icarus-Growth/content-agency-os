"""ready-to-post-roundup, offline, on fake example data.

    python3 -m pytest skills/fulfilment/ready-to-post-roundup -q
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

SKILL = Path(__file__).resolve().parents[1]


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, str(SKILL / "scripts" / file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rtp = _load("ready_to_post_under_test", "ready_to_post_roundup.py")
daily = _load("ready_to_post_daily_under_test", "daily.py")

TODAY = date(2026, 11, 11)


def video(vid, title, client, stage="50 - Ready To Post", **kw):
    return dict({"id": vid, "video_title": title, "client_id": client, "stage": stage, "platform": "Instagram",
                 "edited_url": "https://files.example.com/" + vid}, **kw)


def make_db() -> fakes.FakeDB:
    return fakes.FakeDB({
        "settings": [{"id": 1, "os_url": "https://os.example.com"}],
        "team": [{"id": "t-jane", "full_name": "Jane Doe", "slack_user_id": "member-jane"},
                 {"id": "t-sam", "full_name": "Sam Lee"}],
        "clients": [
            {"id": "c-acme", "client_name": "Acme Dental", "social_media_manager_id": "t-jane",
             "slack_channel_id": "client-channel-acme"},
            {"id": "c-bright", "client_name": "Bright Smiles", "account_manager_id": "t-sam"},
            {"id": "c-gone", "client_name": "Gone Client", "archived_at": "2026-10-01T00:00:00Z"},
        ],
        "videos": [
            video("v1", "Three tips for whiter teeth", "c-acme", due_date="2026-11-12"),
            video("v2", "Meet the team", "c-acme", stage="60 - Scheduled", scheduled_for=None),
            video("v3", "Already booked in", "c-acme", stage="60 - Scheduled",
                  scheduled_for="2026-11-12T09:00:00Z"),
            video("v4", "Before and after", "c-bright", edited_url=None),
            video("v5", "Still editing", "c-bright", stage="20 - Editing"),
            video("v6", "Archived card", "c-bright", archived_at="2026-11-01T00:00:00Z"),
            video("v7", "Client archived", "c-gone"),
        ],
    })


def test_one_post_with_a_thread_per_client_and_links():
    db, slack, seen = make_db(), fakes.FakeSlack(), {}
    out = daily.run(db, slack, fakes.FakeConfig(), seen, TODAY)
    assert out == {"ok": True, "videos": 3, "clients": 2, "posted": True}
    main, acme, bright = slack.posts
    assert main["channel"] == "chan-approved" and "3 videos for 2 clients" in main["text"]
    assert main["blocks"][1]["elements"][0]["url"] == "https://os.example.com/tasks/videos"
    assert acme["thread_ts"] == bright["thread_ts"] == "ts-1"
    assert acme["text"].startswith("*Acme Dental* (<@member-jane>)")
    assert "<https://os.example.com/board/videos/v1|Three tips for whiter teeth>" in acme["text"]
    assert "<https://files.example.com/v1|the file>" in acme["text"] and "due Thu 12 Nov" in acme["text"]
    assert "Meet the team" in acme["text"] and "scheduled, but no time set" in acme["text"]
    assert "Already booked in" not in acme["text"]
    assert bright["text"].startswith("*Bright Smiles* (Sam Lee)") and "no edited file linked" in bright["text"]
    every = " ".join(p["text"] for p in slack.posts)
    for gone in ("Still editing", "Archived card", "Client archived"):
        assert gone not in every
    assert all("client-channel" not in p["channel"] for p in slack.posts)
    assert db.writes == []  # it moves no card


def test_once_a_day_and_silent_when_nothing_is_ready():
    db, slack, seen = make_db(), fakes.FakeSlack(), {}
    daily.run(db, slack, fakes.FakeConfig(), seen, TODAY)
    assert daily.run(db, slack, fakes.FakeConfig(), seen, TODAY)["skipped"] == "already posted today"
    assert len(slack.posts) == 3

    empty, slack2 = fakes.FakeDB({"videos": []}), fakes.FakeSlack()
    assert daily.run(empty, slack2, fakes.FakeConfig(), {}, TODAY)["posted"] is False and slack2.posts == []
    cfg = dict(rtp.load_config(), post_when_empty=True)
    rtp.run(empty, slack2, fakes.FakeConfig(), {}, TODAY, cfg=cfg)
    assert [p["text"] for p in slack2.posts] == ["*Ready to post:* nothing is ready today."]


def test_board_that_cannot_be_read_is_one_clean_failure():
    db = make_db()
    db.fail_on["videos"] = RuntimeError("permission denied")
    slack = fakes.FakeSlack()
    out = daily.run(db, slack, fakes.FakeConfig(), {}, TODAY)
    assert out["ok"] is False
    assert [p["channel"] for p in slack.posts] == ["chan-pipeline-errors"]
    assert db.writes == []
