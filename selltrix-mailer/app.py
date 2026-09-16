# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl==3.1.5", "email-validator==2.3.0", "keyring>=25.0"]
# ///
# Run: uv run app.py (Windows: START.bat).
import sqlite3
import tkinter as tk
from functools import partial
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from zipfile import BadZipFile

from contacts import InputError, address, recipients
from engine import (
    SENDER,
    Campaign,
    Journal,
    deliver,
    preview_batch,
    run_batch,
    smtp_send,
)
from secrets_store import WindowsCredentialStore, load_password, save_password


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.base = Path(__file__).resolve().parent
        self.journal = Journal(self.base / "journal.sqlite3")
        self.emails: tuple[str, ...] = ()
        self.stop = Event()
        self.events: Queue[str] = Queue()
        self.worker: Thread | None = None
        root.title("SelltrixMailer · ff@selltrix.ru")
        root.geometry("960x820")
        root.minsize(800, 700)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="SelltrixMailer · локальная отправка", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(frame, text="От: Валерий Чегодайкин · Selltrix <ff@selltrix.ru> | SMTP Яндекса, TLS").pack(anchor="w")
        self.password = tk.StringVar()
        self.subject = tk.StringVar(value="Фулфилмент для WB и Ozon в Омске: услуги и стоимость")
        self.limit = tk.StringVar(value="20")
        self.start = tk.StringVar(value="10")
        self.end = tk.StringVar(value="17")
        self.interval = tk.StringVar(value="180")
        self.consent = tk.BooleanVar(value=False)
        self.optouts = tk.BooleanVar(value=False)
        ttk.Label(frame, text="Пароль приложения (можно сохранить в Credential Manager Windows)").pack(anchor="w", pady=(10, 0))
        ttk.Entry(frame, textvariable=self.password, show="*").pack(fill="x")
        ttk.Label(frame, text="Тема").pack(anchor="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.subject).pack(fill="x")
        ttk.Label(frame, text="Текст письма / предварительный просмотр (можно редактировать)").pack(anchor="w", pady=(8, 0))
        self.body = ScrolledText(frame, height=15, wrap="word", font=("Segoe UI", 10))
        self.body.pack(fill="both", expand=True)
        self.body.insert("1.0", (self.base / "letter.txt").read_text(encoding="utf-8"))
        settings = ttk.Frame(frame)
        settings.pack(fill="x", pady=8)
        for label, variable in (("Попыток/день", self.limit), ("С часа", self.start), ("До часа", self.end), ("Интервал, сек", self.interval)):
            ttk.Label(settings, text=label).pack(side="left", padx=3)
            ttk.Entry(settings, textvariable=variable, width=5).pack(side="left")
        ttk.Label(frame, text="Время Windows, ежедневно. Только пока окно открыто и ПК не спит. Лимит не гарантирует отсутствие блокировки.").pack(anchor="w")
        self.count = tk.StringVar(value="Excel не загружен. Отправка выключена.")
        ttk.Label(frame, textvariable=self.count).pack(anchor="w", pady=5)
        ttk.Checkbutton(frame, variable=self.consent, text="У выбранных получателей есть согласие на рекламные письма от нас").pack(anchor="w")
        ttk.Checkbutton(frame, variable=self.optouts, text="Перед этой партией проверены ответы, отписки и недоставки; стоп-лист обновлён").pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=8)
        for label, command in (("Сохранить пароль для автозапуска", self.save_password), ("Загрузить Excel", self.load), ("Предпросмотр без отправки", self.preview), ("Тест себе", self.test), ("Запустить партию", self.start_batch), ("СТОП", self.stop.set), ("Стоп-лист +", self.suppress), ("Журнал", self.report)):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=2)
        self.log = ScrolledText(frame, height=6, wrap="word", state="disabled")
        self.log.pack(fill="x")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(200, self.poll)

    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def load(self) -> None:
        if self.busy():
            messagebox.showinfo("Партия работает", "Сначала нажмите СТОП и дождитесь завершения.")
            return
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        self.emails = ()
        self.consent.set(False)
        self.optouts.set(False)
        self.count.set("Загрузка...")
        try:
            emails, skipped = recipients(Path(path))
            self.emails = tuple(emails)
            self.count.set(f"Разрешено в Excel: {len(emails)}; исключено: {skipped}. Журнал и стоп-лист проверяются при отправке.")
        except (InputError, OSError, BadZipFile, ValueError, KeyError) as exc:
            self.count.set("Импорт не выполнен. Очередь пуста.")
            messagebox.showerror("Excel", str(exc))

    def config(self) -> Campaign:
        return Campaign(self.subject.get(), self.body.get("1.0", "end-1c"), int(self.limit.get()), int(self.start.get()), int(self.end.get()), int(self.interval.get()))

    def launch(self, campaign: Campaign, emails: tuple[str, ...], *, test: bool) -> None:
        password = self.password.get()
        if not password.strip():
            password = load_password(WindowsCredentialStore())
        self.password.set("")
        self.stop.clear()
        self.optouts.set(False)
        def work() -> None:
            try:
                send = partial(smtp_send, password=password)
                if test:
                    accepted = deliver(self.journal, campaign, emails[0], send=send, test=True)
                    self.events.put("Тест принят SMTP. Проверьте свой ящик." if accepted else "Тест пропущен: адрес в стоп-листе.")
                else:
                    run_batch(campaign, emails, journal=self.journal, stop=self.stop, send=send, notify=self.events.put)
            except (InputError, OSError, sqlite3.Error, ValueError) as exc:
                self.events.put(str(exc))
            finally:
                self.events.put("Работа завершена. Новая партия требует подтверждения и ввода пароля.")
        self.worker = Thread(target=work, daemon=False)
        self.worker.start()

    def save_password(self) -> None:
        try:
            save_password(WindowsCredentialStore(), self.password.get())
            self.password.set("")
            messagebox.showinfo("Автозапуск", "Пароль сохранён в Credential Manager Windows для текущего пользователя.")
        except InputError as exc:
            messagebox.showerror("Автозапуск", str(exc))

    def preview(self) -> None:
        if self.busy():
            return
        try:
            campaign = self.config()
            if not self.emails:
                raise InputError("Сначала загрузите Excel с утверждёнными получателями.")
            report = preview_batch(self.journal, campaign, self.emails)
            addresses = "\n".join(report.ready[:10]) or "нет"
            messagebox.showinfo(
                "Предпросмотр без отправки",
                f"Готово к новой попытке: {len(report.ready)}\n"
                f"В стоп-листе: {len(report.suppressed)}\n"
                f"Уже в журнале: {len(report.already_recorded)}\n"
                f"Остаток дневного лимита: {report.remaining_today}\n\n"
                f"Первые адреса:\n{addresses}\n\n"
                "Письма не отправлялись и журнал не изменён.",
            )
        except (InputError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Предпросмотр", str(exc))

    def test(self) -> None:
        if self.busy():
            return
        try:
            campaign = self.config()
            raw = simpledialog.askstring("Тест", "Введите свой email для одного тестового письма:")
            if not raw:
                return
            email = address(raw)
            if messagebox.askyesno("Отправить тест?", f"От: {SENDER}\nКому: {email}\nТема: {campaign.subject}\n\nПодтверждаете, что это ваш тестовый адрес?"):
                self.launch(campaign, (email,), test=True)
        except (InputError, ValueError) as exc:
            messagebox.showerror("Настройки", str(exc))

    def start_batch(self) -> None:
        if self.busy():
            return
        try:
            campaign = self.config()
            if not self.emails or not self.consent.get() or not self.optouts.get():
                raise InputError("Загрузите утверждённый список и подтвердите согласия и проверку отписок.")
            preview = "\n".join(self.emails[:10])
            if messagebox.askyesno("Подтвердить реальную отправку", f"От: {SENDER}\nТема: {campaign.subject}\nВ списке: {len(self.emails)}\nЛимит: {campaign.daily_limit} попыток/день\nЧасы Windows: {campaign.start_hour}–{campaign.end_hour}\nПервые адреса:\n{preview}\n\nОтправлять текст, показанный в окне?"):
                self.launch(campaign, self.emails, test=False)
        except (InputError, ValueError) as exc:
            messagebox.showerror("Настройки", str(exc))

    def suppress(self) -> None:
        if self.busy():
            self.stop.set()
            messagebox.showinfo("Остановка", "Дождитесь завершения текущего письма, затем добавьте адрес.")
            return
        raw = simpledialog.askstring("Стоп-лист", "Email отказавшегося получателя или адрес с постоянной недоставкой:")
        if raw:
            try:
                self.journal.suppress(address(raw))
                self.events.put("Адрес добавлен в постоянный стоп-лист.")
            except (InputError, sqlite3.Error) as exc:
                messagebox.showerror("Стоп-лист", str(exc))

    def report(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Журнал и стоп-лист")
        text = ScrolledText(window, width=110, height=30)
        text.pack(fill="both", expand=True)
        text.insert("1.0", self.journal.report())
        text.configure(state="disabled")

    def poll(self) -> None:
        try:
            while True:
                text = self.events.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", text + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except Empty:
            self.root.after(200, self.poll)

    def close(self) -> None:
        self.stop.set()
        if self.busy():
            messagebox.showinfo("Остановка", "Ожидается завершение текущего SMTP-запроса. Закройте окно после сообщения о завершении.")
            return
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
