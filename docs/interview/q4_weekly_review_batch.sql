-- Interview question: "Do clients review videos in one weekly batch?"
-- YES: each video gets the week it goes to the client, and a view counts each batch.
-- NO:  skip this file.

alter table public.videos add column review_week date;
comment on column public.videos.review_week is 'The Monday of the week this video goes to the client for review.';

create view public.v_review_batches with (security_invoker = true) as
select client_id, review_week,
       count(*)::int as videos,
       count(*) filter (where stage = '40 - Client Review')::int as waiting_on_client,
       count(*) filter (where stage = '49 - Client Changes')::int as changes_asked
from public.videos
where review_week is not null and archived_at is null
group by client_id, review_week;
comment on view public.v_review_batches is 'One client''s weekly review batch.';
