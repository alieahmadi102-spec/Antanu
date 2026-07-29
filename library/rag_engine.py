# -*- coding: utf-8 -*-
"""
rag_engine.py — قطعه‌بندی، بردارسازی و جستجوی معنایی کتاب‌ها (ChromaDB).

چرا «معنایی»؟ جستجوی کلیدواژه‌ای فقط وقتی جواب می‌دهد که کاربر دقیقاً همان واژه‌های
کتاب را به کار ببرد. جستجوی معنایی، «سود خالص چطور حساب می‌شود؟» را به بخشی از کتاب
وصل می‌کند که درباره‌ی «محاسبه‌ی درآمد و هزینه» نوشته، حتی بدون واژه‌ی مشترک.

همه‌ی این ماژول اختیاری است. اگر chromadb یا sentence-transformers نصب نباشند،
available() مقدار False می‌دهد و بقیه‌ی توابع بی‌سروصدا نتیجه‌ی خالی برمی‌گردانند —
پس چت آنتانو هیچ‌وقت به این بخش وابسته نمی‌شود.

مدل بردارساز «تنبل» بارگذاری می‌شود: تا وقتی واقعاً جستجو یا افزودن کتابی نباشد،
هیچ حافظه‌ای مصرف نمی‌کند و بالا آمدن سرور کند نمی‌شود.
"""
import os
import re
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DIR = os.environ.get("ANTANU_CHROMA_DIR", os.path.join(_BASE, "chroma_db"))
COLLECTION = "antanu_books"

# مدل چندزبانه‌ای که فارسی را خوب می‌فهمد و محلی و رایگان است
EMBED_MODEL = os.environ.get("ANTANU_EMBED_MODEL",
                             "paraphrase-multilingual-MiniLM-L12-v2")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
MIN_CHUNK = 50

_lock = threading.Lock()
_client = None
_collection = None
_embedder = None
_unavailable_reason = ""
_model_error = ""


# ---------------- در دسترس بودن ----------------

def available() -> bool:
    """آیا کتابخانه‌های لازم برای جستجوی معنایی نصب‌اند؟"""
    global _unavailable_reason
    try:
        import chromadb          # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except ImportError as e:
        _unavailable_reason = str(e)
        return False


def unavailable_reason() -> str:
    if available():
        return ""
    return (_unavailable_reason or "کتابخانه‌های chromadb و sentence-transformers نصب نیستند") + \
        " — برای روشن‌کردن جستجوی معنایی: pip install chromadb sentence-transformers"


# ---------------- قطعه‌بندی ----------------

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """متن را به تیکه‌های ~۸۰۰ نویسه‌ای با هم‌پوشانی می‌شکند.

    مرز شکستن ترجیحاً پایان پاراگراف یا جمله است تا تیکه وسط کلمه قطع نشود.
    تیکه‌های خیلی کوتاه دور ریخته می‌شوند.
    """
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if not text:
        return []
    out, i = [], 0
    n = len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            window = text[i:end]
            cut = max(window.rfind("\n\n"), window.rfind("۔"), window.rfind("."),
                      window.rfind("؟"), window.rfind("!"), window.rfind("\n"))
            if cut > size * 0.5:
                end = i + cut + 1
        piece = text[i:end].strip()
        if len(piece) >= MIN_CHUNK:
            out.append(piece)
        nxt = end - overlap
        i = nxt if nxt > i else end
    return out


# ---------------- پایگاه برداری ----------------

def _get_embedder():
    """مدل بردارساز — فقط یک بار و فقط وقتی واقعاً لازم شد.

    بار اول مدل (~۵۰۰ مگابایت) از اینترنت گرفته می‌شود. اگر سرور به اینترنت
    دسترسی نداشته باشد یا رم کم بیاورد، خطای خام و نامفهوم بالا می‌آید؛ اینجا
    آن را به یک پیام فارسیِ روشن تبدیل و ذخیره می‌کنیم تا پنل مدیریت بتواند
    دلیل واقعی را نشان دهد، نه فقط «نشد».
    """
    global _embedder, _model_error
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(EMBED_MODEL)
            _model_error = ""
        except Exception as e:
            _model_error = (
                f"مدل بردارساز «{EMBED_MODEL}» بارگذاری نشد: {str(e)[:200]} — "
                "بار اول باید از اینترنت دانلود شود (حدود ۵۰۰ مگابایت). "
                "مطمئن شو سرور به huggingface.co دسترسی دارد و رم کافی هست."
            )
            raise RuntimeError(_model_error) from e
    return _embedder


