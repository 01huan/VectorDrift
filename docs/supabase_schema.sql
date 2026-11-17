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

-- Drop first so this file can be re-run to upgrade an existing project.
drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
    for select using (auth.uid() = id);
drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own" on public.profiles
    for insert with check (auth.uid() = id);
drop policy if exists "profiles_update_own" on public.profiles;
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
    created_at timestamptz not null default now(),
    -- 瀏覽統計：遊玩次數、通關次數、通關的玩家（用來算通關人數）
    play_count integer not null default 0,
    clear_count integer not null default 0,
    clear_players jsonb not null default '[]'::jsonb
);

-- 舊的資料庫沒有統計欄位時補上（已存在就不動）。
alter table public.community_levels
    add column if not exists play_count integer not null default 0,
    add column if not exists clear_count integer not null default 0,
    add column if not exists clear_players jsonb not null default '[]'::jsonb;

alter table public.community_levels enable row level security;

-- Drop first so this file can be re-run to add the statistics columns above.
drop policy if exists "community_levels_select_public" on public.community_levels;
create policy "community_levels_select_public" on public.community_levels
    for select using (true);
drop policy if exists "community_levels_insert_authenticated" on public.community_levels;
create policy "community_levels_insert_authenticated" on public.community_levels
    for insert with check (auth.uid() = user_id);
drop policy if exists "community_levels_delete_own" on public.community_levels;
create policy "community_levels_delete_own" on public.community_levels
    for delete using (auth.uid() = user_id);
-- 帳號上傳者可修改自己上傳的社區關卡（改名時同步 uploader_name、修改關卡時同步 level_name/level_data）。
drop policy if exists "community_levels_update_own" on public.community_levels;
create policy "community_levels_update_own" on public.community_levels
    for update using (auth.uid() = user_id);

-- 統計計數用資料庫函式更新，避免兩位玩家同時加一而互相覆蓋。
-- 這些函式對 anon / authenticated 開放（遊客沒有帳號也要能計數），
-- 所以數字只是「盡力而為」的統計，不是防弊機制。
-- 遊玩一次：play_count + 1。
create or replace function public.community_level_record_play(p_level_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    update public.community_levels
       set play_count = play_count + 1
     where id = p_level_id;
end;
$$;

-- 通關一次：clear_count + 1，並把玩家代號記進 clear_players（不重複），
-- 這樣就能算出「有幾位不同的玩家通關過」。
-- clear_players 是公開可讀的欄位，所以只存玩家代號的雜湊；雜湊再加上關卡 id，
-- 同一個玩家在不同關卡的代號不同，無法用來跨關卡追蹤。
create or replace function public.community_level_record_clear(p_level_id uuid, p_player_key text)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_player_key text;
begin
    if p_level_id is null then
        return;
    end if;
    if p_player_key is null or p_player_key = '' then
        update public.community_levels
           set clear_count = clear_count + 1
         where id = p_level_id;
        return;
    end if;
    v_player_key := 'v1:' || md5(p_level_id::text || ':' || p_player_key);
    update public.community_levels
       set clear_count = clear_count + 1,
           clear_players = case
               when clear_players ? v_player_key then clear_players
               else clear_players || jsonb_build_array(v_player_key)
           end
     where id = p_level_id;
end;
$$;

grant execute on function public.community_level_record_play(uuid) to anon, authenticated;
grant execute on function public.community_level_record_clear(uuid, text) to anon, authenticated;

-- Community force functions: anybody can read, only signed-in users can upload.
create table if not exists public.community_functions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    uploader_name text not null default '',
    function_name text not null,
    fx text not null default '',
    fy text not null default '',
    created_at timestamptz not null default now()
);

-- 新欄位先補上再建 policy：舊資料庫執行時不會報錯，已存在就不動。
alter table public.community_functions
    add column if not exists description text not null default '',
    add column if not exists tags text[] not null default '{}'::text[],
    add column if not exists updated_at timestamptz not null default now(),
    add column if not exists usage_count integer not null default 0,
    add column if not exists successful_usage_count integer not null default 0,
    add column if not exists usage_users jsonb not null default '[]'::jsonb,
    add column if not exists unique_user_count integer not null default 0,
    add column if not exists favorite_count integer not null default 0,
    add column if not exists rating_count integer not null default 0,
    add column if not exists rating_total integer not null default 0;
