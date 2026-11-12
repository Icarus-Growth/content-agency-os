---
name: shorts-clipper
description: Finds the best short clips in a long video from its transcript (start and end times, a title, the hook and why each one works), and cuts them with ffmpeg on your computer when you ask. Use when the user says "find clips in this video", "make shorts from this podcast", "cut this long video into short clips", "clip this talk" or "which parts would make good shorts?".
area: fulfilment
agency: content
needs: [ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SECRET_KEY, SLACK_BOT_TOKEN]
runs_on: local
---

# Shorts clipper

Finds short clips in a long video, and cuts them.
It runs on the editor's computer, because the video files are large.

## What it needs

- `ANTHROPIC_API_KEY` in `.env`, to pick the clips.
- A transcript with times: an `.srt`, a `.vtt`, a Whisper `.json`, or a text file where each
  line starts with a time, like `[01:02] the words`. Most editing apps and transcribers
  export one of these.
- No transcript? It runs the free local transcriber in `config.json` (`transcribe_command`,
  Whisper by default) on the video. It uses no paid transcription service.
- To cut the clips: ffmpeg on your computer (ffmpeg.org). Without ffmpeg it still finds
  the clips and saves the list.
- Only with `--card`: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` and `SLACK_BOT_TOKEN`.

## Steps

1. Get the transcript and the video file onto your computer.
2. Find the clips:
   `python3 skills/fulfilment/shorts-clipper/scripts/shorts_clipper.py --transcript talk.srt`
3. Read the list: each clip's start and end, title, hook and why it works. The clips that
   did not fit (too short, too long, outside the video, the same part twice) are listed as
   "Dropped".
4. Show the list to the user. Ask which clips to cut.
5. Cut them:
   `python3 skills/fulfilment/shorts-clipper/scripts/shorts_clipper.py --transcript talk.srt --video talk.mp4 --cut --vertical`
   `--vertical` crops each clip to 9:16 (1080 x 1920). Leave it out to keep the shape.
6. Find the files in the folder `talk_clips/` next to the transcript (or the folder you give
   with `--out`). `clips.json` holds the list.
7. Watch each clip before you use it. The AI picks the times; a person checks them.
8. To put the list on the video's card and tell the team in `task-updates`, add
   `--card <video id>` (the id is in the card's link in the OS). The list is added to the end
   of the card's notes. Nothing else on the card changes.

More options: `--count 3` (at most 3 clips), `--json` (the result as JSON).

## Change it

- `references/clip_rules.md`: what makes a good clip.
- `config.json`: how many clips, the shortest and longest clip, the crop, the ffmpeg
  quality, and the local transcriber command.
