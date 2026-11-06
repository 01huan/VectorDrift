import os

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://jowxwvngepntavrtuzbg.supabase.co"
)

SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "sb_publishable_088ZQZsX2J5wv1WFriWIcQ_0zqd5N1S"
)

SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", SUPABASE_KEY)