def model_ready() -> bool:
    """آیا مدل بردارساز واقعاً بالا می‌آید؟ (یک بار امتحان می‌کند و نتیجه را نگه می‌دارد)"""
    if not available():
        return False
    try:
        _get_embedder()
        return True
    except Exception:
        return False


def model_error() -> str:
    return _model_error


def _embed(texts):
    model = _get_embedder()
    vecs = model.encode(list(texts), show_progress_bar=False,
                        convert_to_numpy=True, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def get_collection():
    """کالکشن کتاب‌ها روی دیسک (chroma_db/). در نبود کتابخانه‌ها None می‌دهد."""
    global _client, _collection
    if not available():
        return None
    with _lock:
        if _collection is not None:
            return _collection
        import chromadb
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_or_create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"})
        return _collection


def book_exists(book_id) -> bool:
    """آیا این کتاب قبلاً اضافه شده؟ (جلوی پردازش دوباره را می‌گیرد)"""
    col = get_collection()
    if col is None:
        return False
    try:
        got = col.get(where={"book_id": str(book_id)}, limit=1)
        return bool(got and got.get("ids"))
    except Exception:
        return False


def add_book(book_id, title: str, text: str) -> int:
    """یک کتاب را قطعه‌بندی، بردارسازی و ذخیره می‌کند. تعداد قطعه‌ها را می‌دهد."""
    col = get_collection()
    if col is None:
        return 0
    chunks = chunk_text(text)
    if not chunks:
        return 0
    bid = str(book_id)
    ids = [f"{bid}:{i}" for i in range(len(chunks))]
    metas = [{"book_id": bid, "book_title": str(title)[:300], "chunk_index": i}
             for i in range(len(chunks))]
    # دسته‌دسته، تا حافظه روی سرور کوچک پر نشود
    step = 64
    added = 0
    for s in range(0, len(chunks), step):
        part = chunks[s:s + step]
        col.add(ids=ids[s:s + step], documents=part,
                embeddings=_embed(part), metadatas=metas[s:s + step])
        added += len(part)
    return added


def search(query: str, top_k: int = 5):
    """مرتبط‌ترین تیکه‌ها: [{text, book_title, book_id, score}, …]"""
    col = get_collection()
    if col is None or not (query or "").strip():
        return []
    try:
        res = col.query(query_embeddings=_embed([query]), n_results=max(1, int(top_k)))
    except Exception:
        return []
    out = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for i, doc in enumerate(docs):
        m = metas[i] if i < len(metas) else {}
        d = dists[i] if i < len(dists) else None
        out.append({
            "text": doc,
            "book_title": (m or {}).get("book_title", "کتاب"),
            "book_id": (m or {}).get("book_id", ""),
            "score": (round(1 - float(d), 3) if d is not None else None),
        })
    return out


def stats() -> dict:
    """آمار کتابخانه برای پنل مدیریت."""
    if not available():
        return {"available": False, "reason": unavailable_reason(),
                "books": 0, "chunks": 0}
    col = get_collection()
    if col is None:
        return {"available": False, "reason": unavailable_reason(),
                "books": 0, "chunks": 0}
    try:
        n = int(col.count())
    except Exception:
        n = 0
    books = 0
    try:
        # شمردن کتاب‌های یکتا از روی متادیتا
        got = col.get(include=["metadatas"], limit=100000)
        books = len({(m or {}).get("book_id") for m in (got.get("metadatas") or [])} - {None})
    except Exception:
        pass
    return {"available": True, "reason": _model_error, "books": books, "chunks": n,
            "path": CHROMA_DIR, "model": EMBED_MODEL, "model_error": _model_error}


def clear() -> bool:
    """کل کتابخانه‌ی برداری را پاک می‌کند."""
    global _collection
    if not available():
        return False
    try:
        import chromadb
        col = get_collection()
        if col is None:
            return False
        with _lock:
            _client.delete_collection(COLLECTION)
            _collection = None
        get_collection()
        return True
    except Exception:
        return False


def context_for(query: str, top_k: int = 4, budget: int = 3500) -> str:
    """متن آماده برای گذاشتن در پرامپت، با ذکر نام کتاب منبع."""
    hits = search(query, top_k=top_k)
    if not hits:
        return ""
    parts, used = [], 0
    for h in hits:
        piece = f"[از کتاب «{h['book_title']}»]: {h['text']}"
        if used + len(piece) > budget:
            break
        parts.append(piece)
        used += len(piece)
    return "\n\n".join(parts)