-- 舊資料把 usage_users 視為空陣列，unique_user_count 以 0 計。
update public.community_functions
   set unique_user_count = jsonb_array_length(usage_users)
 where jsonb_typeof(usage_users) = 'array'
   and unique_user_count <> jsonb_array_length(usage_users);

alter table public.community_functions enable row level security;

drop policy if exists "community_functions_select_public" on public.community_functions;
create policy "community_functions_select_public" on public.community_functions
    for select using (true);
drop policy if exists "community_functions_insert_authenticated" on public.community_functions;
create policy "community_functions_insert_authenticated" on public.community_functions
    for insert with check (auth.uid() = user_id);
drop policy if exists "community_functions_delete_own" on public.community_functions;
create policy "community_functions_delete_own" on public.community_functions
    for delete using (auth.uid() = user_id);
drop policy if exists "community_functions_update_own" on public.community_functions;
create policy "community_functions_update_own" on public.community_functions
    for update using (auth.uid() = user_id);

-- updated_at 只在內容真的變更時更新（統計欄位的觸發器不應弄髒它）。
create or replace function public.community_functions_set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if (new.function_name, new.fx, new.fy, new.description, new.tags, new.uploader_name)
       is distinct from
       (old.function_name, old.fx, old.fy, old.description, old.tags, old.uploader_name) then
        new.updated_at := now();
    end if;
    return new;
end;
$$;

drop trigger if exists community_functions_updated_at on public.community_functions;
create trigger community_functions_updated_at
    before update on public.community_functions
    for each row execute function public.community_functions_set_updated_at();

