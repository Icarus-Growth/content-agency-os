-- Interview question: "Do you post for the client, or hand the finished video back?"
-- HAND BACK: records when and where the finished video was delivered. Use
--            "50 - Ready To Post" as the hand-back stage.
-- POST FOR THEM: skip this file.

alter table public.videos
  add column delivered_to_client_at timestamptz,
  add column delivery_url           text;
