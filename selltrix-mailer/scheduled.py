# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl==3.1.5", "email-validator==2.3.0", "keyring>=25.0", "typer>=0.16"]
# ///
"""Run one bounded, non-GUI campaign from Windows Task Scheduler."""
from __future__ import annotations

import sqlite3
from functools import partial
from pathlib import Path
from threading import Event
from typing import Final

import typer

from contacts import InputError, recipients
from engine import BatchPreview, Campaign, Journal, preview_batch, run_batch, smtp_send
from inbox import sync_opt_outs
from secrets_store import WindowsCredentialStore, load_password

BASE: Final = Path(__file__).resolve().parent
WORKBOOK: Final = BASE / "Контакты_очищенные.xlsx"
JOURNAL: Final = BASE / "journal.sqlite3"
SUBJECT: Final = "Фулфилмент для WB и Ozon в Омске: услуги и стоимость"


def campaign() -> Campaign:
    """Return the reviewed default campaign used by the Windows client."""
    return Campaign(SUBJECT, (BASE / "letter.txt").read_text(encoding="utf-8"), 20, 10, 17, 180)


def dry_run(workbook: Path, journal_path: Path) -> BatchPreview:
    """Preview approved contacts without network calls or journal writes."""
    emails, _ = recipients(workbook)
    return preview_batch(Journal(journal_path), campaign(), tuple(emails))


def run() -> None:
    """Deliver one bounded batch only after every local guard succeeds."""
    emails, _ = recipients(WORKBOOK)
    journal = Journal(JOURNAL)
    password = load_password(WindowsCredentialStore())
    opt_outs = sync_opt_outs(journal, password)
    typer.echo(f"Отказы: {len(opt_outs.suppressed)}; обычные ответы: {opt_outs.ignored}")
    run_batch(
        campaign(),
        tuple(emails),
        journal=journal,
        stop=Event(),
        send=partial(smtp_send, password=password),
        notify=typer.echo,
    )


def main(dry_run_mode: bool = typer.Option(False, "--dry-run")) -> None:
    """Provide the task scheduler's no-send validation mode."""
    try:
        if dry_run_mode:
            report = dry_run(WORKBOOK, JOURNAL)
            typer.echo(
                f"Готово: {len(report.ready)}; стоп-лист: {len(report.suppressed)}; "
                f"журнал: {len(report.already_recorded)}; лимит сегодня: {report.remaining_today}"
            )
            return
        run()
    except (InputError, OSError, sqlite3.Error) as exc:
        typer.echo(f"Ошибка: {exc}", err=True)
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    typer.run(main)
