"""Exceptions raised by the account subsystem."""


class AccountError(Exception):
    """Base class for account-related errors."""


class NotConfiguredError(AccountError):
    """Raised when Supabase credentials are missing."""


class AuthenticationError(AccountError):
    """Raised when sign-in / sign-up fails."""


class NetworkError(AccountError):
    """Raised when a network request fails."""


class ProfileError(AccountError):
    """Raised when reading/writing the player profile fails."""
