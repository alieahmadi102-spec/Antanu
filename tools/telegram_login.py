# -*- coding: utf-8 -*-
"""
telegram_login.py — ورود یک‌باره به تلگرام (فقط در ترمینال).

چرا جداست؟ تلگرام برای ورود یک کد تأیید می‌فرستد و باید همان لحظه تایپ شود.
این کار از داخل یک درخواست وب شدنی نیست، پس یک بار اینجا انجام می‌شود و
فایل نشست (antanu.session) ساخته می‌شود. بعد از آن، همگام‌سازی کتاب‌ها از پنل
مدیریت بدون هیچ کدی کار می‌کند.

روش اجرا (روی سرور، داخل پوشه‌ی پروژه):

    python tools/telegram_login.py

اگر با داکر کار می‌کنی:

    docker compose run --rm -it antanu python tools/telegram_login.py

هشدار: فایل antanu.session مثل رمز عبور توست. در .gitignore هست و هرگز
نباید به گیت‌هاب یا جای دیگری فرستاده شود.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env():
    """خواندن .env بدون وابستگی اضافه (اگر python-dotenv بود، از آن)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except Exception:
        pass
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def main():
    _load_env()
    from library import telegram_sync

    ok, why = telegram_sync.is_configured()
    if not ok:
        print("✗", why)
        print("\nراهنما:")
        print("  ۱) به my.telegram.org برو و با شماره‌ی خودت وارد شو")
        print("  ۲) API development tools را باز کن و یک اپ بساز")
        print("  ۳) api_id و api_hash را در فایل .env بگذار:")
        print("       TELEGRAM_API_ID=1234567")
        print("       TELEGRAM_API_HASH=abcdef...")
        print("       TELEGRAM_BOOKS_CHANNEL=@your_channel")
        return 1

    try:
        from telethon import TelegramClient  # noqa: F401
    except ImportError:
        print("✗ telethon نصب نیست. اجرا کن:  pip install telethon")
        return 1

    print("فایل نشست:", telegram_sync.SESSION)
    if telegram_sync.has_session():
        print("یک نشست از قبل هست؛ اگر معتبر باشد دوباره کد نمی‌خواهد.")

    client = telegram_sync._client()
    await client.start()          # اگر لازم باشد، شماره و کد را می‌پرسد

    me = await client.get_me()
    name = " ".join(x for x in [getattr(me, "first_name", ""),
                                getattr(me, "last_name", "")] if x)
    print(f"\n✓ وارد شدی: {name} (@{getattr(me, 'username', '') or '—'})")

    channel = os.environ["TELEGRAM_BOOKS_CHANNEL"]
    try:
        ent = await client.get_entity(channel)
        title = getattr(ent, "title", None) or getattr(ent, "username", channel)
        print(f"✓ کانال پیدا شد: {title}")
    except Exception as e:
        print(f"⚠ کانال «{channel}» پیدا نشد: {e}")
        print("  مطمئن شو عضو کانال هستی و نامش را درست نوشته‌ای (مثلاً @my_books).")

    await client.disconnect()
    print("\nحالا برو به پنل مدیریت ← کارت «کتابخانه‌ی هوشمند» ← دکمه‌ی همگام‌سازی.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nلغو شد.")
        sys.exit(1)
