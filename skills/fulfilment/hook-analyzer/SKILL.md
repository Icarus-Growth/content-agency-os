---
name: hook-analyzer
description: Scores the opening of a video (the first words of its transcript or caption) from 1 to 10, says what works and what to fix, and writes a stronger opening. It reads a video card or text you give it. Use when the user says "check this hook", "is this opening strong?", "score the hook on this video", "rewrite the first line" or "how good is the start of this video?".
area: fulfilment
agency: content
needs: [ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SECRET_KEY]
runs_on: either
---

# Hook analyzer

Checks the first words of a video and suggests a better start.
The AI scores it against the rules in `references/hook_rules.md`.

It posts nothing. It never writes to a place the client sees.
It writes only when you add `--save`: then it adds the result to the end of the card's
internal notes (`videos.notes`). The editor's change notes (`feedback_notes`) stay as they
are. To save somewhere else, change `save_to` in `config.json`.

It needs `ANTHROPIC_API_KEY` in `.env`. It needs `SUPABASE_URL` and `SUPABASE_SECRET_KEY`
only to read or save a card.

## Steps

1. Find what to check:
   - a video card: copy its id from the card's link in the OS
     (`.../board/videos/<id>`). The skill reads the card's caption.
   - what is said in the video: paste the first lines, or use the transcript file.
2. Run one of:
   - `python3 skills/fulfilment/hook-analyzer/scripts/hook_analyzer.py --text "Do your gums bleed when you brush?"`
   - `python3 skills/fulfilment/hook-analyzer/scripts/hook_analyzer.py --file transcript.srt --platform TikTok`
   - `python3 skills/fulfilment/hook-analyzer/scripts/hook_analyzer.py --card <video id>`
   - `python3 skills/fulfilment/hook-analyzer/scripts/hook_analyzer.py --card <video id> --file transcript.txt`
     (judges the transcript, and takes the title and platform from the card)
3. Read the result: the score, what works, what to fix, and the rewrites.
4. Ask the user if they want the result on the card. If yes, run it again with `--save`.
5. Give the user the best rewrite. A person decides if the video changes.

## What it checks

- Only the first 40 words (`opening_words` in `config.json`).
- Time stamps and caption numbers in a transcript file are taken out first.
- Fewer than 3 words: it stops and says so. No AI call is made.

## Change it

- `references/hook_rules.md`: what a strong and a weak opening is, and how to score.
- `config.json`: how many words to check, and which card column `--save` writes to.
