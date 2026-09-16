"""Credential Manager adapter for the Yandex application password."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

import keyring
from keyring.errors import KeyringError

from contacts import InputError

SERVICE: Final = "SelltrixMailer"
USERNAME: Final = "ff@selltrix.ru"


class CredentialStore(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...


@dataclass(frozen=True, slots=True)
class MissingCredential(InputError):
    detail: str = "Пароль приложения не сохранён в Диспетчере учётных данных Windows."


class WindowsCredentialStore:
    """Use the platform keyring; Windows selects Credential Manager."""

    def get_password(self, service: str, username: str) -> str | None:
        try:
            return keyring.get_password(service, username)
        except KeyringError as exc:
            raise InputError("Не удалось прочитать Credential Manager Windows.") from exc

    def set_password(self, service: str, username: str, password: str) -> None:
        try:
            keyring.set_password(service, username, password)
        except KeyringError as exc:
            raise InputError("Не удалось сохранить пароль в Credential Manager Windows.") from exc


def save_password(store: CredentialStore, password: str) -> None:
    """Store a non-empty application password outside files and the journal."""
    if not password.strip():
        raise InputError("Введите пароль приложения перед сохранением.")
    store.set_password(SERVICE, USERNAME, password)


def load_password(store: CredentialStore) -> str:
    """Read the password or fail before a journal reservation is made."""
    password = store.get_password(SERVICE, USERNAME)
    if password is None or not password.strip():
        raise MissingCredential()
    return password
