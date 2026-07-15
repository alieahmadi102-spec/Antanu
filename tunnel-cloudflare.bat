@echo off
chcp 65001 >nul
title ANTANU Tunnel (Cloudflare)

REM قبل از اولین اجرا، سه دستور داخل فایل «لینک-ثابت.md» را انجام دهید

cloudflared tunnel run --url http://localhost:8000 antanu
pause
