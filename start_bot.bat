@echo off
chcp 65001 >nul
cls
echo ========================================
echo   Telegram-бот учёта рабочего времени
echo ========================================
echo.
echo Запуск бота...
echo.

cd /d %~dp0

python lawyer_timetracker_bot.py

echo.
echo ========================================
echo Бот остановлен
echo ========================================
echo.
pause
