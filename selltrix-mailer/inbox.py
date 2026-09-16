"""Synchronize explicit email opt-outs into the persistent stop-list."""
from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import imaplib
import ssl
from typing import Final

from contacts import InputError, address
from engine import Journal, SENDER

IMAP_HOST: Final = "imap.yandex.ru"
IMAP_PORT: Final = 993
OPT_OUT_PHRASES: Final = (
    "не писать",
    "не пишите",
    "больше не пишите",
    "не присылайте больше",
    "исключите меня из рассылки",
    "удалите меня из рассылки",
    "unsubscribe",
)


@dataclass(frozen=True, slots=True)
class InboundMessage:
    uid: str
    sender: str
    text: str


@dataclass(frozen=True, slots=True)
class OptOutResult:
    suppressed: tuple[str, ...]
    ignored: int


def is_opt_out(text: str) -> bool:
    """Recognize only unambiguous stop requests; uncertain replies are retained."""
    reply = text.split("-----original message-----", 1)[0]
    reply = "\n".join(line for line in reply.splitlines() if not line.lstrip().startswith(">"))
    normalized = " ".join(reply.casefold().split())
    return any(phrase in normalized for phrase in OPT_OUT_PHRASES)


def process_opt_outs(journal: Journal, messages: tuple[InboundMessage, ...]) -> OptOutResult:
    """Add explicit opt-outs once; normal replies never change the stop-list."""
    suppressed: list[str] = []
    for message in messages:
        if is_opt_out(message.text):
            journal.suppress(message.sender)
            suppressed.append(message.sender)
    return OptOutResult(tuple(suppressed), len(messages) - len(suppressed))


def _message_text(raw: bytes) -> str:
    """Extract plain text safely from a fetched RFC 822 message."""
    message = BytesParser(policy=policy.default).parsebytes(raw)
    body = message.get_body(preferencelist=("plain",))
    return "" if body is None else body.get_content()


def sync_opt_outs(journal: Journal, password: str) -> OptOutResult:
    """Read unseen inbox messages, suppress explicit refusals, then mark them read."""
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context()) as client:
            client.login(SENDER, password)
            status, _ = client.select("INBOX")
            if status != "OK":
                raise InputError("Не удалось открыть папку Входящие Яндекс.Почты.")
            status, data = client.uid("search", None, "UNSEEN")
            if status != "OK":
                raise InputError("Не удалось прочитать новые письма Яндекс.Почты.")
            messages: list[InboundMessage] = []
            for uid_bytes in data[0].split():
                uid = uid_bytes.decode("ascii")
                status, fetched = client.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    raise InputError("Не удалось прочитать новое письмо Яндекс.Почты.")
                raw = fetched[0][1]
                parsed = BytesParser(policy=policy.default).parsebytes(raw)
                sender = address(parseaddr(parsed.get("Reply-To") or parsed.get("From") or "")[1])
                messages.append(InboundMessage(uid, sender, _message_text(raw)))
            result = process_opt_outs(journal, tuple(messages))
            for message in messages:
                client.uid("store", message.uid, "+FLAGS", "(\\Seen)")
            return result
    except (imaplib.IMAP4.error, OSError, UnicodeDecodeError) as exc:
        raise InputError("Не удалось обработать входящие Яндекс.Почты; рассылка остановлена.") from exc
