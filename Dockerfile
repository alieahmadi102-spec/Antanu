FROM python:3.11-slim

WORKDIR /app

# LibreOffice (برای ساخت PDF با ظاهر دقیقاً مثل Word) + فونت‌ها + ffmpeg (دوبله‌ی ویدیو)
# libreoffice-writer سبک‌تر از کل libreoffice است و برای تبدیل docx→pdf کافی است.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-noto-core \
        fontconfig \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# نصب فونت وزیرمتن در سیستم تا LibreOffice همان فونت Word را برای PDF استفاده کند
RUN mkdir -p /usr/share/fonts/truetype/vazirmatn \
    && cp static/fonts/Vazirmatn-Regular.ttf /usr/share/fonts/truetype/vazirmatn/ 2>/dev/null || true \
    && fc-cache -f

# دیتابیس و خروجی‌ها در مسیر قابل‌نوشتن (روی Fly.io با Volume به /data نگاشت می‌شود)
ENV ANTANU_DB=/tmp/antanu.db
ENV ANTANU_EXPORT_DIR=/tmp/antanu_exports

# پورت از متغیر PORT خوانده می‌شود (Fly=8080، Render/HF خودشان تعیین می‌کنند)
ENV PORT=8080
EXPOSE 8080

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
