"""Shorts clipper: finds short clips in a long video from its transcript, and cuts them.

1. The transcript: a file you give (--transcript: .srt, .vtt, a Whisper .json, or text lines
   that start with a time like [01:02]). With no transcript, it runs the free local
   transcriber in config.json (`transcribe_command`, Whisper by default) on --video.
   No paid transcription service is used, so nothing is spent on it.
2. The AI (skillkit.ask_ai, with a JSON schema) picks the clips: start, end, title, hook and
   why. The rules are in references/clip_rules.md. Clips that are too short, too long or
   outside the video are dropped, and the result says why.
3. With --cut, ffmpeg on this computer cuts each clip from --video (--vertical crops to 9:16).
4. The list is saved as clips.json in the output folder. With --card <video id>, the list is
   also added to the card's notes and one line is posted in task-updates.

It runs on the editor's computer (large video files stay local):

    python3 skills/fulfilment/shorts-clipper/scripts/shorts_clipper.py --transcript talk.srt
    python3 skills/fulfilment/shorts-clipper/scripts/shorts_clipper.py --video talk.mp4 --transcript talk.srt --cut --vertical
"""

from __future__ import annotations

import sys
from pathlib import Path

for _up in Path(__file__).resolve().parents:
    _kit = [k for k in (_up / "skills/_kit", _up / "core/skills/_kit") if (k / "skillkit.py").exists()]
    if _kit:
        sys.path.insert(0, str(_kit[0]))
        break
import skillkit  # noqa: E402

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

SKILL = "shorts-clipper"
BOT = "✂️ Shorts Clipper"
SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = SKILL_DIR / "config.json"
RULES_FILE = SKILL_DIR / "references" / "clip_rules.md"
DEFAULTS: Dict[str, Any] = {
    "clip_count": 5, "min_seconds": 20, "max_seconds": 60, "max_transcript_chars": 120000, "max_tokens": 4000,
    "effort": "medium", "vertical_filter": "crop=trunc(ih*9/16/2)*2:ih,scale=1080:1920",
    "ffmpeg_quality": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k"],
    "transcribe_command": ["whisper", "{video}", "--model", "base", "--output_format", "json", "--output_dir", "{out}"],
    "channel": "task-updates",
}
SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"clips": {"type": "array", "items": {
        "type": "object",
        "properties": {"start": {"type": "number"}, "end": {"type": "number"}, "title": {"type": "string"},
                       "hook": {"type": "string"}, "why": {"type": "string"}},
        "required": ["start", "end", "title", "hook", "why"], "additionalProperties": False}}},
    "required": ["clips"], "additionalProperties": False,
}
SYSTEM = ("You are a short-form video editor. You pick the strongest short clips from a long video's transcript. "
          "Use only the time stamps in the transcript. Follow the rules you are given.")
TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?")


class BadInput(ValueError):
    """The input cannot be used. The message says why, in plain words."""


