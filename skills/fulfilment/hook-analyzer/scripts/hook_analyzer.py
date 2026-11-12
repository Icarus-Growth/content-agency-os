"""Hook analyzer: scores the opening of a video and writes a stronger one.

The opening is the first words of the transcript or the caption. It comes from:
  * --text "..." or --file transcript.txt (what is said in the video), or
  * --card <video id>: the card's caption document on the Editing pipeline board.
With --card and --text/--file together, the text is judged and the card gives the title
and the platform.

The AI (skillkit.ask_ai, with a JSON schema) gives a score from 1 to 10, what works, what
to fix, and a rewrite. The rules it scores against are in references/hook_rules.md.

It writes nothing and posts nothing, unless you add --save: then the result is added to the
end of the card's internal notes (videos.notes, set by `save_to` in config.json). It never
writes to a client-facing place.

    python3 skills/fulfilment/hook-analyzer/scripts/hook_analyzer.py --text "Stop doing this one thing..."
    python3 skills/fulfilment/hook-analyzer/scripts/hook_analyzer.py --card <video id> --save
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
from datetime import date  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = SKILL_DIR / "config.json"
RULES_FILE = SKILL_DIR / "references" / "hook_rules.md"
DEFAULTS: Dict[str, Any] = {"opening_words": 40, "save_to": "notes", "max_tokens": 1500, "effort": "low"}
SAVE_COLUMNS = ("notes", "feedback_notes")

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "1 to 10, from the scoring rules"},
        "verdict": {"type": "string", "description": "one short sentence"},
        "what_works": {"type": "array", "items": {"type": "string"}},
        "what_to_fix": {"type": "array", "items": {"type": "string"}},
        "rewrite": {"type": "string", "description": "the best new opening, short enough to say in 3 seconds"},
        "other_rewrites": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "verdict", "what_works", "what_to_fix", "rewrite", "other_rewrites"],
    "additionalProperties": False,
}
SYSTEM = ("You judge the opening of short social videos for a content agency. Score only what is written. "
          "Follow the rules you are given. Never add a claim the video does not make.")


class BadInput(ValueError):
    """The input cannot be checked. The message says why, in plain words."""


def load_config(path: Path = CONFIG_FILE) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update({k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")})
    if cfg["save_to"] not in SAVE_COLUMNS:
        raise BadInput("config.json 'save_to' must be one of: {0}.".format(", ".join(SAVE_COLUMNS)))
    return cfg


def opening(text: str, words: int) -> str:
    """The first `words` words, with timestamps and caption numbers taken out. Pure."""
    clean = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or ln.isdigit() or "-->" in ln or ln.upper() == "WEBVTT":
            continue
        clean.append(re.sub(r"^\[?\(?\d{1,2}:\d{2}(:\d{2})?([.,]\d+)?\]?\)?\s*", "", ln))
    return " ".join(" ".join(clean).split()[:words])


def check(text: str, title: str = "", platform: str = "", cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score one opening. Raises BadInput when there is nothing to check (nothing is spent)."""
    cfg = cfg or load_config()
    first = opening(text, int(cfg["opening_words"]))
    if len(first.split()) < 3:
        raise BadInput("There is no opening to check. Give at least a few words with --text or --file, "
                       "or write the card's caption first.")
    rules = RULES_FILE.read_text() if RULES_FILE.exists() else ""
    prompt = ("Rules:\n{0}\n\nVideo title: {1}\nPlatform: {2}\n\nThe opening (the first words of the video):\n"
              "\"\"\"{3}\"\"\"\n\nScore the opening from 1 to 10 with the rules. Say what works and what to fix "
              "(at most 3 lines each). Write one best rewrite and up to 2 other rewrites.").format(
        rules, title or "(none)", platform or "(not set)", first)
    ans = skillkit.ask_ai(prompt, system=SYSTEM, schema=SCHEMA, max_tokens=int(cfg["max_tokens"]),
                          effort=str(cfg["effort"]))
    if not isinstance(ans, dict) or any(k not in ans for k in SCHEMA["required"]):
        raise skillkit.AIError("The AI answer is missing parts. Run it again.")
    try:
        score = int(ans["score"])
    except (TypeError, ValueError):
        raise skillkit.AIError("The AI gave no score. Run it again.")
    return dict(ans, score=max(1, min(10, score)), opening=first)


