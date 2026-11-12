-- SQL editor paste 4 of 18: 0004_boards.sql
-- Paste all of this into the Supabase SQL editor and press Run.
-- Wait for "Success" before you paste the next file.

-- =============================================================================
-- 0004  Boards: content
--
-- Boards on the Tasks screen: Tasks (made in 0001) and Editing pipeline.
-- One video card goes from raw footage to posted. The client uploads the raw
-- footage themselves. Shoot days and monthly content plans are Interview only.
-- =============================================================================

-- Content columns on the client (wide-table rule) -----------------------------
alter table public.clients
  add column editor_id               uuid references public.team(id) on delete set null,
  add column social_media_manager_id uuid references public.team(id) on delete set null,
  add column platforms               text[] not null default '{}',
  add column posts_per_week          int,
  add column raw_footage_folder_url  text,
  add column brand_guidelines_url    text,
  add column strategy_brief_url      text;
comment on column public.clients.platforms is 'Where the client posts, as values (for example the platform names).';
comment on column public.clients.raw_footage_folder_url is 'The folder where the client uploads raw footage.';

-- Editing pipeline board ------------------------------------------------------
create type public.video_stage as enum (
  '0 - Raw Footage',
  '10 - Ready To Edit',
  '20 - Editing',
  '30 - Internal Review',
  '39 - Amendments',
  '40 - Client Review',
  '49 - Client Changes',
  '50 - Ready To Post',
  '60 - Scheduled',
  '100 - Posted'
);
create type public.caption_status as enum ('To Write', 'To Review', 'Done');

create table public.videos (
  id                   uuid primary key default gen_random_uuid(),
  video_title          text not null,
  client_id            uuid not null references public.clients(id) on delete cascade,
  stage                public.video_stage not null default '0 - Raw Footage',
  stage_changed_at     timestamptz,
  stage_changed_by_id  uuid references public.team(id) on delete set null,
  assignee_id          uuid references public.team(id) on delete set null,
  reviewer_id          uuid references public.team(id) on delete set null,
  raw_footage_url      text,
  edited_url           text,
  caption              text,
  caption_status       public.caption_status not null default 'To Write',
  platform             text,
  feedback_notes       text,
  due_date             date,
  scheduled_for        timestamptz,
  posted_at            timestamptz,
  post_url             text,
  notes                text,
  is_example           boolean not null default false,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
comment on table public.videos is 'One video, from raw footage to posted. The "Editing pipeline" board.';
comment on column public.videos.assignee_id is 'Who must act now: usually the editor.';
create index videos_client_idx on public.videos (client_id);
create index videos_assignee_idx on public.videos (assignee_id);

create trigger videos_touch_updated_at before update on public.videos
  for each row execute function public.touch_updated_at();
select public.attach_stage_log('videos');

-- Every open card on every board, in one shape. The dashboard reads this.
create view public.v_open_cards with (security_invoker = true) as
select 'tasks'::text as board, 'Tasks'::text as board_label, id as card_id, task_name as card_name,
       client_id, stage::text as stage, split_part(stage::text, ' ', 1)::int as stage_number,
       assignee_id, reviewer_id, due_date, coalesce(stage_changed_at, created_at) as stage_changed_at, is_example
from public.tasks where stage not in ('100 - Complete', '-1 - Rejected')
union all
select 'videos', 'Editing pipeline', id, video_title,
       client_id, stage::text, split_part(stage::text, ' ', 1)::int,
       assignee_id, reviewer_id, due_date, coalesce(stage_changed_at, created_at), is_example
from public.videos where stage not in ('60 - Scheduled', '100 - Posted');
comment on view public.v_open_cards is 'Every open card on every board, in one shape. Scheduled and posted videos are left out.';
