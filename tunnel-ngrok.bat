@echo off
chcp 65001 >nul
title ANTANU Tunnel (ngrok)

REM دامنه ثابت خودتان را جایگزین کنید (از dashboard.ngrok.com/domains)
set DOMAIN=antanu.ngrok-free.app

echo لینک ثابت شما: https://%DOMAIN%
ngrok http --domain=%DOMAIN% 8000
pause
