-- Interview question: "Do you film clients yourself?"
-- YES: adds shoot days. Each video can point at the shoot day it came from.
-- NO:  skip this file. Clients upload their own raw footage.

create table public.shoot_days (
  id             uuid primary key default gen_random_uuid(),
  shoot_name     text not null,
  client_id      uuid not null references public.clients(id) on delete cascade,
  shoot_date     date,
  location       text,
  shooter_id     uuid references public.team(id) on delete set null,
  attendees      text,
  prep_notes     text,
  shooter_notes  text,
  footage_url    text,
  is_example     boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
comment on table public.shoot_days is 'One filming day for one client.';
create trigger shoot_days_touch_updated_at before update on public.shoot_days
  for each row execute function public.touch_updated_at();
select public.lock_table('shoot_days');

alter table public.videos add column shoot_day_id uuid references public.shoot_days(id) on delete set null;
