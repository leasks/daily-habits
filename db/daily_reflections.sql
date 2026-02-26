create table if not exists daily_reflections (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  checkin_id bigint references daily_checkins(id) on delete set null,
  reflection_date date not null,
  achieved_goals jsonb not null default '[]'::jsonb,
  unachieved_goals jsonb not null default '[]'::jsonb,
  worked_well text,
  did_not_work text,
  reflection_summary text,
  next_day_prompt text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, reflection_date)
);

create index if not exists idx_daily_reflections_user_date
  on daily_reflections(user_id, reflection_date desc);
