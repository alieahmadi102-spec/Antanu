# 🚀 راهنمای راه‌اندازی آنتانو روی سرور رایگان (Oracle Always Free)

این راهنما از **صفر تا صد** است: از ساخت سرور رایگان تا بالا آمدن سایت، بکاپ خودکار، و انتقال بعدی به سرور اصلی.

> چرا Oracle؟ چون **همیشه‌رایگان** است (نه تریال)، دیسک ماندگار دارد، و چند ماه/سال دوام می‌آورد. کد روی گیت‌هاب می‌ماند و همه‌ی داده‌ها در یک فایل `antanu.db` است، پس انتقال بعدی فقط کپی یک فایل است.

---

## 🟦 مرحله ۱ — ساخت حساب Oracle Cloud
1. برو به **https://www.oracle.com/cloud/free/** و «Start for free» را بزن.
2. ایمیل، کشور و مشخصات را وارد کن. یک **کارت بانکی** برای تأیید هویت می‌خواهد (پول کم نمی‌شود؛ فقط تأیید).
3. حساب که ساخته شد، وارد **Oracle Cloud Console** شو.

## 🟦 مرحله ۲ — ساخت سرور مجازی رایگان (VM)
1. از منوی بالا-چپ: **Menu → Compute → Instances**.
2. **Create Instance** را بزن.
3. تنظیمات:
   - **Name**: `antanu`
   - **Image**: روی «Edit» بزن و **Ubuntu 22.04** را انتخاب کن.
   - **Shape**: روی «Edit» → **Ampere (ARM)** → `VM.Standard.A1.Flex` (رایگان: تا ۴ هسته و ۲۴ گیگ رم). اگر موجود نبود، `VM.Standard.E2.1.Micro` (AMD رایگان) را بگیر.
4. بخش **Add SSH keys**: گزینه‌ی **Generate a key pair for me** را بزن و **هر دو فایل کلید (private/public) را دانلود کن** — این‌ها برای ورود لازم‌اند. (اگر با ویندوز و PuTTY کار می‌کنی، بعداً از همین private key استفاده می‌کنی.)
5. **Create** را بزن. چند دقیقه بعد وضعیت سبز (Running) می‌شود.
6. **IP سرور** را یادداشت کن: در صفحه‌ی Instance، مقدار **Public IP address** (مثلاً `140.238.x.x`).

## 🟦 مرحله ۳ — باز کردن پورت ۸۰ (تا سایت از اینترنت باز شود)
1. در صفحه‌ی Instance، روی نام **Virtual Cloud Network (VCN)** یا زیرشبکه (Subnet) کلیک کن.
2. وارد **Security Lists** → **Default Security List** شو.
3. **Add Ingress Rules**:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: **TCP**
   - Destination Port Range: `80` (و اگر HTTPS خواستی، یک قانون دیگر برای `443`)
   - **Add**.

## 🟦 مرحله ۴ — ورود به سرور (SSH)
روی کامپیوتر خودت (PowerShell یا ترمینال)، با کلید private که دانلود کردی:
```bash
ssh -i مسیر\کلید-private ubuntu@IP-سرور
```
مثال:
```bash
ssh -i C:\Users\me\Downloads\ssh-key.key ubuntu@140.238.10.20
```
> اگر خطای «permissions too open» داد (لینوکس/مک):  `chmod 600 مسیر-کلید`  و دوباره امتحان کن.

## 🟦 مرحله ۵ — نصب Docker
داخل سرور این دستورها را یکی‌یکی بزن:
```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```
حالا **یک‌بار از سرور خارج شو و دوباره وارد شو** (تا دسترسی docker فعال شود):
```bash
exit
ssh -i مسیر-کلید ubuntu@IP-سرور
docker --version   # باید نسخه را نشان دهد
```

> اگر Oracle فایروال داخلی داشت و پورت باز نشد، این را هم بزن:
> ```bash
> sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
> sudo netfilter-persistent save
> ```

## 🟦 مرحله ۶ — گرفتن کد آنتانو
```bash
sudo apt install -y git
git clone https://github.com/alieahmadi102-spec/Antanu.git
cd Antanu
```
> اگر ریپو خصوصی است، از یک **Personal Access Token** گیت‌هاب استفاده کن یا کد را با `scp` بالا بفرست.

## 🟦 مرحله ۷ — تنظیم رمز ادمین (فایل .env)
```bash
cp .env.example .env
nano .env
```
حداقل این‌ها را پر کن (رمز قوی بگذار)، بعد `Ctrl+O` سپس `Enter` سپس `Ctrl+X`:
```
ANTANU_ADMIN_USER=admin
ANTANU_ADMIN_PASS=RmzeKheyliGhavi_1234
ANTANU_ADMIN_CONTACT=آیدی تلگرام ادمین: @Anuyouka
```
> کلیدهای API هوش مصنوعی را لازم نیست اینجا بگذاری — بعد از بالا آمدن سایت، از **پنل مدیریت** خود آنتانو وارد می‌کنی (در دیتابیس ماندگار ذخیره می‌شود).

