# -*- coding: utf-8 -*-
"""
db.py — لایه پایگاه داده آنتانو (SQLite)
جدول‌ها: کاربران، کدهای ثبت‌نام، نشست‌ها، گفتگوها، پیام‌ها، حافظه بلندمدت
"""
import sqlite3
import os
import secrets
import hashlib

DB_PATH = os.environ.get("ANTANU_DB", "antanu.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------- رمزنگاری گذرواژه (PBKDF2 - بدون نیاز به کتابخانه اضافی) ----------

def hash_pw(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${h}"


def verify_pw(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return secrets.compare_digest(calc, h)


# ---------- ساختار جدول‌ها ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,
    stars       INTEGER NOT NULL DEFAULT 1,     -- سطح اشتراک: ۱ تا ۴ ستاره
    is_admin    INTEGER NOT NULL DEFAULT 0,
    device_fp   TEXT,                            -- اثر انگشت دستگاه (قفل یک‌دستگاهی)
    avatar      TEXT,                            -- عکس پروفایل (base64)
    expires_at  TEXT,                            -- پایان اعتبار اشتراک (۳۰ روز)
    code_used   TEXT,                            -- کدی که با آن ثبت‌نام کرده
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,            -- کد ۵۰ رقمی حروف و عدد
    stars       INTEGER NOT NULL,                -- سطح اشتراکی که این کد می‌دهد
    used        INTEGER NOT NULL DEFAULT 0,
    used_by     TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT,
    share_token TEXT,                            -- توکن اشتراک‌گذاری عمومی (فقط‌خواندنی)
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,               -- user | assistant
    content         TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS uploads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    content     TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'text',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,               -- chat | image | video | article
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage ON usage_log(user_id, kind, created_at);

CREATE TABLE IF NOT EXISTS knowledge (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bib_refs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ref_type    TEXT NOT NULL DEFAULT 'article',  -- article | book | website | thesis | conference
    authors     TEXT,                             -- نویسندگان (با ؛ جدا)
    title       TEXT NOT NULL,                    -- عنوان اثر
    year        TEXT,                             -- سال انتشار
    source      TEXT,                             -- نام مجله/ناشر/کنفرانس
    volume      TEXT,                             -- دوره
    issue       TEXT,                             -- شماره
    pages       TEXT,                             -- صفحات
    url         TEXT,                             -- نشانی/DOI
    note        TEXT,                             -- یادداشت آزاد
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bib ON bib_refs(user_id, created_at);

CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username    TEXT,                             -- نام کاربری در لحظه ثبت
    category    TEXT NOT NULL DEFAULT 'idea',     -- idea | bug | feature | other
    content     TEXT NOT NULL,                    -- متن ایده/نظر کاربر
    status      TEXT NOT NULL DEFAULT 'new',      -- new | seen | done
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_feedback ON feedback(status, created_at);

CREATE TABLE IF NOT EXISTS glossary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lang          TEXT NOT NULL DEFAULT 'hy',   -- کد زبان مبدأ (hy = ارمنی)
    term          TEXT NOT NULL,                -- کلمه/عبارت به زبان اصلی
    translation   TEXT,                         -- ترجمه فارسی
    pronunciation TEXT,                         -- تلفظ با حروف انگلیسی (فینگلیش)
    status        TEXT NOT NULL DEFAULT 'done', -- done | pending (منتظر تکمیل خودکار)
    source        TEXT NOT NULL DEFAULT 'seed', -- seed | auto | user
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_glossary_term ON glossary(lang, term);
"""


def init_db():
    """ساخت جدول‌ها و کاربر ادمین پیش‌فرض (اگر وجود نداشته باشد)"""
    conn = get_db()
    conn.executescript(SCHEMA)
    try:
        conn.execute("ALTER TABLE uploads ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")
    except Exception:
        pass  # ستون از قبل وجود دارد
    try:
        conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE usage_log ADD COLUMN amount INTEGER NOT NULL DEFAULT 1")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN expires_at TEXT")
        # کاربران قدیمی: ۳۰ روز از امروز
        conn.execute("UPDATE users SET expires_at = datetime('now', '+30 days') WHERE is_admin = 0 AND expires_at IS NULL")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE conversations ADD COLUMN share_token TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except Exception:
        pass
    # زبان انتخابی کاربر (خالی = زبان پیش‌فرض سایت، یعنی انگلیسی)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN lang TEXT")
    except Exception:
        pass
    # جلوگیری از ثبت‌نام دوباره با یک ایمیل (یکتا بودن ایمیل‌های واقعی)
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email "
            "ON users(email) WHERE email IS NOT NULL AND email <> ''"
        )
    except Exception:
        pass

    admin_user = os.environ.get("ANTANU_ADMIN_USER", "admin")
    admin_pass = os.environ.get("ANTANU_ADMIN_PASS", "Antanu@1234")

    row = conn.execute("SELECT id FROM users WHERE username = ?", (admin_user,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users (username, password, stars, is_admin) VALUES (?, ?, 4, 1)",
            (admin_user, hash_pw(admin_pass)),
        )
        print(f"[ANTANU] کاربر ادمین ساخته شد → نام کاربری: {admin_user}")

    conn.commit()
    conn.close()


# ---------- تولید کد ثبت‌نام ۵۰ رقمی ----------

CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_code() -> str:
    return "".join(secrets.choice(CODE_CHARS) for _ in range(50))