def load_config(path: Path = CONFIG_FILE) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update({k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")})
    if not 0 < float(cfg["min_seconds"]) < float(cfg["max_seconds"]):
        raise BadInput("config.json: 'min_seconds' must be more than 0 and less than 'max_seconds'.")
    return cfg


# --------------------------------------------------------------------------- transcript


def seconds(stamp: str) -> float:
    m = TIME.fullmatch(stamp.strip())
    if not m:
        raise BadInput("This is not a time: {0}".format(stamp))
    h, mi, s, frac = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + (int(frac.ljust(3, "0")) / 1000.0 if frac else 0.0)


def clock(sec: float) -> str:
    sec = int(round(sec))
    return "{0}:{1:02d}:{2:02d}".format(sec // 3600, sec % 3600 // 60, sec % 60) if sec >= 3600 else \
        "{0}:{1:02d}".format(sec // 60, sec % 60)


def parse_transcript(text: str) -> List[Dict[str, Any]]:
    """Segments [{start, end, text}] from SRT, VTT, Whisper JSON or time-stamped lines. Pure."""
    raw = (text or "").strip()
    if not raw:
        raise BadInput("The transcript is empty.")
    if raw[0] in "[{":
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if data is not None:
            segs = data.get("segments") if isinstance(data, dict) else data
            out = [{"start": float(s["start"]), "end": float(s["end"]), "text": str(s.get("text", "")).strip()}
                   for s in segs or [] if isinstance(s, dict) and "start" in s and "end" in s]
            if not out:
                raise BadInput("The JSON transcript has no segments with a start and an end.")
            return out
    out: List[Dict[str, Any]] = []
    if "-->" in raw:  # SRT or VTT
        block: Dict[str, Any] = {}
        for ln in raw.splitlines() + [""]:
            ln = ln.strip()
            if "-->" in ln:
                a, b = [x.strip().split(" ")[0] for x in ln.split("-->", 1)]
                block = {"start": seconds(a), "end": seconds(b), "text": ""}
            elif not ln:
                if block.get("text"):
                    out.append(block)
                block = {}
            elif block and not (ln.isdigit() and not block["text"]):
                block["text"] = (block["text"] + " " + re.sub(r"<[^>]+>", "", ln)).strip()
        return out
    stamped = []
    for ln in raw.splitlines():
        m = re.match(r"^\s*[\[(]?((?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)[\])]?\s*[-:]?\s*(.*)$", ln)
        if m and m.group(2).strip():
            stamped.append((seconds(m.group(1)), m.group(2).strip()))
    if not stamped:
        raise BadInput("The transcript has no time stamps, so clips cannot be timed. "
                       "Use an .srt, .vtt or .json transcript, or lines that start with a time like [01:02].")
    for i, (start, words) in enumerate(stamped):
        end = stamped[i + 1][0] if i + 1 < len(stamped) else start + 5
        out.append({"start": start, "end": end, "text": words})
    return out


def transcribe(video: Path, cfg: Dict[str, Any]) -> str:
    """Runs the free local transcriber from config.json. Returns the transcript text (JSON)."""
    exe = shutil.which(str(cfg["transcribe_command"][0]))
    if not exe:
        raise BadInput("There is no transcript, and the local transcriber '{0}' is not installed. "
                       "Give a transcript with --transcript, or install it (see SKILL.md).".format(
                           cfg["transcribe_command"][0]))
    with tempfile.TemporaryDirectory() as out:
        cmd = [str(p).format(video=str(video), out=out) for p in cfg["transcribe_command"]]
        _run(cmd)
        found = sorted(Path(out).glob("*.json")) or sorted(Path(out).glob("*.srt")) or sorted(Path(out).glob("*.vtt"))
        if not found:
            raise BadInput("The local transcriber made no transcript file. Check `transcribe_command` in config.json.")
        return found[0].read_text(errors="ignore")


def _run(cmd: List[str]) -> None:
    """Runs one local command (ffmpeg or the transcriber). Tests replace this."""
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError("{0} failed: {1}".format(Path(cmd[0]).name, (done.stderr or "").strip()[-300:]))


# --------------------------------------------------------------------------- the clips


def find_clips(segments: List[Dict[str, Any]], cfg: Dict[str, Any], count: int) -> Dict[str, Any]:
    """Asks the AI for clips, then keeps only the ones that fit. Returns {clips, dropped}."""
    lines = ["[{0:.1f}-{1:.1f}] {2}".format(s["start"], s["end"], s["text"]) for s in segments if s["text"]]
    body = "\n".join(lines)[: int(cfg["max_transcript_chars"])]
    if len(body.split()) < 30:
        raise BadInput("The transcript is too short to find clips in (under 30 words).")
    rules = RULES_FILE.read_text() if RULES_FILE.exists() else ""
    prompt = ("Rules:\n{0}\n\nPick up to {1} clips. Each clip is {2} to {3} seconds long. Times are in seconds.\n\n"
              "The transcript, one line per segment as [start-end] words:\n{4}").format(
        rules, count, cfg["min_seconds"], cfg["max_seconds"], body)
    ans = skillkit.ask_ai(prompt, system=SYSTEM, schema=SCHEMA, max_tokens=int(cfg["max_tokens"]),
                          effort=str(cfg["effort"]))
    return check_clips((ans or {}).get("clips") or [], segments, cfg, count)


def check_clips(clips: List[Dict[str, Any]], segments: List[Dict[str, Any]], cfg: Dict[str, Any],
                count: int) -> Dict[str, Any]:
    """Drops clips that are outside the video, too short, too long or overlap a better one. Pure."""
    first, last = min(s["start"] for s in segments), max(s["end"] for s in segments)
    lo, hi = float(cfg["min_seconds"]) * 0.75, float(cfg["max_seconds"]) * 1.25
    keep: List[Dict[str, Any]] = []
    dropped: List[str] = []
    for c in clips:
        try:
            start, end = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            dropped.append("a clip with no start or end")
            continue
        name = c.get("title") or "untitled"
        if start < first - 1 or end > last + 1 or end <= start:
            dropped.append("{0}: outside the video".format(name))
        elif not lo <= end - start <= hi:
            dropped.append("{0}: {1:.0f} seconds long".format(name, end - start))
        elif any(min(end, k["end"]) - max(start, k["start"]) > 0.5 * (end - start) for k in keep):
            dropped.append("{0}: the same part as another clip".format(name))
        else:
            keep.append({"start": round(max(start, first), 2), "end": round(min(end, last), 2), "title": name,
                         "hook": c.get("hook") or "", "why": c.get("why") or ""})
    keep = sorted(keep[:count], key=lambda k: k["start"])
    for i, k in enumerate(keep, 1):
        k["number"] = i
        k["length"] = round(k["end"] - k["start"], 1)
        k["file"] = "clip_{0:02d}_{1}.mp4".format(i, slug(k["title"]))
    return {"clips": keep, "dropped": dropped}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "clip"


def cut_clips(video: Path, clips: List[Dict[str, Any]], out_dir: Path, vertical: bool,
              cfg: Dict[str, Any]) -> List[Path]:
    """Cuts each clip with ffmpeg on this computer. Returns the files made."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise BadInput("ffmpeg is not installed on this computer, so the clips were not cut. "
                       "The clip list is saved. Install ffmpeg (ffmpeg.org), then run it again with --cut.")
    made = []
    for c in clips:
        target = out_dir / c["file"]
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", "{0:.2f}".format(c["start"]),
               "-i", str(video), "-t", "{0:.2f}".format(c["end"] - c["start"])]
        if vertical:
            cmd += ["-vf", str(cfg["vertical_filter"])]
        cmd += [str(x) for x in cfg["ffmpeg_quality"]] + [str(target)]
        _run(cmd)
        made.append(target)
    return made


def notes_block(found: Dict[str, Any], today: date) -> str:
    lines = ["Short clips found, {0}:".format(today.isoformat())]
    for c in found["clips"]:
        lines.append("{0}. {1} to {2} ({3:.0f}s) {4}. Hook: \"{5}\". Why: {6}".format(
            c["number"], clock(c["start"]), clock(c["end"]), c["length"], c["title"], c["hook"], c["why"]))
    return "\n".join(lines)


def save_to_card(ctx: Any, card_id: str, found: Dict[str, Any], cut: bool, today: date) -> None:
    """Adds the clip list to the card's notes and posts one line in task-updates."""
    card = ctx.db.get("videos", card_id)
    if not card:
        raise BadInput("No video card has the id {0}. Copy the id from the card's link in the OS.".format(card_id))
    old = (card.get("notes") or "").rstrip()
    ctx.db.update("videos", card_id, {"notes": (old + "\n\n" if old else "") + notes_block(found, today)})
    link = skillkit.card_link(ctx.settings(), "videos", card_id)
    text = ("*{0} short clip{1} found for {2}.*\nThe list is in the card's notes. {3}").format(
        len(found["clips"]), "" if len(found["clips"]) == 1 else "s",
        str(card.get("video_title") or "a video").replace("<", "&lt;").replace(">", "&gt;"),
        "The clips are cut. Upload the ones you use to the card." if cut else
        "They are not cut yet. Cut them with --cut, or by hand from the times.")
    skillkit.post(ctx, load_config()["channel"], BOT, text, link=link)


def main(argv: Optional[List[str]] = None, ctx: Any = None, today: Optional[date] = None) -> int:
    ap = argparse.ArgumentParser(description="Find short clips in a long video, and cut them with ffmpeg.")
    ap.add_argument("--transcript", help="the transcript file (.srt, .vtt, .json or time-stamped .txt)")
    ap.add_argument("--video", help="the long video file on this computer")
    ap.add_argument("--count", type=int, help="how many clips at most (default in config.json)")
    ap.add_argument("--cut", action="store_true", help="cut the clips with ffmpeg (needs --video)")
    ap.add_argument("--vertical", action="store_true", help="crop the clips to 9:16")
    ap.add_argument("--out", help="the folder for clips.json and the clips")
    ap.add_argument("--card", help="a video card id: add the list to its notes and tell task-updates")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    a = ap.parse_args(argv)
    today = today or date.today()
    try:
        cfg = load_config()
        video = Path(a.video).expanduser() if a.video else None
        if video and not video.is_file():
            raise BadInput("There is no video file at {0}.".format(video))
        if a.cut and not video:
            raise BadInput("--cut needs --video: the clips are cut from the video file.")
        if not a.transcript and not video:
            raise BadInput("Give a transcript with --transcript, or a video with --video.")
        if a.transcript:
            tpath = Path(a.transcript).expanduser()
            if not tpath.is_file():
                raise BadInput("There is no transcript file at {0}.".format(tpath))
            source = tpath
        else:
            source = video  # type: ignore[assignment]
        if ctx is None and a.card:
            ctx = skillkit.context(needs=["ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN"], where=skillkit.AI_WHERE)
        elif ctx is None:
            skillkit.load_dotenv()
            skillkit.need(["ANTHROPIC_API_KEY"], skillkit.AI_WHERE)
        text = tpath.read_text(errors="ignore") if a.transcript else transcribe(video, cfg)  # type: ignore[arg-type]
        segments = parse_transcript(text)
        found = find_clips(segments, cfg, a.count or int(cfg["clip_count"]))
        if not found["clips"]:
            print("No clip fits the rules. Dropped: {0}".format("; ".join(found["dropped"]) or "none given"))
            return 1
        out_dir = Path(a.out).expanduser() if a.out else source.with_name(source.stem + "_clips")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "clips.json").write_text(json.dumps(found, indent=2))
        made: List[Path] = []
        cut_error = ""
        if a.cut:
            try:
                made = cut_clips(video, found["clips"], out_dir, a.vertical, cfg)  # type: ignore[arg-type]
            except BadInput as e:
                cut_error = str(e)
        if a.card:
            save_to_card(ctx, a.card, found, bool(made), today)
    except BadInput as e:
        print(str(e))
        return 2
    except skillkit.AIError as e:
        print("The clip search stopped: {0}".format(e))
        return 1
    if a.json:
        print(json.dumps(dict(found, folder=str(out_dir), cut=[str(m) for m in made]), indent=2))
    else:
        for c in found["clips"]:
            print("{0}. {1} to {2} ({3:.0f}s)  {4}\n   Hook: {5}\n   Why: {6}".format(
                c["number"], clock(c["start"]), clock(c["end"]), c["length"], c["title"], c["hook"], c["why"]))
        if found["dropped"]:
            print("\nDropped: " + "; ".join(found["dropped"]))
        print("\nThe list is saved in {0}".format(out_dir / "clips.json"))
        if made:
            print("{0} clips cut into {1}".format(len(made), out_dir))
    if cut_error:
        print(cut_error)
        return 2
    return 0


if __name__ == "__main__":
    skillkit.main_guard(main)
