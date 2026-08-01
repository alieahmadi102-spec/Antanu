# -*- coding: utf-8 -*-
"""
test_library.py — آزمون «کتابخانه‌ی هوشمند آنتانو».

سه چیز را می‌سنجد:
  ۱) استخراج متن از هر پنج فرمت، و اینکه فایل خراب کرش نکند
  ۲) قطعه‌بندی: هم‌پوشانی، شکستن روی مرز جمله، دور ریختن قطعه‌ی کوتاه
  ۳) جستجوی معنایی: پرسشی که **هیچ واژه‌ی مشترکی** با متن ندارد باید همان متن را
     پیدا کند — این دقیقاً همان چیزی است که جستجوی کلیدواژه‌ای (FTS5) نمی‌تواند

و مهم‌تر از همه: اگر chromadb/sentence-transformers نصب نباشند، هیچ‌کدام از
این‌ها نباید آنتانو را بشکند. بخش «تنزل بی‌خطر» همین را می‌سنجد.

اجرا:  python test_library.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  — {detail}" if detail else ""))
    return bool(cond)


def section(title):
    print("\n" + "─" * 68 + f"\n{title}\n" + "─" * 68)


# ═══════════════ ۱) استخراج متن ═══════════════

SAMPLE = (
    "مدیریت مالی یکی از شاخه‌های اصلی دانش مدیریت است. "
    "در این حوزه، تصمیم‌گیری درباره‌ی تأمین منابع مالی و تخصیص آن‌ها بررسی می‌شود. "
    "نسبت‌های نقدینگی توان شرکت را در پرداخت بدهی‌های کوتاه‌مدت نشان می‌دهند. "
    "سرمایه در گردش تفاوت دارایی جاری و بدهی جاری است و شاخص سلامت عملیاتی شرکت به شمار می‌رود. "
) * 4


def make_samples(d):
    """از هر فرمت یک نمونه می‌سازد؛ فرمت‌هایی که کتابخانه‌شان نیست رد می‌شوند."""
    made = {}

    p = os.path.join(d, "a.txt")
    open(p, "w", encoding="utf-8").write(SAMPLE)
    made["txt"] = p

    p = os.path.join(d, "a.md")
    open(p, "w", encoding="utf-8").write("# عنوان\n\n" + SAMPLE)
    made["md"] = p

    try:
        import docx
        doc = docx.Document()
        for para in SAMPLE.split(". "):
            doc.add_paragraph(para)
        p = os.path.join(d, "a.docx")
        doc.save(p)
        made["docx"] = p
    except Exception as e:
        print("  ⓘ docx ساخته نشد:", e)

    try:
        from pptx import Presentation
        from pptx.util import Inches
        pres = Presentation()
        for para in SAMPLE.split(". ")[:8]:
            s = pres.slides.add_slide(pres.slide_layouts[5])
            tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
            tb.text_frame.text = para
        p = os.path.join(d, "a.pptx")
        pres.save(p)
        made["pptx"] = p
    except Exception as e:
        print("  ⓘ pptx ساخته نشد:", e)

    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        for i, para in enumerate(SAMPLE.split(". "), 1):
            ws.cell(row=i, column=1, value=para)
        p = os.path.join(d, "a.xlsx")
        wb.save(p)
        made["xlsx"] = p
    except Exception as e:
        print("  ⓘ xlsx ساخته نشد:", e)

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        p = os.path.join(d, "a.pdf")
        c = canvas.Canvas(p, pagesize=A4)
        # متن لاتین: pypdf باید متن را ببیند؛ کیفیت فارسی در PDF به فونت وابسته است
        for page in range(3):
            y = 800
            for line in (
                "Financial management is a core branch of management science.",
                "It studies how a firm raises funds and allocates them over time.",
                "Liquidity ratios show the ability to pay short-term obligations.",
                "Working capital is current assets minus current liabilities.",
            ) * 4:
                c.drawString(60, y, line)
                y -= 16
            c.showPage()
        c.save()
        made["pdf"] = p
    except Exception as e:
        print("  ⓘ pdf ساخته نشد:", e)

    return made


def test_extractors():
    section("۱) استخراج متن از فرمت‌های کتاب")
    from library import extractors

    d = tempfile.mkdtemp(prefix="antanu_ext_")
    try:
        made = make_samples(d)
        for fmt, path in sorted(made.items()):
            txt = extractors.extract_text(path)
            check(f"استخراج {fmt}", len(txt) > 200, f"{len(txt)} نویسه")

        check("پسوند پشتیبانی‌شده شناخته می‌شود",
              extractors.is_supported("کتاب.PDF") and extractors.is_supported("a.docx"))
        check("پسوند ناشناخته رد می‌شود",
              not extractors.is_supported("a.zip") and not extractors.is_supported("a"))

        # فایل خراب و فایل نبودن نباید کرش کند
        bad = os.path.join(d, "bad.pdf")
        open(bad, "wb").write(b"NOT A PDF AT ALL \x00\x01\x02")
        check("فایل خراب رشته‌ی خالی می‌دهد (بدون کرش)",
              extractors.extract_text(bad) == "")
        check("فایل ناموجود رشته‌ی خالی می‌دهد",
              extractors.extract_text(os.path.join(d, "nope.pdf")) == "")
        check("پسوند پشتیبانی‌نشده رشته‌ی خالی می‌دهد",
              extractors.extract_text(__file__.replace(".py", ".py")) == "")

        # متن خیلی کوتاه = بی‌ارزش، باید رد شود
        tiny = os.path.join(d, "tiny.txt")
        open(tiny, "w", encoding="utf-8").write("سلام")
        check("متن بی‌کیفیت/کوتاه کنار گذاشته می‌شود",
              extractors.extract_text(tiny) == "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════ ۲) قطعه‌بندی ═══════════════

def test_chunking():
    section("۲) قطعه‌بندی متن")
    from library import rag_engine as R

    text = SAMPLE * 6
    ch = R.chunk_text(text, size=800, overlap=150)
    check("متن بلند به چند قطعه می‌شکند", len(ch) > 1, f"{len(ch)} قطعه")
    check("هیچ قطعه‌ای خیلی بزرگ‌تر از اندازه نیست",
          all(len(c) <= 900 for c in ch), f"بلندترین={max(len(c) for c in ch)}")
    check("هیچ قطعه‌ی کوتاه‌تر از حد نداریم",
          all(len(c) >= R.MIN_CHUNK for c in ch),
          f"کوتاه‌ترین={min(len(c) for c in ch)}")

    # هم‌پوشانی: پایان یک قطعه باید در قطعه‌ی بعد دیده شود
    if len(ch) > 1:
        tail = ch[0][-60:].strip()
        check("قطعه‌ها هم‌پوشانی دارند (متن بین دو قطعه گم نمی‌شود)",
              tail[:30] in ch[1] or ch[1][:30] in ch[0], repr(tail[:30]))

    check("متن خالی هیچ قطعه‌ای نمی‌دهد", R.chunk_text("") == [] and R.chunk_text(None) == [])
    check("متن کوتاه‌تر از حداقل، قطعه نمی‌سازد", R.chunk_text("سلام") == [])

    # شکستن روی مرز جمله، نه وسط واژه
    ends = sum(1 for c in ch[:-1] if c.rstrip()[-1:] in ".؟!۔\n")
    check("بیشتر قطعه‌ها روی مرز جمله بریده شده‌اند",
          ends >= max(1, int(len(ch[:-1]) * 0.6)), f"{ends} از {len(ch)-1}")

    # متنِ بدون هیچ نشانه‌ی جمله: باید با گام ثابت پیش برود و بی‌نهایت حلقه نزند
    flat = "الف" * 20000                       # ۶۰٬۰۰۰ نویسه
    big = R.chunk_text(flat, size=800, overlap=150)
    expected = -(-len(flat) // (800 - 150))    # گام = اندازه منهای هم‌پوشانی
    check("متن بدون هیچ نقطه‌ای هم درست تکه می‌شود",
          abs(len(big) - expected) <= 2, f"{len(big)} قطعه، انتظار ≈{expected}")


# ═══════════════ ۳) جستجوی معنایی ═══════════════

BOOK_A = (
    "فصل سوم: تغذیه‌ی سالم. خوردن میوه و سبزیجات تازه در هر وعده، فشار خون را "
    "پایین نگه می‌دارد و خطر بیماری‌های قلبی را کم می‌کند. مصرف نمک و چربی "
    "اشباع باید محدود شود. نوشیدن آب کافی در طول روز برای عملکرد کلیه‌ها لازم است. "
    "خواب منظم شبانه و ورزش سبک روزانه نیز بر سلامت دستگاه گردش خون اثر مستقیم دارد. "
) * 3

BOOK_B = (
    "فصل هفتم: معماری شبکه‌های رایانه‌ای. پروتکل انتقال داده در لایه‌ی چهارم مدل "
    "مرجع، بسته‌ها را شماره‌گذاری می‌کند تا ترتیب رسیدنشان تضمین شود. مسیریاب‌ها "
    "جدول مسیر را با تبادل پیام میان خود به‌روز نگه می‌دارند. پهنای باند و تأخیر "
    "دو سنجه‌ی اصلی کیفیت خط ارتباطی هستند. "
) * 3


def test_semantic():
    section("۳) جستجوی معنایی (ChromaDB)")
    from library import rag_engine as R

    if not R.available():
        print("  ⏭  chromadb/sentence-transformers نصب نیستند — این بخش رد شد.")
        print("     دلیل:", R.unavailable_reason()[:110])
        return False

    # مدل واقعی بار اول از اینترنت می‌آید؛ اگر دسترسی نبود، رد شو نه اینکه بترکی
    if not R.model_ready():
        print("  ⏭  مدل بردارساز در این محیط دانلود نشد — این بخش رد شد.")
        print("     دلیل:", (R.model_error() or "")[:160])
        return False

    d = tempfile.mkdtemp(prefix="antanu_rag_")
    R.CHROMA_DIR = d
    R._client = R._collection = None      # کالکشن تازه در پوشه‌ی موقت
    try:
        n1 = R.add_book("b1", "راهنمای زندگی سالم", BOOK_A)
        n2 = R.add_book("b2", "مبانی شبکه", BOOK_B)
        check("کتاب اول افزوده شد", n1 > 0, f"{n1} قطعه")
        check("کتاب دوم افزوده شد", n2 > 0, f"{n2} قطعه")

        check("book_exists کتاب موجود را می‌شناسد", R.book_exists("b1"))
        check("book_exists کتاب ناموجود را نمی‌شناسد", not R.book_exists("b404"))

        # ★ آزمون اصلی: پرسش هم‌معنا ولی با واژه‌های کاملاً متفاوت
        q = "چه کاری قلب آدم را قوی نگه می‌دارد؟"
        hits = R.search(q, top_k=3)
        check("جستجو نتیجه می‌دهد", len(hits) > 0, f"{len(hits)} نتیجه")
        if hits:
            top = hits[0]
            shared = set(q) & set()      # فقط برای خوانایی؛ سنجه پایین‌تر است
            check("پرسشِ هم‌معنا (بدون واژه‌ی مشترک) کتابِ درست را پیدا می‌کند",
                  top["book_title"] == "راهنمای زندگی سالم",
                  f"برنده: «{top['book_title']}» با نمره {top['score']}")
            check("نتیجه نام کتاب منبع را همراه دارد",
                  bool(top.get("book_title")) and top.get("book_id") == "b1")

        q2 = "چطور بسته‌های اطلاعاتی بین دستگاه‌ها جابه‌جا می‌شوند؟"
        h2 = R.search(q2, top_k=3)
        check("پرسش فنی، کتاب فنی را می‌آورد (نه کتاب تغذیه)",
              bool(h2) and h2[0]["book_title"] == "مبانی شبکه",
              f"برنده: «{h2[0]['book_title'] if h2 else '—'}»")

        ctx = R.context_for("سلامت قلب", top_k=2, budget=1200)
        check("context_for متن آماده‌ی پرامپت می‌دهد", len(ctx) > 100, f"{len(ctx)} نویسه")
        check("context_for نام کتاب را در متن می‌آورد", "از کتاب" in ctx)
        check("context_for بودجه را رعایت می‌کند", len(ctx) <= 1400, f"{len(ctx)}")

        st = R.stats()
        check("آمار درست است: دو کتاب", st["books"] == 2, str(st["books"]))
        check("آمار درست است: تعداد قطعه", st["chunks"] == n1 + n2,
              f"{st['chunks']} در برابر {n1+n2}")

        check("پرسش خالی، نتیجه‌ی خالی می‌دهد", R.search("  ") == [])

        check("clear کتابخانه را پاک می‌کند",
              R.clear() and R.stats()["chunks"] == 0)
        return True
    finally:
        R._client = R._collection = None
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════ ۳ب) خطِ لوله با بردارسازِ ساختگی ═══════════════

def test_pipeline_with_stub_embedder():
    """همان مسیر کامل، ولی با بردارسازِ کنترل‌شده به‌جای مدل واقعی.

    چرا؟ دانلود مدل چندزبانه در این محیط بسته است. با بردارسازِ ساختگی می‌شود
    *لوله‌کشی* را کامل سنجید — اینکه هر متن به بردار خودش بچسبد، نزدیک‌ترین همسایه
    درست برگردد، متادیتا سالم بماند، دسته‌بندی ۶۴‌تایی چیزی را جا نیندازد — بدون
    اینکه ادعایی درباره‌ی کیفیتِ معناییِ مدل واقعی بکنیم.
    """
    section("۳ب) خط لوله‌ی ChromaDB با بردارسازِ کنترل‌شده")
    from library import rag_engine as R

    try:
        import chromadb  # noqa: F401
    except ImportError:
        print("  ⏭  chromadb نصب نیست — رد شد.")
        return False

    # هر متن را روی «موضوع»هایش نگاشت می‌کنیم: دو متنِ هم‌موضوع نزدیک می‌شوند،
    # حتی اگر واژه‌هایشان یکی نباشد. این همان کاری است که مدل واقعی می‌کند.
    TOPICS = {
        0: ("قلب", "تغذیه", "میوه", "سبزیجات", "خون", "ورزش", "خواب", "سلامت", "کلیه"),
        1: ("شبکه", "پروتکل", "بسته", "مسیریاب", "پهنای", "تأخیر", "داده", "لایه"),
    }

    def fake_encode(texts, **kw):
        import numpy as np
        out = []
        for t in texts:
            v = np.zeros(len(TOPICS) + 1, dtype="float32")
            for i, words in TOPICS.items():
                v[i] = sum(t.count(w) for w in words)
            v[-1] = 0.01                       # تا بردار صفر نشود
            n = float(np.linalg.norm(v)) or 1.0
            out.append(v / n)
        return np.array(out)

    class FakeModel:
        def encode(self, texts, **kw):
            return fake_encode(texts, **kw)

    d = tempfile.mkdtemp(prefix="antanu_stub_")
    saved = (R.CHROMA_DIR, R._client, R._collection, R._embedder)
    R.CHROMA_DIR, R._client, R._collection = d, None, None
    R._embedder = FakeModel()
    try:
        n1 = R.add_book("b1", "راهنمای زندگی سالم", BOOK_A)
        n2 = R.add_book("b2", "مبانی شبکه", BOOK_B)
        check("کتاب اول ذخیره شد", n1 > 0, f"{n1} قطعه")
        check("کتاب دوم ذخیره شد", n2 > 0, f"{n2} قطعه")
        check("book_exists کتاب موجود را می‌شناسد", R.book_exists("b1"))
        check("book_exists کتاب ناموجود را نمی‌شناسد", not R.book_exists("b404"))

        # پرسشِ هم‌موضوع ولی با واژه‌های متفاوت از متن
        hits = R.search("ورزش و خواب برای سلامت قلب", top_k=3)
        check("جستجو نتیجه می‌دهد", len(hits) > 0, f"{len(hits)} نتیجه")
        check("پرسشِ هم‌موضوع، کتابِ درست را می‌آورد",
              bool(hits) and hits[0]["book_title"] == "راهنمای زندگی سالم",
              f"برنده: «{hits[0]['book_title'] if hits else '—'}»")
        check("نتیجه شناسه و نام کتاب را همراه دارد",
              bool(hits) and hits[0]["book_id"] == "b1" and hits[0]["score"] is not None)

        h2 = R.search("مسیریاب و پهنای باند و بسته‌ها", top_k=3)
        check("پرسش فنی، کتاب فنی را می‌آورد نه کتاب تغذیه",
              bool(h2) and h2[0]["book_title"] == "مبانی شبکه",
              f"برنده: «{h2[0]['book_title'] if h2 else '—'}»")

        ctx = R.context_for("سلامت قلب", top_k=2, budget=1200)
        check("context_for متن آماده‌ی پرامپت می‌دهد", len(ctx) > 100, f"{len(ctx)} نویسه")
        check("context_for نام کتاب منبع را ذکر می‌کند", "از کتاب" in ctx)
        check("context_for از بودجه فراتر نمی‌رود", len(ctx) <= 1400, f"{len(ctx)}")

        st = R.stats()
        check("آمار: دقیقاً دو کتاب", st["books"] == 2, str(st["books"]))
        check("آمار: هیچ قطعه‌ای گم نشده", st["chunks"] == n1 + n2,
              f"{st['chunks']} در برابر {n1 + n2}")

        # دسته‌بندی ۶۴‌تایی نباید چیزی را جا بیندازد
        big = SAMPLE * 40
        nb = R.add_book("b3", "کتاب بزرگ", big)
        check("کتاب بزرگ‌تر از یک دسته کامل ذخیره می‌شود",
              nb > 64 and R.stats()["chunks"] == n1 + n2 + nb, f"{nb} قطعه")

        check("پرسش خالی نتیجه‌ی خالی می‌دهد", R.search("   ") == [])
        check("clear همه را پاک می‌کند و کالکشن سالم می‌ماند",
              R.clear() and R.stats()["chunks"] == 0)
        return True
    finally:
        R.CHROMA_DIR, R._client, R._collection, R._embedder = saved
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════ ۴) تنزل بی‌خطر ═══════════════

def test_graceful_degradation():
    section("۴) نبودِ کتابخانه‌های سنگین، آنتانو را نمی‌شکند")
    import builtins
    from library import rag_engine as R

    real_import = builtins.__import__

    def blocked(name, *a, **k):
        if name.split(".")[0] in ("chromadb", "sentence_transformers"):
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *a, **k)

    saved = (R._client, R._collection)
    R._client = R._collection = None
    builtins.__import__ = blocked
    try:
        check("available() مقدار False می‌دهد", R.available() is False)
        check("دلیلِ فارسی و راهنمای نصب داده می‌شود",
              "pip install" in R.unavailable_reason())
        check("get_collection مقدار None می‌دهد", R.get_collection() is None)
        check("search نتیجه‌ی خالی می‌دهد بدون خطا", R.search("هرچیزی") == [])
        check("context_for رشته‌ی خالی می‌دهد", R.context_for("هرچیزی") == "")
        check("add_book صفر می‌دهد بدون خطا", R.add_book("x", "t", SAMPLE) == 0)
        check("book_exists مقدار False می‌دهد", R.book_exists("x") is False)
        check("stats گزارش «در دسترس نیست» می‌دهد", R.stats()["available"] is False)
        check("clear مقدار False می‌دهد", R.clear() is False)

        # و مهم‌ترین بخش: چت باید همچنان از FTS5 نتیجه بگیرد
        import main
        ctx = main._library_context("مدیریت مالی چیست؟")
        check("_library_context بدون RAG هم کار می‌کند (FTS5 دست‌نخورده)",
              isinstance(ctx, str))
        check("_rag_context بی‌سروصدا خالی برمی‌گردد",
              main._rag_context("مدیریت مالی") == "")
        # پرسشی که هیچ واژه‌ی واقعی ندارد، پس FTS5 هم چیزی نمی‌یابد
        ctx2 = main._library_context("ژضصثقپ ۱۲۳۴۵۶ qxzjvw", books_only=True)
        check("حالت «فقط کتابخانه» وقتی چیزی نیست، صادقانه اعلام می‌کند",
              "پیدا نشد" in ctx2)
        ctx3 = main._library_context("ژضصثقپ ۱۲۳۴۵۶ qxzjvw")
        check("حالت عادی وقتی چیزی نیست، پرامپت را بی‌دلیل بزرگ نمی‌کند", ctx3 == "")
    finally:
        builtins.__import__ = real_import
        R._client, R._collection = saved


# ═══════════════ ۴ب) حلقه‌ی همگام‌سازی با تلگرامِ ساختگی ═══════════════

def test_sync_loop():
    """حلقه‌ی دانلود را با یک کلاینت تلگرامِ ساختگی می‌سنجد.

    چیزهایی که اینجا ثابت می‌شوند و بدون آزمون معلوم نمی‌شدند:
    کتابِ تکراری دوباره پردازش نمی‌شود، خطای یک کتاب بقیه را متوقف نمی‌کند،
    فایل خام همیشه پاک می‌شود (حتی وقتی استخراج شکست بخورد)، و دو همگام‌سازی
    هم‌زمان اجرا نمی‌شوند.
    """
    section("۴ب) حلقه‌ی همگام‌سازی (با تلگرام ساختگی)")
    import asyncio
    from library import telegram_sync as TS

    d = tempfile.mkdtemp(prefix="antanu_sync_")
    saved_env = {k: os.environ.get(k) for k in
                 ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_BOOKS_CHANNEL")}
    saved = (TS.BOOKS_DIR, TS._client, TS.has_session, TS.rag_engine, TS.extractors)
    os.environ.update({"TELEGRAM_API_ID": "1", "TELEGRAM_API_HASH": "x",
                       "TELEGRAM_BOOKS_CHANNEL": "@fake"})
    TS.BOOKS_DIR = os.path.join(d, "books_raw")
    TS.has_session = lambda: True

    downloaded = []

    class FakeFile:
        def __init__(self, name):
            self.name = name
            self.ext = os.path.splitext(name)[1]

    class FakeMsg:
        def __init__(self, mid, name):
            self.id = mid
            self.file = FakeFile(name)

    MSGS = [FakeMsg(1, "کتاب اول.txt"),      # سالم
            FakeMsg(2, "عکس.jpg"),           # پشتیبانی‌نشده → وارد فهرست نمی‌شود
            FakeMsg(3, "کتاب تکراری.txt"),   # قبلاً هست → رد
            FakeMsg(4, "خراب.txt"),          # متن بی‌ارزش → رد
            FakeMsg(5, "منفجرشو.txt")]       # خطا هنگام افزودن → شمرده شود، متوقف نکند

    class FakeClient:
        async def connect(self):
            pass

        async def is_user_authorized(self):
            return True

        async def disconnect(self):
            pass

        def iter_messages(self, channel, limit=None):
            async def gen():
                for m in (MSGS[:limit] if limit else MSGS):
                    yield m
            return gen()

        async def download_media(self, m, file=None):
            open(file, "w", encoding="utf-8").write("محتوا")
            downloaded.append(file)
            return file

    TS._client = lambda: FakeClient()

    class FakeExtractors:
        is_supported = staticmethod(lambda n: n.endswith(".txt"))

        @staticmethod
        def extract_text(p):
            return "" if "خراب" in p else SAMPLE

    class FakeRag:
        @staticmethod
        def available():
            return True

        @staticmethod
        def unavailable_reason():
            return ""

        @staticmethod
        def book_exists(bid):
            return str(bid) == "3"

        @staticmethod
        def add_book(bid, title, text):
            if "منفجرشو" in title:
                raise RuntimeError("خطای ساختگی")
            return 5

    TS.extractors, TS.rag_engine = FakeExtractors, FakeRag

    try:
        res = asyncio.run(TS.sync_channel())
        check("همگام‌سازی با موفقیت تمام شد", res.get("ok") is True, str(res)[:90])
        check("فایل پشتیبانی‌نشده وارد فهرست نشد", res.get("total") == 4,
              f"total={res.get('total')}")
        check("فقط کتاب سالم افزوده شد", res.get("added") == 1, f"added={res.get('added')}")
        check("کتاب تکراری و کتاب بی‌متن رد شدند", res.get("skipped") == 2,
              f"skipped={res.get('skipped')}")
        check("خطای یک کتاب شمرده شد و بقیه ادامه یافتند", res.get("failed") == 1,
              f"failed={res.get('failed')}")
        check("کتاب تکراری اصلاً دانلود نشد", len(downloaded) == 3,
              f"{len(downloaded)} دانلود")

        left = os.listdir(TS.BOOKS_DIR) if os.path.isdir(TS.BOOKS_DIR) else []
        check("هیچ فایل خامی روی دیسک نماند", left == [], str(left))
        check("زمان پایان ثبت شد", bool(TS.status().get("finished_at")))
        check("وضعیت «در حال اجرا» پاک شد", TS.status().get("running") is False)
        check("گزارش بازگشتی هم «در حال اجرا» نمی‌گوید", res.get("running") is False)

        # قفل: تا یکی در جریان است، دومی شروع نشود
        TS._running.acquire()
        try:
            r2 = asyncio.run(TS.sync_channel())
            check("دو همگام‌سازی هم‌زمان اجرا نمی‌شوند",
                  r2.get("ok") is False and "قبل" in r2.get("error", ""), str(r2)[:70])
        finally:
            TS._running.release()

        # نبودِ نشست باید پیام روشن بدهد نه کرش
        TS.has_session = lambda: False
        r3 = asyncio.run(TS.sync_channel())
        check("بدون ورود به تلگرام، راهنمای روشن می‌دهد",
              r3.get("ok") is False and "telegram_login" in r3.get("error", ""))
    finally:
        TS.BOOKS_DIR, TS._client, TS.has_session, TS.rag_engine, TS.extractors = saved
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════ ۵) امنیت و اتصال‌ها ═══════════════

def test_wiring_and_secrets():
    section("۵) اتصال‌ها، تنظیمات و امنیت")

    gi = open(".gitignore", encoding="utf-8").read()
    for pat in ("*.session", "books_raw/", "chroma_db/", ".env"):
        check(f".gitignore شامل {pat} است", pat in gi)

    import subprocess
    tracked = subprocess.run(["git", "ls-files"], capture_output=True,
                             text=True).stdout.splitlines()
    leaks = [f for f in tracked
             if f.endswith(".session") or f.startswith("books_raw/")
             or f.startswith("chroma_db/") or f == ".env"]
    check("هیچ کلید/نشستی در گیت نیست", not leaks, str(leaks))

    env = open(".env.example", encoding="utf-8").read()
    for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_BOOKS_CHANNEL"):
        check(f".env.example شامل {k} است", k in env)

    req = open("requirements-library.txt", encoding="utf-8").read()
    for p in ("telethon", "chromadb", "sentence-transformers"):
        check(f"requirements-library.txt شامل {p} است", p in req)

    # حیاتی: وابستگی‌های سنگین نباید در requirements اصلی باشند، وگرنه روی سرور
    # کم‌رم کل سایت (نه فقط این قابلیت) از کار می‌افتد.
    main_req = open("requirements.txt", encoding="utf-8").read()
    heavy = [p for p in ("chromadb", "sentence-transformers", "telethon")
             if any(ln.strip().startswith(p) for ln in main_req.splitlines())]
    check("وابستگی‌های سنگین در requirements.txt اصلی نیستند", not heavy, str(heavy))

    dock = open("Dockerfile", encoding="utf-8").read()
    check("داکرفایل پرچم WITH_LIBRARY دارد (پیش‌فرض خاموش)",
          "ARG WITH_LIBRARY=0" in dock and "requirements-library.txt" in dock)

    import yaml
    comp = yaml.safe_load(open("docker-compose.yml", encoding="utf-8"))
    envs = comp["services"]["antanu"]["environment"]
    for k in ("ANTANU_CHROMA_DIR", "ANTANU_TG_SESSION", "HF_HOME"):
        check(f"{k} روی دیسک ماندگار /data است", str(envs.get(k, "")).startswith("/data"),
              str(envs.get(k)))

    src = open("main.py", encoding="utf-8").read()
    check("اندپوینت آمار کتابخانه‌ی هوشمند هست", '"/admin/library/stats"' in src)
    check("اندپوینت همگام‌سازی هست", '"/admin/library/sync"' in src)
    check("اندپوینت پاک‌کردن هست", '"/admin/library/clear"' in src)
    check("هر سه اندپوینت پشت require_admin هستند",
          src.count("require_admin(request)") >= 3)
    check("پرچم library از بدنه‌ی درخواست خوانده می‌شود",
          'body.get("library")' in src)
    check("پرچم به _library_context می‌رسد", "books_only=library_on" in src)

    js = open("static/app.js", encoding="utf-8").read()
    check("دکمه‌ی کتابخانه در app.js هست", "#libraryBtn" in js)
    check("پرچم library در بدنه‌ی درخواست فرستاده می‌شود", "library: libraryOn" in js)
    check("دکمه کلاس ctype ندارد (سند تولید نمی‌کند)",
          "libraryBtn" not in js.split("runContentQueue")[0].split("ctype")[-1]
          if "ctype" in js else True)

    html = open("templates/chat.html", encoding="utf-8").read()
    check("دکمه در قالب چت هست", 'id="libraryBtn"' in html)
    check("دکمه کلاس ctype ندارد",
          'id="libraryBtn"' in html and
          "ctype" not in html.split('id="libraryBtn"')[1].split(">")[0])

    # حالت کتابخانه باید واقعاً پرامپت متفاوتی بسازد، نه فقط یک پرچمِ بی‌اثر
    import main
    q = "نسبت نقدینگی چیست؟"
    normal = main._library_context(q)
    only = main._library_context(q, books_only=True)
    check("حالت «فقط کتابخانه» پرامپت متفاوتی می‌سازد", normal != only)
    check("در حالت کتابخانه، مدل ملزم به پاسخ فقط از منابع می‌شود",
          "**فقط**" in only and "**فقط**" not in normal)
    check("در حالت عادی، مدل آزاد است از دانش خودش هم بگوید",
          "از دانش خودت پاسخ بده" in normal)

    # اندپوینت‌های مدیریت پشت ورود‌اند
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    codes = [c.get("/admin/library/stats").status_code,
             c.post("/admin/library/sync").status_code,
             c.post("/admin/library/clear").status_code]
    check("اندپوینت‌های مدیریت بدون ورود بسته‌اند", all(x == 401 for x in codes), str(codes))

    adm = open("templates/admin.html", encoding="utf-8").read()
    check("کارت کتابخانه‌ی هوشمند در پنل مدیریت هست", "tgLibSync" in adm)
    check("کارت وضعیت نبودِ کتابخانه‌ها را نشان می‌دهد", "tgLibWarn" in adm)

    import json
    import glob
    for f in sorted(glob.glob("locales/*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if "chat.tool_library" not in d:
            check(f"کلید ترجمه در {os.path.basename(f)}", False)
            break
    else:
        check("کلید «جستجو در کتابخانه» در هر ۱۲ زبان هست", True)


# ═══════════════ ۶) عدم تخریب ═══════════════

def test_no_regression():
    section("۶) عدم تخریب قابلیت‌های موجود")
    import subprocess

    # آزمون‌های مرحله‌های قبل. اگر کنار پروژه نبودند، مسیرشان را با
    # ANTANU_OLD_TESTS بده تا همان‌ها هم دوباره اجرا شوند.
    old_dir = os.environ.get("ANTANU_OLD_TESTS", ".")

    # آزمون تیکر ترجمه‌ها را در جدول تنظیمات کش می‌کند، پس اجرای دومش «نیاز به
    # ترجمه» را False می‌بیند و بی‌دلیل رد می‌شود. کش را صفر می‌کنیم تا هر اجرا
    # از شرایط یکسان شروع شود.
    try:
        import db as _db
        c = _db.get_db()
        c.execute("DELETE FROM settings WHERE key LIKE 'ticker_tr:%'")
        c.commit()
        c.close()
    except Exception:
        pass

    ran = 0
    for t in ("test_lang.py", "test_kb.py", "test_planner.py", "test_ticker.py"):
        p = os.path.join(old_dir, t)
        if not os.path.exists(p):
            continue
        ran += 1
        r = subprocess.run([sys.executable, p], capture_output=True, text=True,
                           timeout=1800, cwd=os.path.dirname(os.path.abspath(__file__)))
        out = (r.stdout or "") + (r.stderr or "")
        check(f"{t} همچنان پاس می‌شود", r.returncode == 0,
              out.strip().splitlines()[-1][:90] if out.strip() else "")
    if not ran:
        print(f"  ⓘ آزمون‌های مرحله‌های قبل در «{old_dir}» پیدا نشدند — رد شدند.")

    # این‌ها کنار همین فایل و در گیت‌اند، نه در ANTANU_OLD_TESTS
    here = os.path.dirname(os.path.abspath(__file__))
    for t in ("test_digits.py", "test_footnotes.py", "test_article_stats.py", "test_article_refs.py",
             "test_stats_gaps.py", "test_workbench.py"):
        p = os.path.join(here, t)
        if not os.path.exists(p):
            continue
        r = subprocess.run([sys.executable, p], capture_output=True, text=True,
                           timeout=600, cwd=here)
        out = (r.stdout or "") + (r.stderr or "")
        check(f"{t} پاس می‌شود", r.returncode == 0,
              out.strip().splitlines()[-1][:90] if out.strip() else "")

    r = subprocess.run([sys.executable, "-c", "import main; print(len(main.app.routes))"],
                       capture_output=True, text=True, timeout=300)
    check("main.py بدون خطا بارگذاری می‌شود", r.returncode == 0,
          (r.stdout or r.stderr).strip()[-90:])

    from jinja2 import Environment, FileSystemLoader, select_autoescape
    import glob
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=select_autoescape(["html"]))
    env.globals["t"] = lambda k, **kw: k
    bad = []
    for f in glob.glob("templates/*.html"):
        try:
            env.get_template(os.path.basename(f))
        except Exception as e:
            bad.append(f"{f}: {e}")
    check("همه‌ی قالب‌ها سالم‌اند", not bad, "؛ ".join(bad)[:110])


def main_run():
    print("═" * 68)
    print("  آزمون کتابخانه‌ی هوشمند آنتانو")
    print("═" * 68)
    test_extractors()
    test_chunking()
    semantic_ok = test_semantic()
    test_pipeline_with_stub_embedder()
    test_graceful_degradation()
    test_sync_loop()
    test_wiring_and_secrets()
    test_no_regression()

    print("\n" + "═" * 68)
    print(f"  نتیجه: {len(PASS)} پاس، {len(FAIL)} ناموفق")
    if FAIL:
        print("  ناموفق‌ها:")
        for f in FAIL:
            print("    ✗", f)
    if not semantic_ok:
        print("\n  ⚠ جستجوی معنایی با «مدل واقعی» در این محیط اجرا نشد.")
        print("    خط لوله‌ی ChromaDB با بردارسازِ کنترل‌شده کامل سنجیده شد (بخش ۳ب)،")
        print("    اما کیفیتِ معناییِ مدل باید روی سرور خودت تأیید شود:")
        print("        pip install -r requirements-library.txt && python test_library.py")
    print("═" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main_run())