-- 使用統計用資料庫函式更新，避免兩位玩家同時加一而互相覆蓋。
-- p_success = true 時 successful_usage_count 同步 + 1；
-- 同一玩家（以 p_player_key 雜湊後比對）重複使用不會增加 unique_user_count；
-- usage_users 只存「關卡/函式 id ＋玩家代號」的雜湊，無法反推出玩家身分。
create or replace function public.community_function_record_usage(
    p_function_id uuid,
    p_success boolean,
    p_player_key text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_key text;
begin
    if p_function_id is null then
        return;
    end if;
    if p_player_key is not null and p_player_key <> '' then
        v_key := 'v1:' || md5(p_function_id::text || ':' || p_player_key);
        update public.community_functions
           set usage_count = usage_count + 1,
               successful_usage_count = successful_usage_count + (case when p_success then 1 else 0 end),
               usage_users = case when usage_users ? v_key
                                  then usage_users
                                  else usage_users || jsonb_build_array(v_key) end,
               unique_user_count = jsonb_array_length(
                   case when usage_users ? v_key
                        then usage_users
                        else usage_users || jsonb_build_array(v_key) end)
         where id = p_function_id;
    else
        update public.community_functions
           set usage_count = usage_count + 1,
               successful_usage_count = successful_usage_count + (case when p_success then 1 else 0 end)
         where id = p_function_id;
    end if;
end;
$$;

grant execute on function public.community_function_record_usage(uuid, boolean, text) to anon, authenticated;

-- 社區函式：收藏（每人每函式一列）。只允許操作自己的收藏。
create table if not exists public.community_function_favorites (
    user_id uuid not null references auth.users(id) on delete cascade,
    function_id uuid not null references public.community_functions(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, function_id)
);

alter table public.community_function_favorites enable row level security;

drop policy if exists "community_function_favorites_select_own" on public.community_function_favorites;
create policy "community_function_favorites_select_own" on public.community_function_favorites
    for select using (auth.uid() = user_id);
drop policy if exists "community_function_favorites_insert_own" on public.community_function_favorites;
create policy "community_function_favorites_insert_own" on public.community_function_favorites
    for insert with check (auth.uid() = user_id);
drop policy if exists "community_function_favorites_delete_own" on public.community_function_favorites;
create policy "community_function_favorites_delete_own" on public.community_function_favorites
    for delete using (auth.uid() = user_id);

-- 收藏數由觸發器維護，客戶端不送數字。
create or replace function public.community_function_favorites_touch()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if tg_op = 'INSERT' then
        update public.community_functions
           set favorite_count = favorite_count + 1
         where id = new.function_id;
        return new;
    elsif tg_op = 'DELETE' then
        update public.community_functions
           set favorite_count = greatest(favorite_count - 1, 0)
         where id = old.function_id;
        return old;
    end if;
    return null;
end;
$$;

drop trigger if exists community_function_favorites_count on public.community_function_favorites;
create trigger community_function_favorites_count
    after insert or delete on public.community_function_favorites
    for each row execute function public.community_function_favorites_touch();

-- 社區函式：評分（每人每函式一筆，可修改；1..5 星）。只允許操作自己的評分。
create table if not exists public.community_function_ratings (
    user_id uuid not null references auth.users(id) on delete cascade,
    function_id uuid not null references public.community_functions(id) on delete cascade,
    rating smallint not null check (rating between 1 and 5),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (user_id, function_id)
);

alter table public.community_function_ratings enable row level security;

drop policy if exists "community_function_ratings_select_own" on public.community_function_ratings;
create policy "community_function_ratings_select_own" on public.community_function_ratings
    for select using (auth.uid() = user_id);
drop policy if exists "community_function_ratings_insert_own" on public.community_function_ratings;
create policy "community_function_ratings_insert_own" on public.community_function_ratings
    for insert with check (auth.uid() = user_id);
drop policy if exists "community_function_ratings_update_own" on public.community_function_ratings;
create policy "community_function_ratings_update_own" on public.community_function_ratings
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "community_function_ratings_delete_own" on public.community_function_ratings;
create policy "community_function_ratings_delete_own" on public.community_function_ratings
    for delete using (auth.uid() = user_id);

-- 評分彙總（平均、筆數）由觸發器維護，客戶端不送數字。
create or replace function public.community_function_ratings_touch()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if tg_op = 'INSERT' then
        update public.community_functions
           set rating_count = rating_count + 1,
               rating_total = rating_total + new.rating
         where id = new.function_id;
        return new;
    elsif tg_op = 'UPDATE' then
        if new.rating is distinct from old.rating then
            update public.community_functions
               set rating_total = greatest(rating_total - old.rating + new.rating, 0)
             where id = new.function_id;
        end if;
        return new;
    elsif tg_op = 'DELETE' then
        update public.community_functions
           set rating_count = greatest(rating_count - 1, 0),
               rating_total = greatest(rating_total - old.rating, 0)
         where id = old.function_id;
        return old;
    end if;
    return null;
end;
$$;

drop trigger if exists community_function_ratings_count on public.community_function_ratings;
create trigger community_function_ratings_count
    after insert or update or delete on public.community_function_ratings
    for each row execute function public.community_function_ratings_touch();

-- 使用者操作自己的收藏/評分所需的表級權限（RLS 負責列級限制）。
grant select, insert, delete on public.community_function_favorites to authenticated;
grant select, insert, update, delete on public.community_function_ratings to authenticated;

-- 統計欄位與擁有者絕不信任客戶端：撤掉整表的 insert/update 授權，只開放
-- 內容欄位；統計欄位只由 security definer 的函式與觸發器更新。
revoke insert, update on public.community_functions from anon, authenticated;
grant insert (user_id, uploader_name, function_name, fx, fy, description, tags)
    on public.community_functions to authenticated;
grant update (uploader_name, function_name, fx, fy, description, tags, updated_at)
    on public.community_functions to authenticated;
revoke insert, update on public.community_levels from anon, authenticated;
grant insert (user_id, uploader_name, level_name, level_data)
    on public.community_levels to authenticated;
grant update (uploader_name, level_name, level_data)
    on public.community_levels to authenticated;

-- 舊版函式曾把原始玩家代號寫進 clear_players；改成只留每關的雜湊。
-- 'v1:' 前綴讓這段可以重複執行，已轉換的項目不會被再次雜湊。
update public.community_levels as cl
   set clear_players = coalesce(
       (select jsonb_agg(distinct
                   case when value like 'v1:%' then value
                        else 'v1:' || md5(cl.id::text || ':' || value)
                   end)
          from jsonb_array_elements_text(cl.clear_players) as value),
       '[]'::jsonb)
 where jsonb_typeof(cl.clear_players) = 'array'
   and cl.clear_players <> '[]'::jsonb;

-- ============================================================
-- Community custom levels: favorites and ratings (like functions)
-- Run this whole file on an existing project to upgrade it in place.
-- ============================================================

-- 1) the per-level counters live on the level row (never client-writable)
alter table public.community_levels
    add column if not exists favorite_count integer not null default 0,
    add column if not exists rating_count integer not null default 0,
    add column if not exists rating_total integer not null default 0;

