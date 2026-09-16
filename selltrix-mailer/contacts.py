"""Read only explicitly approved, unflagged Excel recipients."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from openpyxl import load_workbook


@dataclass(frozen=True, slots=True)
class InputError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def address(value: str) -> str:
    try:
        return validate_email(
            value.strip(), check_deliverability=False, allow_smtputf8=False,
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise InputError(f"Некорректный email: {value}") from exc


def recipients(path: Path) -> tuple[list[str], int]:
    """Require an explicit approval column; do not infer consent from names."""
    with closing(load_workbook(path, read_only=True, data_only=False)) as book:
        sheet_name = "К отправке"
        if sheet_name not in book.sheetnames:
            sheet_name = "Очищенный список"
        if sheet_name not in book.sheetnames:
            raise InputError("Нужен лист «К отправке» или «Очищенный список».")
        rows = book[sheet_name].iter_rows(values_only=True)
        header = [str(v or "").strip().lower() for v in next(rows, ())]
        email_key = "email" if "email" in header else "почта"
        if email_key not in header or "approved" not in header:
            raise InputError("Добавьте столбец approved: ДА только для согласованных получателей.")
        email_i, approved_i = header.index(email_key), header.index("approved")
        flag_i = header.index("флаги") if "флаги" in header else None
        blocked: set[str] = set()
        for name in ("Исправления доменов", "Требует проверки", "Полный аудит изменений"):
            if name not in book.sheetnames:
                continue
            for row in book[name].iter_rows(min_row=2, values_only=True):
                if len(row) >= 7 and (name != "Полный аудит изменений" or "R3" in str(row[6])):
                    blocked.add(str(row[4] or "").strip().lower())
        result: list[str] = []
        seen: set[str] = set()
        skipped = 0
        for row in rows:
            raw = str(row[email_i] or "").strip()
            approved = str(row[approved_i] or "").strip().upper() == "ДА"
            flagged = flag_i is not None and bool(row[flag_i])
            try:
                email = address(raw)
            except InputError:
                skipped += 1
                continue
            if not approved or flagged or email in blocked or email in seen:
                skipped += 1
                continue
            seen.add(email)
            result.append(email)
        return result, skipped
