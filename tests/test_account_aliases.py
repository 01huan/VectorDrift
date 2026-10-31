from vector_drift.account import local_profile_manager as base
from vector_drift.account import (
    guest_manager,
    guest_profile,
    guest_profile_manager,
    guest_session,
    local_data,
    local_manager,
    local_profile,
    local_store,
)


def test_alias_modules_expose_same_api():
    for mod in (
        guest_manager,
        guest_profile,
        guest_profile_manager,
        guest_session,
        local_data,
        local_manager,
        local_profile,
        local_store,
    ):
        assert mod.LocalProfileManager.__name__ == base.LocalProfileManager.__name__
        assert set(dir(mod.LocalProfileManager)) >= {"save", "load", "clear", "exists"}
