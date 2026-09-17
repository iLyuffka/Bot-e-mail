import sys
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contacts import RecipientBatch, recipients


def test_recipients_streams_approved_addresses_after_counting_them(tmp_path: Path) -> None:
    # Given: an approved recipient list with an unapproved row and a duplicate.
    path = tmp_path / "contacts.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "К отправке"
    sheet.append(["email", "approved"])
    sheet.append(["first@example.com", "ДА"])
    sheet.append(["skip@example.com", "нет"])
    sheet.append(["first@example.com", "ДА"])
    sheet.append(["second@example.com", "ДА"])
    book.save(path)

    # When: the file is prepared for a campaign.
    batch = recipients(path)

    # Then: the UI receives only metadata and delivery can iterate addresses lazily.
    assert isinstance(batch, RecipientBatch)
    assert batch.allowed == 2
    assert batch.skipped == 2
    assert len(batch) == 2
    assert not hasattr(batch, "emails")
    assert tuple(batch) == ("first@example.com", "second@example.com")
    assert tuple(batch) == ("first@example.com", "second@example.com")
