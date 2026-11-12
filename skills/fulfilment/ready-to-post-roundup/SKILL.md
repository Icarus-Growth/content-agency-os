---
name: ready-to-post-roundup
description: Every day, posts one list of the videos that are ready to post (stage 50 - Ready To Post, and scheduled videos with no time set), grouped by client, with a link to each card and to the edited file. It moves no card. Use when the user says "what is ready to post?", "ready to post roundup", "what can we post today?" or "post the roundup now".
area: fulfilment
agency: content
needs: [SUPABASE_URL, SUPABASE_SECRET_KEY, SLACK_BOT_TOKEN]
runs_on: modal
daily: true
---

# Ready to post roundup

Shows the team, once a day, every video that waits to be posted.
It only reads. It moves no card and writes nothing to the database.
It never posts in a client's channel.

## What counts

- A video card at `50 - Ready To Post`.
- A video card at `60 - Scheduled` with no time set (`scheduled_for` is empty).
- Archived cards and archived clients are left out.

## What it posts

- One main post in `approved`: how many videos are ready, for how many clients, and a
  button that opens the Editing pipeline board.
- One reply in the thread for each client. It tags the client's social media manager (else
  the account manager). Each line gives the card link, the platform, the link to the edited
  file and the due date.
- Nothing ready: no post. Set `post_when_empty` to `true` in `config.json` to get a
  "nothing is ready today" line instead.
- It posts once a day at most.

A failure is posted once to `pipeline-errors`.

## Steps

1. The daily job runs it once a day. You do not need to start it.
2. To see what it would post (a dry run, the default):
   `python3 skills/fulfilment/ready-to-post-roundup/scripts/ready_to_post_roundup.py`
3. To post now: add `--now`.
4. After you post or schedule a video, move its card on. It then leaves the list.

## Change it

`config.json`: the channel, the stages that count, whether scheduled videos with no time
count, what to do when nothing is ready, and the most lines per client.
