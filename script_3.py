
# Создаём batch-файл для Windows
batch_script = """@echo off
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
"""

with open('start_bot.bat', 'w', encoding='utf-8') as f:
    f.write(batch_script)

print("✅ Файл start_bot.bat создан успешно!")

# Создаём shell-скрипт для Linux/Mac
shell_script = """#!/bin/bash

echo "========================================"
echo "  Telegram-бот учёта рабочего времени"
echo "========================================"
echo ""
echo "Запуск бота..."
echo ""

cd "$(dirname "$0")"

python3 lawyer_timetracker_bot.py

echo ""
echo "========================================"
echo "Бот остановлен"
echo "========================================"
"""

with open('start_bot.sh', 'w', encoding='utf-8') as f:
    f.write(shell_script)

print("✅ Файл start_bot.sh создан успешно!")

# Создаём файл с примерами команд для быстрого старта
quick_start = """# БЫСТРЫЙ СТАРТ - Команды для копирования

## Установка (Windows)
pip install -r requirements.txt

## Установка (Linux/macOS)
pip3 install -r requirements.txt

## Запуск (Windows)
python lawyer_timetracker_bot.py

## Запуск (Linux/macOS)
python3 lawyer_timetracker_bot.py

## Запуск в фоновом режиме на сервере (Linux)
screen -S lawyer_bot
python3 lawyer_timetracker_bot.py
# Нажмите Ctrl+A, затем D для отключения

## Вернуться к боту
screen -r lawyer_bot

## Остановка бота
Ctrl + C

## Создание резервной копии БД (Windows)
copy lawyer_timetracker.db backup_%date:~-4,4%%date:~-7,2%%date:~-10,2%.db

## Создание резервной копии БД (Linux/macOS)
cp lawyer_timetracker.db backup_$(date +%Y%m%d).db

## Проверка версии Python
python --version

## Проверка установленных пакетов
pip list

## Обновление библиотек
pip install --upgrade python-telegram-bot pandas openpyxl
"""

with open('QUICK_START.txt', 'w', encoding='utf-8') as f:
    f.write(quick_start)

print("✅ Файл QUICK_START.txt создан успешно!")

print("\n" + "="*70)
print("✅ ВСЕ ФАЙЛЫ УСПЕШНО СОЗДАНЫ!")
print("="*70)
print("\nСписок созданных файлов:")
print("1. lawyer_timetracker_bot.py - Основной код бота (Python)")
print("2. requirements.txt - Список зависимостей")
print("3. installation-guide.md - Подробная инструкция по установке")
print("4. user-guide.md - Полное руководство пользователя")
print("5. README.md - Краткая справка")
print("6. start_bot.bat - Скрипт запуска для Windows")
print("7. start_bot.sh - Скрипт запуска для Linux/macOS")
print("8. QUICK_START.txt - Шпаргалка с командами")
print("\n" + "="*70)
print("📋 ЧТО ДЕЛАТЬ ДАЛЬШЕ:")
print("="*70)
print("1. Создайте бота в @BotFather и получите токен")
print("2. Откройте lawyer_timetracker_bot.py")
print("3. В строке 33 замените YOUR_BOT_TOKEN_HERE на ваш токен")
print("4. Выполните: pip install -r requirements.txt")
print("5. Запустите: python lawyer_timetracker_bot.py")
print("6. Найдите бота в Telegram и отправьте /start")
print("\n🎉 Готово! Бот будет работать!")
