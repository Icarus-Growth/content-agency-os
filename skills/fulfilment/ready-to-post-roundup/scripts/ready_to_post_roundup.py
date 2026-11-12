"""Ready to post roundup: one post a day with every video that is ready to post, by client.

It lists the videos at '50 - Ready To Post', and the videos at '60 - Scheduled' that have
no time set (scheduled_for is empty). Archived cards and archived clients are left out.
The main post gives the counts. The thread under it has one reply per client, with a
link to each card and to the edited file. It only reads: it moves no card.

The daily job runs it once a day (scripts/daily.py). On demand:

    python3 skills/fulfilment/ready-to-post-roundup/scripts/ready_to_post_roundup.py          (dry run)
    python3 skills/fulfilment/ready-to-post-roundup/scripts/ready_to_post_roundup.py --now    (posts)
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
from datetime import date  # noqa: E402
from typing import Any, Dict, List, MutableMapping, Optional  # noqa: E402

SKILL = "ready-to-post-roundup"
BOT = "📬 Ready to Post"
BOARD = "videos"
CONFIG_FILE = Path(__file__).resolve().parents[1] / "config.json"
DEFAULTS: Dict[str, Any] = {"channel": "approved", "ready_stage": "50 - Ready To Post",
                            "scheduled_stage": "60 - Scheduled", "include_scheduled_without_time": True,
                            "post_when_empty": False, "max_lines_per_client": 30}


def load_config(path: Path = CONFIG_FILE) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update({k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")})
    return cfg


def esc(text: Any) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def short_date(value: Any) -> str:
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return esc(value)
    return "{0} {1} {2}".format(d.strftime("%a"), d.day, d.strftime("%b"))


def ready(videos: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The videos that count. Pure."""
    out = []
    for v in videos:
        if v.get("archived_at"):
            continue
        if v.get("stage") == cfg["ready_stage"]:
            out.append(v)
        elif (cfg.get("include_scheduled_without_time") and v.get("stage") == cfg["scheduled_stage"]
              and not v.get("scheduled_for")):
            out.append(v)
    return sorted(out, key=lambda v: (str(v.get("due_date") or "9999"), str(v.get("video_title") or "")))


def line(v: Dict[str, Any], settings: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    name = esc(v.get("video_title") or "Untitled video")
    link = skillkit.card_link(settings, BOARD, str(v.get("id")))
    parts = ["🎬 " + ("<{0}|{1}>".format(link, name) if link else name)]
    parts.append(esc(v.get("platform")) or "no platform set")
    parts.append("<{0}|the file>".format(v["edited_url"]) if v.get("edited_url") else "no edited file linked")
    if v.get("stage") == cfg["scheduled_stage"]:
        parts.append("scheduled, but no time set")
    if v.get("due_date"):
        parts.append("due " + short_date(v["due_date"]))
    return "• " + ", ".join(parts)


def run(db: Any, slack: Any, config: Any, seen: Optional[MutableMapping[str, Any]], today: date,
        cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_config()
    ctx = skillkit.Context(db, slack, config, seen)
    settings = ctx.settings()
    board_link = skillkit.os_link(settings, "tasks/" + BOARD)
    try:
        stages = '"{0}","{1}"'.format(cfg["ready_stage"], cfg["scheduled_stage"])
        videos = ready(db.select_all(BOARD, {"stage": "in.({0})".format(stages), "archived_at": "is.null"},
                                     order="due_date") or [], cfg)
        ids = sorted({str(v.get("client_id")) for v in videos if v.get("client_id")})
        clients = {str(c["id"]): c for c in
                   (db.select_all("clients", {"id": "in.({0})".format(",".join(ids))}) if ids else [])
                   if not c.get("archived_at")}
        videos = [v for v in videos if str(v.get("client_id")) in clients]
    except Exception as e:  # noqa: BLE001
        skillkit.report_failure(ctx, SKILL, "read the Editing pipeline board", e, board_link)
        return {"ok": False, "error": str(e)[:200]}

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for v in videos:
        groups.setdefault(str(v.get("client_id")), []).append(v)
    out: Dict[str, Any] = {"ok": True, "videos": len(videos), "clients": len(groups), "posted": False}
    if not videos and not cfg.get("post_when_empty"):
        return out
    key = "{0}:{1}".format(SKILL, today.isoformat())
    if not skillkit.first_time(seen, key, hours=20):
        out["skipped"] = "already posted today"
        return out

    if not videos:
        skillkit.post(ctx, cfg["channel"], BOT, "*Ready to post:* nothing is ready today.")
        out["posted"] = True
        return out
    head = ("*Ready to post: {0} video{1} for {2} client{3}.*\n"
            "Each client's list is in the thread. Post or schedule them, then move each card on.").format(
        len(videos), "" if len(videos) == 1 else "s", len(groups), "" if len(groups) == 1 else "s")
    ts = skillkit.post(ctx, cfg["channel"], BOT, head, link=board_link, button="Open the board")
    if not ts:
        return out
    team = {str(t["id"]): t for t in db.select_all("team", {}) or []}
    channel = ctx.config.channel_id(cfg["channel"])
    for cid in sorted(groups, key=lambda c: str(clients[c].get("client_name") or "").lower()):
        client = clients[cid]
        lines = ["*{0}* ({1})".format(esc(client.get("client_name")), _who(client, team))]
        vids = groups[cid]
        lines += [line(v, settings, cfg) for v in vids[: int(cfg["max_lines_per_client"])]]
        if len(vids) > int(cfg["max_lines_per_client"]):
            lines.append("…and {0} more on the board.".format(len(vids) - int(cfg["max_lines_per_client"])))
        ctx.slack.post(channel, BOT, "\n".join(lines), thread_ts=ts)
    out["posted"] = True
    return out


def _who(client: Dict[str, Any], team: Dict[str, Dict[str, Any]]) -> str:
    for col in ("social_media_manager_id", "account_manager_id"):
        p = team.get(str(client.get(col) or ""))
        if p:
            return "<@{0}>".format(p["slack_user_id"]) if p.get("slack_user_id") else esc(p.get("full_name"))
    return "nobody set to post"


class DryRun:
    """Stands in for Slack and the channels: prints each post instead of sending it."""

    def channel_id(self, key: str) -> str:
        return "#" + key

    def post(self, channel: str, bot_name: str, text: str, blocks: Optional[list] = None,
             thread_ts: Optional[str] = None) -> str:
        where = "the thread" if thread_ts else channel
        print("--- would post in {0} as {1}:\n{2}\n".format(where, bot_name, text))
        return "dry-run"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Post every video that is ready to post, grouped by client.")
    ap.add_argument("--now", action="store_true", help="post now")
    ap.add_argument("--dry-run", action="store_true", help="print what it would post (the default)")
    a = ap.parse_args(argv)
    live = a.now and not a.dry_run
    ctx = skillkit.context(needs=["SLACK_BOT_TOKEN"] if live else [])
    if live:
        out = run(ctx.db, ctx.slack, ctx.config, {}, date.today())
    else:
        print("Dry run: nothing is posted. Add --now to post.\n")
        fake = DryRun()
        out = run(ctx.db, fake, fake, {}, date.today())
    print(skillkit.dump(out))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    skillkit.main_guard(main)
