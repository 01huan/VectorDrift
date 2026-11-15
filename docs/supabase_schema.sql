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
