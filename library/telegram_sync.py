# -*- coding: utf-8 -*-
"""
telegram_sync.py — دانلود کتاب‌های کانال تلگرام و افزودنشان به کتابخانه‌ی هوشمند.

با Telethon و **حساب کاربری خودِ مالک** وصل می‌شود، نه ربات؛ چون ربات‌های تلگرام
فقط تا ۲۰ مگابایت می‌توانند فایل بگیرند و بیشتر کتاب‌ها بزرگ‌ترند.

ورود یک‌باره در ترمینال انجام می‌شود (tools/telegram_login.py) و فایل نشست ساخته
می‌شود؛ بعد از آن همگام‌سازی از پنل مدیریت بدون نیاز به کد کار می‌کند.

هر کتاب جداگانه در try/except است: خرابی یکی، بقیه را متوقف نمی‌کند.
فایل خام بعد از استخراج متن حذف می‌شود تا دیسک پر نشود.
"""
import asyncio
import os
import threading

from . import extractors, rag_engine

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS_DIR = os.environ.get("ANTANU_BOOKS_DIR", os.path.join(_BASE, "books_raw"))
SESSION = os.environ.get("ANTANU_TG_SESSION", os.path.join(_BASE, "antanu.session"))

# جلوگیری از اجرای هم‌زمان دو همگام‌سازی
_running = threading.Lock()
_state = {"running": False, "done": 0, "total": 0, "added": 0,
          "skipped": 0, "failed": 0, "message": "", "finished_at": ""}


def status() -> dict:
    return dict(_state)


def is_configured():
    """آیا کلیدهای تلگرام در .env هست؟ (پیام فارسیِ روشن اگر نه)"""
    missing = [k for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH",
                           "TELEGRAM_BOOKS_CHANNEL") if not os.environ.get(k)]
    if missing:
        return False, ("این‌ها در فایل .env تنظیم نشده‌اند: " + "، ".join(missing) +
                       " — API_ID و API_HASH را از my.telegram.org بگیر.")
    return True, ""


def _session_base() -> str:
    """مسیر نشست بدون پسوند — تلثون خودش «.session» را می‌چسباند.

    اگر مقدار محیطی با «.session» تمام شود آن را برمی‌داریم، وگرنه دو بار پسوند
    می‌خورد و فایلی که می‌سازد با فایلی که دنبالش می‌گردیم یکی نمی‌شود.
    """
    return SESSION[:-8] if SESSION.endswith(".session") else SESSION


def has_session() -> bool:
    return os.path.exists(_session_base() + ".session")


def _client():
    from telethon import TelegramClient
    base = _session_base()
    d = os.path.dirname(base)
    if d:
        os.makedirs(d, exist_ok=True)
    return TelegramClient(base,
                          int(os.environ["TELEGRAM_API_ID"]),
                          os.environ["TELEGRAM_API_HASH"])


async def sync_channel(progress=None, limit: int = None) -> dict:
    """کتاب‌های تازه‌ی کانال را دانلود، متن‌کاوی و به پایگاه برداری اضافه می‌کند.

    progress: تابعی که پیام پیشرفت می‌گیرد (برای لاگ یا نمایش در پنل)
    limit:    حداکثر تعداد پیامِ بررسی‌شده (برای آزمایش)
    """
    def say(msg):
        _state["message"] = msg
        if progress:
            try:
                progress(msg)
            except Exception:
                pass
        print("[ANTANU library]", msg, flush=True)

    ok, why = is_configured()
    if not ok:
        return {"ok": False, "error": why}
    if not rag_engine.available():
        return {"ok": False, "error": rag_engine.unavailable_reason()}
    if not has_session():
        return {"ok": False, "error":
                "هنوز به تلگرام وارد نشده‌ای. یک بار در ترمینال اجرا کن: "
                "python tools/telegram_login.py"}
    if not _running.acquire(blocking=False):
        return {"ok": False, "error": "یک همگام‌سازی از قبل در حال اجراست."}

    _state.update({"running": True, "done": 0, "total": 0, "added": 0,
                   "skipped": 0, "failed": 0, "finished_at": ""})
    os.makedirs(BOOKS_DIR, exist_ok=True)
    channel = os.environ["TELEGRAM_BOOKS_CHANNEL"]

    client = None
    try:
        client = _client()
        await client.connect()
        if not await client.is_user_authorized():
            return {"ok": False, "error":
                    "نشست تلگرام معتبر نیست. دوباره اجرا کن: python tools/telegram_login.py"}
        say(f"اتصال برقرار شد؛ در حال خواندن کانال {channel}…")

        # اول فهرست پیام‌های دارای فایلِ پشتیبانی‌شده
        msgs = []
        async for m in client.iter_messages(channel, limit=limit):
            if not getattr(m, "file", None):
                continue
            name = getattr(m.file, "name", None) or ""
            if not name:
                ext = getattr(m.file, "ext", "") or ""
                name = f"book-{m.id}{ext}"
            if extractors.is_supported(name):
                msgs.append((m, name))
        _state["total"] = len(msgs)
        say(f"{len(msgs)} فایل کتاب در کانال پیدا شد.")

        for idx, (m, name) in enumerate(msgs, 1):
            _state["done"] = idx
            path = None
            try:
                if rag_engine.book_exists(m.id):
                    _state["skipped"] += 1
                    continue
                safe = "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip()[:120]
                path = os.path.join(BOOKS_DIR, f"{m.id}-{safe}")
                await client.download_media(m, file=path)
                text = extractors.extract_text(path)
                if not text:
                    _state["skipped"] += 1
                    say(f"({idx} از {len(msgs)}) «{safe[:40]}» متن قابل‌استفاده نداشت — رد شد")
                    continue
                title = os.path.splitext(safe)[0]
                n = rag_engine.add_book(m.id, title, text)
                if n:
                    _state["added"] += 1
                    say(f"({idx} از {len(msgs)}) «{title[:40]}» افزوده شد — {n} قطعه")
                else:
                    _state["skipped"] += 1
            except Exception as e:
                _state["failed"] += 1
                say(f"({idx} از {len(msgs)}) خطا در «{name[:40]}»: {str(e)[:80]}")
            finally:
                # فایل خام را نگه نمی‌داریم؛ متن در پایگاه برداری هست
                if path:
                    for p in (path, path + ".tmp"):
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except OSError:
                            pass

        import datetime as _dt
        _state["finished_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        say(f"پایان: {_state['added']} کتاب تازه، {_state['skipped']} رد شده، "
            f"{_state['failed']} خطا.")
        # running را همین‌جا پایین می‌آوریم تا گزارشِ بازگشتی «هنوز در حال اجرا»
        # نگوید؛ finally هم در مسیرهای خطا همین کار را می‌کند.
        _state["running"] = False
        return {"ok": True, **status()}
    except Exception as e:
        say(f"همگام‌سازی ناتمام ماند: {str(e)[:120]}")
        return {"ok": False, "error": f"همگام‌سازی ناتمام ماند: {e}"}
    finally:
        # اتصال باید در هر حالتی بسته شود، وگرنه نشست باز می‌ماند و
        # همگام‌سازی بعدی به دردسر می‌افتد.
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        _state["running"] = False
        try:
            _running.release()
        except RuntimeError:
            pass


def sync_channel_blocking(progress=None, limit: int = None) -> dict:
    """اجرای همگام‌سازی از یک نخِ معمولی (برای BackgroundTasks فست‌ای‌پی‌آی)."""
    try:
        return asyncio.run(sync_channel(progress=progress, limit=limit))
    except Exception as e:
        _state["running"] = False
        return {"ok": False, "error": str(e)}
