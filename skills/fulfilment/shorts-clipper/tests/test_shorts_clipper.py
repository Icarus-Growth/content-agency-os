"""shorts-clipper, offline, on fake example data. The AI call is replaced. The ffmpeg test
runs only when ffmpeg is installed.

    python3 -m pytest skills/fulfilment/shorts-clipper -q
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
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
spec = importlib.util.spec_from_file_location("shorts_clipper_under_test", str(SKILL / "scripts/shorts_clipper.py"))
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

TODAY = date(2026, 11, 11)
WORDS = "brushing twice a day is not enough if you skip the gum line every single night"


def srt(n: int = 12, step: int = 5) -> str:
    blocks = []
    for i in range(n):
        a, b = i * step, (i + 1) * step
        blocks.append("{0}\n00:00:{1:02d},000 --> 00:00:{2:02d},000\nPart {0}: {3}\n".format(i + 1, a, b, WORDS))
    return "\n".join(blocks)


@pytest.fixture
def ai(monkeypatch):
    calls = []

    def fake_ask(prompt, system="", schema=None, **kw):
        calls.append(prompt)
        return {"clips": [
            {"start": 5, "end": 30, "title": "The gum line mistake", "hook": "Brushing twice is not enough.",
             "why": "One clear tip with a payoff."},
            {"start": 32, "end": 57, "title": "Night routine", "hook": "Skip this at night and pay later.",
             "why": "A strong warning."},
            {"start": 40, "end": 400, "title": "Too long", "hook": "", "why": ""},
            {"start": 10, "end": 28, "title": "Same part", "hook": "", "why": ""},
        ]}

    monkeypatch.setattr(skillkit, "ask_ai", fake_ask)
    return calls


def make_ctx():
    db = fakes.FakeDB({
        "settings": [{"id": 1, "os_url": "https://os.example.com"}],
        "videos": [{"id": "v1", "video_title": "Gum care talk", "client_id": "c-acme", "notes": "Long talk, 1 hour."}],
    })
    return skillkit.Context(db, fakes.FakeSlack(), fakes.FakeConfig(), {})


def test_parses_srt_vtt_json_and_stamped_lines():
    assert sc.parse_transcript(srt(2))[1] == {"start": 5.0, "end": 10.0, "text": "Part 2: " + WORDS}
    vtt = "WEBVTT\n\n00:01.500 --> 00:04.000 align:start\n<v Sam>Hello there</v>\n"
    assert sc.parse_transcript(vtt) == [{"start": 1.5, "end": 4.0, "text": "Hello there"}]
    js = json.dumps({"segments": [{"start": 0, "end": 2.5, "text": " Hi"}]})
    assert sc.parse_transcript(js) == [{"start": 0.0, "end": 2.5, "text": "Hi"}]
    lines = "[00:10] First idea\n[01:02:03] Later idea"
    assert sc.parse_transcript(lines)[0] == {"start": 10.0, "end": 3723.0, "text": "First idea"}


def test_finds_clips_saves_list_and_tells_the_card(ai, tmp_path, capsys):
    t = tmp_path / "talk.srt"
    t.write_text(srt())
    ctx = make_ctx()
    assert sc.main(["--transcript", str(t), "--card", "v1"], ctx=ctx, today=TODAY) == 0

    saved = json.loads((tmp_path / "talk_clips" / "clips.json").read_text())
    assert [c["title"] for c in saved["clips"]] == ["The gum line mistake", "Night routine"]
    assert saved["clips"][0]["file"] == "clip_01_the-gum-line-mistake.mp4"
    assert any("Too long" in d for d in saved["dropped"]) and any("Same part" in d for d in saved["dropped"])

    notes = ctx.db.tables["videos"][0]["notes"]
    assert notes.startswith("Long talk, 1 hour.\n\nShort clips found, 2026-11-11:")
    assert "1. 0:05 to 0:30 (25s) The gum line mistake." in notes
    assert ctx.db.writes == [("update", "videos", "v1")]
    (post,) = ctx.slack.posts
    assert post["channel"] == "chan-task-updates" and "2 short clips found for Gum care talk" in post["text"]
    assert post["blocks"][1]["elements"][0]["url"] == "https://os.example.com/board/videos/v1"
    assert "[5.0-10.0] Part 2:" in ai[0]


def test_cut_without_ffmpeg_keeps_the_list_and_says_so(ai, tmp_path, monkeypatch, capsys):
    t, v = tmp_path / "talk.srt", tmp_path / "talk.mp4"
    t.write_text(srt())
    v.write_bytes(b"not really a video")
    monkeypatch.setattr(sc.shutil, "which", lambda name: None)
    assert sc.main(["--transcript", str(t), "--video", str(v), "--cut"], ctx=make_ctx(), today=TODAY) == 2
    assert "ffmpeg is not installed" in capsys.readouterr().out
    assert (tmp_path / "talk_clips" / "clips.json").exists()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg is not installed")
def test_ffmpeg_cuts_a_real_vertical_clip(ai, tmp_path):
    video = tmp_path / "talk.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=2",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "60", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-shortest", str(video)], check=True)
    t = tmp_path / "talk.srt"
    t.write_text(srt())
    out = tmp_path / "clips"
    assert sc.main(["--transcript", str(t), "--video", str(video), "--cut", "--vertical", "--out", str(out)],
                   ctx=make_ctx(), today=TODAY) == 0
    clip = out / "clip_01_the-gum-line-mistake.mp4"
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:format=duration", "-of", "json", str(clip)],
                           capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (1080, 1920)
    assert abs(float(info["format"]["duration"]) - 25) < 1.0
    assert (out / "clip_02_night-routine.mp4").exists()


def test_transcript_with_no_times_is_a_clean_failure(ai, tmp_path, capsys):
    t = tmp_path / "talk.txt"
    t.write_text("Just words with no times at all. " * 20)
    ctx = make_ctx()
    assert sc.main(["--transcript", str(t), "--card", "v1"], ctx=ctx, today=TODAY) == 2
    assert "no time stamps" in capsys.readouterr().out
    assert ai == [] and ctx.db.writes == [] and ctx.slack.posts == []
    assert not (tmp_path / "talk_clips").exists()


def test_missing_inputs_stop_plainly(ai, tmp_path, capsys):
    assert sc.main([], ctx=make_ctx()) == 2
    assert "Give a transcript" in capsys.readouterr().out
    assert sc.main(["--transcript", str(tmp_path / "nope.srt")], ctx=make_ctx()) == 2
    assert "There is no transcript file" in capsys.readouterr().out
    assert ai == []