-- 2) one favorite per (player, level); the counter is trigger-maintained
create table if not exists public.community_level_favorites (
    user_id uuid not null references auth.users(id) on delete cascade,
    level_id uuid not null references public.community_levels(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, level_id)
);

alter table public.community_level_favorites enable row level security;

drop policy if exists "community_level_favorites_select_own" on public.community_level_favorites;
create policy "community_level_favorites_select_own" on public.community_level_favorites
    for select using (auth.uid() = user_id);
drop policy if exists "community_level_favorites_insert_own" on public.community_level_favorites;
create policy "community_level_favorites_insert_own" on public.community_level_favorites
    for insert with check (auth.uid() = user_id);
drop policy if exists "community_level_favorites_delete_own" on public.community_level_favorites;
create policy "community_level_favorites_delete_own" on public.community_level_favorites
    for delete using (auth.uid() = user_id);

create or replace function public.community_level_favorites_touch()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if tg_op = 'INSERT' then
        update public.community_levels
           set favorite_count = favorite_count + 1
         where id = new.level_id;
        return new;
    elsif tg_op = 'DELETE' then
        update public.community_levels
           set favorite_count = greatest(favorite_count - 1, 0)
         where id = old.level_id;
        return old;
    end if;
    return null;
end;
$$;

drop trigger if exists community_level_favorites_count on public.community_level_favorites;
create trigger community_level_favorites_count
    after insert or delete on public.community_level_favorites
    for each row execute function public.community_level_favorites_touch();

-- 3) one rating per (player, level), changeable; aggregates are trigger-maintained
create table if not exists public.community_level_ratings (
    user_id uuid not null references auth.users(id) on delete cascade,
    level_id uuid not null references public.community_levels(id) on delete cascade,
    rating smallint not null check (rating between 1 and 5),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (user_id, level_id)
);

alter table public.community_level_ratings enable row level security;

drop policy if exists "community_level_ratings_select_own" on public.community_level_ratings;
create policy "community_level_ratings_select_own" on public.community_level_ratings
    for select using (auth.uid() = user_id);
drop policy if exists "community_level_ratings_insert_own" on public.community_level_ratings;
create policy "community_level_ratings_insert_own" on public.community_level_ratings
    for insert with check (auth.uid() = user_id);
drop policy if exists "community_level_ratings_update_own" on public.community_level_ratings;
create policy "community_level_ratings_update_own" on public.community_level_ratings
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "community_level_ratings_delete_own" on public.community_level_ratings;
create policy "community_level_ratings_delete_own" on public.community_level_ratings
    for delete using (auth.uid() = user_id);

create or replace function public.community_level_ratings_touch()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if tg_op = 'INSERT' then
        update public.community_levels
           set rating_count = rating_count + 1,
               rating_total = rating_total + new.rating
         where id = new.level_id;
        return new;
    elsif tg_op = 'UPDATE' then
        if new.rating is distinct from old.rating then
            update public.community_levels
               set rating_total = greatest(rating_total - old.rating + new.rating, 0)
             where id = new.level_id;
        end if;
        return new;
    elsif tg_op = 'DELETE' then
        update public.community_levels
           set rating_count = greatest(rating_count - 1, 0),
               rating_total = greatest(rating_total - old.rating, 0)
         where id = old.level_id;
        return old;
    end if;
    return null;
end;
$$;

drop trigger if exists community_level_ratings_count on public.community_level_ratings;
create trigger community_level_ratings_count
    after insert or update or delete on public.community_level_ratings
    for each row execute function public.community_level_ratings_touch();

-- 4) players manage their own rows only (RLS enforces it)
grant select, insert, delete on public.community_level_favorites to authenticated;
grant select, insert, update, delete on public.community_level_ratings to authenticated;

-- 5) the statistics columns are maintained by triggers/security-definer
--    functions only; the client may not write them (the grants above
--    already limit inserts/updates to the content columns).
revoke insert, update on public.community_levels from anon, authenticated;
grant insert (user_id, uploader_name, level_name, level_data)
    on public.community_levels to authenticated;
grant update (uploader_name, level_name, level_data)
    on public.community_levels to authenticated;