## 🟦 مرحله ۸ — اجرا! 🎉
```bash
docker compose up -d --build
```
اولین بار چند دقیقه طول می‌کشد (چون LibreOffice نصب می‌شود). بعد:
```bash
docker compose logs -f    # دیدن لاگ؛ با Ctrl+C خارج شو (سرور همچنان روشن می‌ماند)
```

## 🟦 مرحله ۹ — باز کردن سایت
در مرورگر برو به:
```
http://IP-سرور
```
با `admin` و رمزی که گذاشتی وارد شو → **پنل مدیریت → تنظیمات API** → کلیدهای هوش مصنوعی را وارد و ذخیره کن. تمام! ✅

---

## 🌐 (اختیاری) دامنه و HTTPS
اگر یک دامنه داری (مثل `antanu.ir`):
1. در تنظیمات DNS دامنه، یک رکورد **A** بساز که به **IP سرور** اشاره کند.
2. ساده‌ترین راه برای HTTPS خودکار، افزودن **Caddy** است. یک فایل `docker-compose.override.yml` بساز:
   ```yaml
   services:
     antanu:
       ports: []            # پورت 80 را از app بگیر
       expose: ["8080"]
     caddy:
       image: caddy:2
       restart: unless-stopped
       ports: ["80:80", "443:443"]
       command: caddy reverse-proxy --from https://دامنه-تو --to antanu:8080
       volumes: ["caddy_data:/data"]
   volumes:
     caddy_data:
   ```
3. `docker compose up -d` — Caddy خودش گواهی HTTPS رایگان می‌گیرد. حالا `https://دامنه-تو` باز می‌شود.

---

## 💾 بکاپ (خیلی مهم برای دوام چند ماهه)
- آنتانو **هر شب خودکار** از دیتابیس نسخه‌ی پشتیبان می‌گیرد و در `/data/backups` نگه می‌دارد (۷ نسخه‌ی آخر).
- برای اطمینان بیشتر، هر چند وقت یک نسخه را **روی کامپیوتر خودت** هم کپی کن:
  ```bash
  # روی کامپیوتر خودت اجرا کن:
  scp -i کلید ubuntu@IP:/var/lib/docker/volumes/antanu_antanu_data/_data/antanu.db  ./antanu-backup.db
  ```
  یا ساده‌تر: در **پنل مدیریت** دکمه‌ی **«💾 پشتیبان‌گیری»** را بزن تا فایل دانلود شود.
- تنظیمات بکاپ با متغیرهای محیطی قابل تغییر است: `ANTANU_BACKUP_KEEP` (تعداد نسخه)، `ANTANU_BACKUP_INTERVAL_HOURS`، یا `ANTANU_AUTO_BACKUP=0` برای خاموش‌کردن.

---

## 🔄 به‌روزرسانی آنتانو (بعد از تغییر کد)
```bash
cd Antanu
git pull
docker compose up -d --build
```
داده‌ها (دیتابیس) دست‌نخورده می‌مانند چون روی دیسک ماندگار `/data` هستند.

---

## 📦 انتقال به سرور اصلی (در آینده)
چون همه‌چیز در یک فایل `antanu.db` است:
1. روی سرور اصلی جدید، Docker را نصب و کد را clone کن (مرحله‌های ۵ و ۶).
2. فایل `antanu.db` را از سرور قدیمی بگیر و به سرور جدید منتقل کن:
   ```bash
   # نسخه‌ی پشتیبان از سرور قدیمی
   docker compose exec antanu sh -c "cp /data/antanu.db /data/exports/move.db"
   # سپس آن را دانلود و روی سرور جدید در مسیر volume بگذار
   ```
3. `.env` را بساز و `docker compose up -d --build` بزن.
4. دامنه را به IP سرور جدید اشاره بده. کاربران هیچ تفاوتی حس نمی‌کنند. ✅

---

## 🆘 عیب‌یابی سریع
| مشکل | راه‌حل |
|---|---|
| سایت باز نمی‌شود | پورت 80 در Security List و iptables باز است؟ (مرحله ۳ و ۵) |
| `docker: permission denied` | یک‌بار `exit` و دوباره SSH بزن (مرحله ۵) |
| ساخت PDF خطا/رم کم | رم سرور را بیشتر کن یا Shape بزرگ‌تر انتخاب کن |
| رمز ادمین را فراموش کردم | `.env` را ویرایش و `docker compose up -d` بزن (فقط رمزِ کاربرِ جدید؛ کاربر موجود با پنل تغییر کند) |
| لاگ‌ها | `docker compose logs -f` |