def card_input(db: Any, card_id: str) -> Dict[str, Any]:
    """The card, and its caption text (the caption document, or the old caption column)."""
    card = db.get("videos", card_id)
    if not card:
        raise BadInput("No video card has the id {0}. Copy the id from the card's link in the OS.".format(card_id))
    docs = db.select("documents", {"board": "eq.videos", "card_id": "eq." + card_id, "field_key": "eq.caption"},
                     limit=1) or []
    caption = (docs[0].get("body_md") if docs else "") or card.get("caption") or ""
    return {"card": card, "caption": caption}


def notes_block(result: Dict[str, Any], today: date) -> str:
    lines = ["Hook check, {0}: {1}/10. {2}".format(today.isoformat(), result["score"], result["verdict"]),
             "Opening checked: \"{0}\"".format(result["opening"])]
    lines += ["What works: " + w for w in result["what_works"]]
    lines += ["To fix: " + w for w in result["what_to_fix"]]
    lines.append("Rewrite: " + result["rewrite"])
    lines += ["Other rewrite: " + w for w in result["other_rewrites"]]
    return "\n".join(lines)


def save(db: Any, card: Dict[str, Any], result: Dict[str, Any], cfg: Dict[str, Any], today: date) -> Dict[str, Any]:
    """Adds the result to the end of the card's notes. What was there stays."""
    col = cfg["save_to"]
    old = (card.get(col) or "").rstrip()
    new = (old + "\n\n" if old else "") + notes_block(result, today)
    return db.update("videos", str(card["id"]), {col: new})


def show(result: Dict[str, Any]) -> str:
    out = ["Score: {0}/10. {1}".format(result["score"], result["verdict"]), "",
           "Opening checked: \"{0}\"".format(result["opening"]), "", "What works:"]
    out += ["- " + w for w in result["what_works"]] or ["- (nothing)"]
    out += ["", "What to fix:"] + (["- " + w for w in result["what_to_fix"]] or ["- (nothing)"])
    out += ["", "Rewrite: " + result["rewrite"]]
    out += ["Other: " + w for w in result["other_rewrites"]]
    return "\n".join(out)


def main(argv: Optional[List[str]] = None, db: Any = None, today: Optional[date] = None) -> int:
    ap = argparse.ArgumentParser(description="Score the opening of a video and write a stronger one.")
    ap.add_argument("--card", help="the video card's id (Editing pipeline)")
    ap.add_argument("--text", help="the opening, or the whole transcript")
    ap.add_argument("--file", help="a transcript file (.txt, .srt or .vtt)")
    ap.add_argument("--platform", default="", help="where it will be posted, if no card")
    ap.add_argument("--save", action="store_true", help="add the result to the card's notes (needs --card)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    a = ap.parse_args(argv)
    today = today or date.today()
    try:
        cfg = load_config()
        if a.save and not a.card:
            raise BadInput("--save needs --card: the result is saved on a card.")
        if not (a.card or a.text or a.file):
            raise BadInput("Give the opening with --text or --file, or a card with --card.")
        text = a.text or ""
        if a.file:
            p = Path(a.file).expanduser()
            if not p.is_file():
                raise BadInput("There is no file at {0}.".format(p))
            text = p.read_text(errors="ignore")
        card, title, platform = None, "", a.platform
        if a.card:
            if db is None:
                db = skillkit.context(needs=["ANTHROPIC_API_KEY"], where=skillkit.AI_WHERE).db
            got = card_input(db, a.card)
            card = got["card"]
            text = text or got["caption"]
            title, platform = card.get("video_title") or "", platform or card.get("platform") or ""
        else:
            skillkit.load_dotenv()
            skillkit.need(["ANTHROPIC_API_KEY"], skillkit.AI_WHERE)
        result = check(text, title, platform, cfg)
    except BadInput as e:
        print(str(e))
        return 2
    except skillkit.AIError as e:
        print("The hook check stopped: {0}".format(e))
        return 1
    if a.save and card is not None:
        save(db, card, result, cfg, today)
        result["saved_to"] = "videos.{0}".format(cfg["save_to"])
    print(json.dumps(result, indent=2) if a.json else show(result))
    if result.get("saved_to"):
        print("\nSaved to the card's {0}.".format(cfg["save_to"]))
    return 0


if __name__ == "__main__":
    skillkit.main_guard(main)
