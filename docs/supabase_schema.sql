-- Vector Drift account schema (run in Supabase SQL editor)

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    money integer not null default 0,
    owned_ships text[] not null default array['ship01'],
    purchased_items text[] not null default array[]::text[],
    records jsonb not null default '{}'::jsonb,
    replays jsonb not null default '[]'::jsonb,
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

-- Auto-create profile on signup.
-- 顯示名稱優先使用 Supabase Auth user_metadata 裡的 display_name（註冊時輸入的帳號 ID），
-- 沒有才退回使用信箱，讓遊戲內各處顯示帳號名稱而非信箱。
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
as $$
begin
    insert into public.profiles (id, display_name)
    values (new.id, nullif(new.raw_user_meta_data->>'display_name', ''))
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Community custom levels: anybody can read, only signed-in users can upload.
create table if not exists public.community_levels (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    uploader_name text not null default '',   -- 上傳者的帳號名稱，社區卡片顯示此欄位，不顯示信箱
    level_name text not null,
    level_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.community_levels enable row level security;

create policy "community_levels_select_public" on public.community_levels
    for select using (true);
create policy "community_levels_insert_authenticated" on public.community_levels
    for insert with check (auth.uid() = user_id);
create policy "community_levels_delete_own" on public.community_levels
    for delete using (auth.uid() = user_id);
-- 帳號上傳者可修改自己上傳的社區關卡（改名時同步 uploader_name、修改關卡時同步 level_name/level_data）。
create policy "community_levels_update_own" on public.community_levels
    for update using (auth.uid() = user_id);
