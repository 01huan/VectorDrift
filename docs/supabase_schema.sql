-- Vector Drift account schema (run in Supabase SQL editor)

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    money integer not null default 0,
    owned_ships text[] not null default array['ship01'],
    purchased_items text[] not null default array[]::text[],
    records jsonb not null default '{}'::jsonb,
    collected_money_pickups jsonb not null default '[]'::jsonb,
    stats jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles_select_own" on public.profiles
    for select using (auth.uid() = id);
create policy "profiles_insert_own" on public.profiles
    for insert with check (auth.uid() = id);
create policy "profiles_update_own" on public.profiles
    for update using (auth.uid() = id);

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
as $$
begin
    insert into public.profiles (id, display_name)
    values (new.id, new.email)
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();
