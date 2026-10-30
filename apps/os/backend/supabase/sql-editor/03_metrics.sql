-- SQL editor paste 3 of 15: 0003_metrics.sql
-- Paste all of this into the Supabase SQL editor and press Run.
-- Wait for "Success" before you paste the next file.

-- =============================================================================
-- 0003  Report numbers: content
--
-- daily_metrics:  one client on one day.
-- weekly_metrics: one client in one week (week_start is a Monday).
-- They stay empty until you connect your social or scheduling tool. The tool
-- is a value in the "source" column, never a column name.
-- Engagement rate is worked out by the database (engagements / views).
-- =============================================================================

create table public.daily_metrics (
  id                uuid primary key default gen_random_uuid(),
  client_id         uuid not null references public.clients(id) on delete cascade,
  metric_date       date not null,
  posts_published   int not null default 0,
  views             int not null default 0,
  followers         int,
  engagements       int not null default 0,
  engagement_rate   numeric generated always as (round(engagements::numeric / nullif(views, 0), 4)) stored,
  top_post_url      text,
  source            text,
  is_example        boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (client_id, metric_date)
);
comment on table public.daily_metrics is 'One client on one day. Content numbers. followers is the total at the end of the day.';

create table public.weekly_metrics (
  id                uuid primary key default gen_random_uuid(),
  client_id         uuid not null references public.clients(id) on delete cascade,
  week_start        date not null,
  posts_published   int not null default 0,
  views             int not null default 0,
  followers         int,
  engagements       int not null default 0,
  engagement_rate   numeric generated always as (round(engagements::numeric / nullif(views, 0), 4)) stored,
  top_post_url      text,
  note              text,
  is_example        boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (client_id, week_start)
);
comment on table public.weekly_metrics is 'One client in one week. The daily numbers summed, plus a short note.';

create trigger daily_metrics_touch_updated_at before update on public.daily_metrics
  for each row execute function public.touch_updated_at();
create trigger weekly_metrics_touch_updated_at before update on public.weekly_metrics
  for each row execute function public.touch_updated_at();
