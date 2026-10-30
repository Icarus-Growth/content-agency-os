-- Interview question: "Which platforms do you post on, and do you report each one apart?"
-- EACH ONE APART: the report numbers get one row per platform per day (and per week).
-- ALL TOGETHER: skip this file.

alter table public.daily_metrics add column platform text not null default 'All';
alter table public.daily_metrics drop constraint if exists daily_metrics_client_id_metric_date_key;
alter table public.daily_metrics add constraint daily_metrics_client_date_platform_key unique (client_id, metric_date, platform);

alter table public.weekly_metrics add column platform text not null default 'All';
alter table public.weekly_metrics drop constraint if exists weekly_metrics_client_id_week_start_key;
alter table public.weekly_metrics add constraint weekly_metrics_client_week_platform_key unique (client_id, week_start, platform);
