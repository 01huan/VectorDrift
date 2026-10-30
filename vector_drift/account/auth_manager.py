"""Authentication and account orchestration (async, non-blocking)."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .errors import AccountError, AuthenticationError
from .models import AccountUser, PlayerProfile
from .profile_manager import ProfileManager
from .local_profile_manager import LocalProfileManager
from .session_manager import SessionManager
from .supabase_client import get_client, is_configured


@dataclass
class _Task:
    kind: str
    fn: Callable[[], Any]
    on_success: Optional[Callable[[Any], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None


class AccountManager:
    def __init__(self) -> None:
        self.session_manager = SessionManager()
        self.profile_manager = ProfileManager()
        self._queue: "queue.Queue" = queue.Queue()

        self.current_user: Optional[AccountUser] = None
        self.profile: Optional[PlayerProfile] = None
        self.status: str = "guest"
        self.last_error: Optional[str] = None
        self.is_busy: bool = False

    def is_configured(self) -> bool:
        return is_configured()

    def is_authenticated(self) -> bool:
        return self.current_user is not None and self.status == "authenticated"

    def reset_to_guest(self) -> None:
        self.current_user = None
        self.profile = None
        self.status = "guest"
        self.last_error = None

    def _run_async(
        self,
        kind: str,
        fn: Callable[[], Any],
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        if not self.is_configured():
            if on_error:
                on_error(AccountError("Supabase is not configured"))
            return

        if self.is_busy:
            if on_error:
                on_error(AccountError("Another request is already in progress. Please wait."))
            return

        task = _Task(kind=kind, fn=fn, on_success=on_success, on_error=on_error)
        self.is_busy = True

        def worker() -> None:
            try:
                result = task.fn()
            except Exception as exc:  # noqa: BLE001
                self._queue.put((task, None, exc))
                return
            self._queue.put((task, result, None))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self) -> None:
        while True:
            try:
                task, result, exc = self._queue.get_nowait()
            except queue.Empty:
                break
            self.is_busy = False
            if exc is not None:
                self.last_error = str(exc)
                if task.on_error:
                    task.on_error(exc)
            else:
                self.last_error = None
                if task.on_success:
                    task.on_success(result)

    # ------------------------------------------------------------------ auth
    def sign_up_async(
        self,
        email: str,
        password: str,
        on_success: Optional[Callable[[AccountUser], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def fn() -> tuple[AccountUser, Optional[PlayerProfile]]:
            client = get_client()
            resp = client.auth.sign_up({"email": email, "password": password})
            user = getattr(resp, "user", None)
            if user is None:
                raise AuthenticationError("Sign up failed: no user returned")
            session = getattr(resp, "session", None)
            account_user = AccountUser(
                id=user.id,
                email=user.email,
                email_confirmed=bool(getattr(user, "email_confirmed_at", None)),
                access_token=getattr(session, "access_token", None) if session else None,
                refresh_token=getattr(session, "refresh_token", None) if session else None,
            )
            if account_user.access_token and account_user.refresh_token:
                self.session_manager.save(
                    {
                        "user_id": account_user.id,
                        "email": account_user.email,
                        "access_token": account_user.access_token,
                        "refresh_token": account_user.refresh_token,
                    }
                )
            profile: Optional[PlayerProfile] = None
            if account_user.access_token:
                try:
                    profile = self.profile_manager.ensure_exists(account_user.id, account_user.email)
                except Exception as exc:  # noqa: BLE001
                    self.last_error = f"Profile unavailable: {exc}"
            return account_user, profile

        def success(result: Any) -> None:
            account_user, profile = result
            self.current_user = account_user
            self.profile = profile
            if account_user.email_confirmed or account_user.access_token:
                self.status = "authenticated"
            else:
                self.status = "pending_verification"
            if on_success:
                on_success(account_user)

        def error(exc: Exception) -> None:
            self.last_error = str(exc)
            if on_error:
                on_error(exc)

        self._run_async("sign_up", fn, success, error)

    def sign_in_async(
        self,
        email: str,
        password: str,
        on_success: Optional[Callable[[AccountUser], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def fn() -> tuple[AccountUser, Optional[PlayerProfile]]:
            client = get_client()
            resp = client.auth.sign_in_with_password({"email": email, "password": password})
            user = getattr(resp, "user", None)
            session = getattr(resp, "session", None)
            if user is None or session is None:
                raise AuthenticationError("Sign in failed: invalid credentials")
            account_user = AccountUser(
                id=user.id,
                email=user.email,
                email_confirmed=bool(getattr(user, "email_confirmed_at", None)),
                access_token=session.access_token,
                refresh_token=session.refresh_token,
            )
            self.session_manager.save(
                {
                    "user_id": account_user.id,
                    "email": account_user.email,
                    "access_token": account_user.access_token,
                    "refresh_token": account_user.refresh_token,
                }
            )
            profile = None
            try:
                profile = self.profile_manager.fetch(account_user.id)
                if profile is None:
                    profile = self.profile_manager.ensure_exists(account_user.id, account_user.email)
            except Exception as exc:  # noqa: BLE001
                # Do not fail login if the profiles table is missing/misconfigured.
                self.last_error = f"Profile unavailable: {exc}"
            return account_user, profile

        def success(result: Any) -> None:
            account_user, profile = result
            self.current_user = account_user
            self.profile = profile
            self.status = "authenticated"
            if on_success:
                on_success(account_user)

        def error(exc: Exception) -> None:
            self.last_error = str(exc)
            if on_error:
                on_error(exc)

        self._run_async("sign_in", fn, success, error)

    def sign_out_async(
        self,
        on_success: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def fn() -> None:
            try:
                get_client().auth.sign_out()
            except Exception:
                pass
            self.session_manager.clear()
            return None

        def success(_: Any) -> None:
            self.reset_to_guest()
            if on_success:
                on_success()

        def error(exc: Exception) -> None:
            self.session_manager.clear()
            self.reset_to_guest()
            if on_error:
                on_error(exc)

        self._run_async("sign_out", fn, success, error)

    def request_password_reset_async(
        self,
        email: str,
        on_success: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def fn() -> None:
            get_client().auth.reset_password_for_email(email)
            return None

        def success(_: Any) -> None:
            if on_success:
                on_success()

        def error(exc: Exception) -> None:
            self.last_error = str(exc)
            if on_error:
                on_error(exc)

        self._run_async("password_reset", fn, success, error)

    def restore_session_async(
        self,
        on_success: Optional[Callable[[AccountUser], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def fn() -> tuple[AccountUser, Optional[PlayerProfile]]:
            data = self.session_manager.load()
            if not data:
                raise AuthenticationError("No saved session")
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            if not access_token or not refresh_token:
                raise AuthenticationError("Saved session is incomplete")
            client = get_client()
            user = None
            try:
                client.auth.set_session(access_token, refresh_token)
                user_resp = client.auth.get_user()
                user = getattr(user_resp, "user", None)
            except Exception:
                user = None
            if user is None:
                resp = client.auth.refresh_session(refresh_token)
                user = getattr(resp, "user", None)
                session = getattr(resp, "session", None)
                if user is None or session is None:
                    raise AuthenticationError("Session expired")
                access_token = session.access_token
                refresh_token = session.refresh_token
            account_user = AccountUser(
                id=user.id,
                email=user.email,
                email_confirmed=bool(getattr(user, "email_confirmed_at", None)),
                access_token=access_token,
                refresh_token=refresh_token,
            )
            self.session_manager.save(
                {
                    "user_id": account_user.id,
                    "email": account_user.email,
                    "access_token": account_user.access_token,
                    "refresh_token": account_user.refresh_token,
                }
            )
            profile = None
            if account_user.access_token:
                try:
                    profile = self.profile_manager.fetch(account_user.id)
                    if profile is None:
                        profile = self.profile_manager.ensure_exists(account_user.id, account_user.email)
                except Exception as exc:  # noqa: BLE001
                    self.last_error = f"Profile unavailable: {exc}"
            return account_user, profile

        def success(result: Any) -> None:
            account_user, profile = result
            self.current_user = account_user
            self.profile = profile
            self.status = "authenticated"
            if on_success:
                on_success(account_user)

        def error(exc: Exception) -> None:
            self.session_manager.clear()
            self.reset_to_guest()
            if on_error:
                on_error(exc)

        self._run_async("restore_session", fn, success, error)

    def load_profile_async(
        self,
        on_success: Optional[Callable[[PlayerProfile], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        if self.current_user is None:
            if on_error:
                on_error(AuthenticationError("Not authenticated"))
            return

        def fn() -> PlayerProfile:
            try:
                profile = self.profile_manager.fetch(self.current_user.id)
                if profile is None:
                    profile = self.profile_manager.ensure_exists(self.current_user.id, self.current_user.email)
                return profile
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Profile unavailable (run docs/supabase_schema.sql): {exc}") from exc

        def success(result: Any) -> None:
            self.profile = result
            if on_success:
                on_success(result)

        def error(exc: Exception) -> None:
            self.last_error = str(exc)
            if on_error:
                on_error(exc)

        self._run_async("load_profile", fn, success, error)

    def save_profile_async(
        self,
        profile: PlayerProfile,
        on_success: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def fn() -> None:
            try:
                self.profile_manager.upsert(profile)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Profile save failed (run docs/supabase_schema.sql): {exc}") from exc
            return None

        def success(_: Any) -> None:
            self.profile = profile
            if on_success:
                on_success()

        def error(exc: Exception) -> None:
            self.last_error = str(exc)
            if on_error:
                on_error(exc)

        self._run_async("save_profile", fn, success, error)


    # --------------------------------------------------------------- guest/local
    def load_guest_profile(self):
        return self.local_profile_manager.load()

    def save_guest_profile(self, profile_or_session=None):
        self.local_profile_manager.save(profile_or_session)

    def clear_guest_profile(self):
        self.local_profile_manager.clear()

    def delete_local_data(self, session=None):
        self.local_profile_manager.clear()
        if session is not None:
            from .integration import reset_session_to_guest
            reset_session_to_guest(session)

    def delete_local_records(self, session=None):
        self.delete_local_data(session)
