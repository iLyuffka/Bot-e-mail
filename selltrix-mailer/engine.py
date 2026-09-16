"""Persistent reservations and bounded SMTP delivery, without automatic retries."""
import smtplib
import sqlite3
import ssl
import uuid
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from threading import Event
from typing import Final

from contacts import InputError

SENDER: Final = "ff@selltrix.ru"
SENDER_NAME: Final = "Валерий Чегодайкин · Selltrix"


@dataclass(frozen=True, slots=True)
class Campaign:
    subject: str
    body: str
    daily_limit: int
    start_hour: int
    end_hour: int
    interval: int

    def __post_init__(self) -> None:
        if not self.subject.strip() or any(c in self.subject for c in "\r\n"):
            raise InputError("Тема пуста или содержит перенос строки.")
        if not self.body.strip():
            raise InputError("Текст письма пуст.")
        if not 1 <= self.daily_limit <= 100:
            raise InputError("Лимит пилота: от 1 до 100 попыток в день.")
        if not 0 <= self.start_hour < self.end_hour <= 24:
            raise InputError("Часы: 0 ≤ начало < конец ≤ 24.")
        if not 60 <= self.interval <= 3600:
            raise InputError("Интервал: от 60 до 3600 секунд.")


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS attempts (
                    key TEXT PRIMARY KEY, email TEXT NOT NULL, day TEXT NOT NULL,
                    status TEXT NOT NULL, message_id TEXT NOT NULL, time TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS suppressed (email TEXT PRIMARY KEY);
            """)

    def suppress(self, email: str) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR IGNORE INTO suppressed VALUES (?)", (email,))

    def reserve(self, email: str, limit: int, *, test: bool = False) -> str | None:
        now = datetime.now().astimezone()
        key = str(uuid.uuid4()) if test else email
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM suppressed WHERE email=?", (email,)).fetchone():
                return None
            if db.execute("SELECT 1 FROM attempts WHERE key=?", (key,)).fetchone():
                return None
            count = db.execute("SELECT COUNT(*) FROM attempts WHERE day=?", (now.date().isoformat(),)).fetchone()[0]
            if count >= limit:
                raise InputError("Дневной лимит достигнут. Следующую партию запустите завтра вручную.")
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?)", (
                key, email, now.date().isoformat(), "reserved", make_msgid(domain="selltrix.ru"), now.isoformat(),
            ))
        return key

    def finish(self, key: str, status: str) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE attempts SET status=? WHERE key=?", (status, key))

    def message_id(self, key: str) -> str:
        with closing(sqlite3.connect(self.path)) as db:
            return str(db.execute("SELECT message_id FROM attempts WHERE key=?", (key,)).fetchone()[0])

    def report(self) -> str:
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT time,email,status FROM attempts ORDER BY time DESC LIMIT 500").fetchall()
            excluded = db.execute("SELECT email FROM suppressed ORDER BY email").fetchall()
        return "Последние 500 попыток:\n" + "\n".join(" | ".join(map(str, r)) for r in rows) + "\n\nСтоп-лист:\n" + "\n".join(str(r[0]) for r in excluded)


def smtp_send(message: EmailMessage, password: str) -> None:
    """Do not treat QUIT failure as failure of an already accepted message."""
    server = smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=30, context=ssl.create_default_context())
    try:
        server.login(SENDER, password)
        server.send_message(message)
    finally:
        server.close()


def deliver(journal: Journal, campaign: Campaign, email: str, *,
            send: Callable[[EmailMessage], None], test: bool = False) -> bool:
    key = journal.reserve(email, campaign.daily_limit, test=test)
    if key is None:
        return False
    message = EmailMessage()
    message["From"] = formataddr((SENDER_NAME, SENDER))
    message["To"] = email
    message["Subject"] = campaign.subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = journal.message_id(key)
    message.set_content(campaign.body)
    try:
        send(message)
    except (OSError, smtplib.SMTPException):
        journal.finish(key, "uncertain_or_failed")
        raise InputError("Ошибка SMTP/сети. Отправка остановлена. Проверьте вход, ограничения и доставку; автоматического повтора не будет.") from None
    journal.finish(key, "smtp_accepted")
    return True


def run_batch(campaign: Campaign, emails: Iterable[str], *, journal: Journal,
              stop: Event, send: Callable[[EmailMessage], None], notify: Callable[[str], None]) -> None:
    """A daily batch expires at midnight; next day's opt-outs require review."""
    day = datetime.now().astimezone().date()
    for email in emails:
        if stop.is_set() or datetime.now().astimezone().date() != day:
            break
        now = datetime.now().astimezone()
        if now.hour >= campaign.end_hour:
            notify("Окно отправки закончилось. Новую партию запустите вручную.")
            break
        while datetime.now().astimezone().hour < campaign.start_hour:
            if stop.wait(1) or datetime.now().astimezone().date() != day:
                return
        if stop.is_set() or datetime.now().astimezone().hour >= campaign.end_hour:
            break
        sent = deliver(journal, campaign, email, send=send)
        notify(f"{email}: " + ("принято SMTP (не подтверждение доставки)" if sent else "пропущен: уже в журнале / стоп-листе"))
        if sent and stop.wait(campaign.interval):
            break
