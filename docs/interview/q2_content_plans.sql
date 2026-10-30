-- Interview question: "Do you make a monthly content plan for each client?"
-- YES: adds content plans. Each video can point at its month's plan.
-- NO:  skip this file.

create table public.content_plans (
  id            uuid primary key default gen_random_uuid(),
  plan_name     text not null,
  client_id     uuid not null references public.clients(id) on delete cascade,
  plan_month    date not null,
  pillars       text,
  plan_url      text,
  owner_id      uuid references public.team(id) on delete set null,
  notes         text,
  is_example    boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (client_id, plan_month)
);
comment on table public.content_plans is 'One client''s content plan for one month. plan_month is the first day of the month.';
create trigger content_plans_touch_updated_at before update on public.content_plans
  for each row execute function public.touch_updated_at();
select public.lock_table('content_plans');

alter table public.videos add column content_plan_id uuid references public.content_plans(id) on delete set null;
