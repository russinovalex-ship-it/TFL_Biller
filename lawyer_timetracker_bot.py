#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот для учёта рабочего времени юристов
Версия: 1.1 (с проверкой подписки на канал)
Требования: python-telegram-bot 20.x, pandas, openpyxl
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from telegram.error import TelegramError

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ТОКЕН БОТА - ЗАМЕНИТЕ на свой токен от @BotFather
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# ПРОВЕРКА ПОДПИСКИ НА КАНАЛ
CHANNEL_USERNAME = "@moskvichca"  # Замените на username вашего канала (например: @technology_for_lawyers)

# База данных
DB_NAME = "lawyer_timetracker.db"

# Состояния для ConversationHandler
(
    WAITING_CLIENT_NAME,
    WAITING_PROJECT_CLIENT,
    WAITING_PROJECT_NAME,
    WAITING_PROJECT_RATE,
    WAITING_CUSTOM_TASK
) = range(5)

# Типы задач с эмодзи
TASK_TYPES = [
    "📝 Подготовка иска",
    "📄 Подготовка договора",
    "💬 Консультация",
    "📚 Изучение материалов",
    "⚖️ Судебное заседание",
    "📞 Переговоры",
    "🔍 Анализ документов",
    "✉️ Переписка с клиентом",
    "🔎 Исследование практики",
    "📋 Подготовка заявления",
    "✍️ Другое"
]


# ==================== ПРОВЕРКА ПОДПИСКИ ====================

async def is_subscribed(user_id: int, bot) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.
    Возвращает True если подписан, False если нет.
    """
    try:
        chat_member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        # Проверяем статусы: member, administrator, creator
        is_sub = chat_member.status in ["member", "administrator", "creator"]
        return is_sub
    except TelegramError as e:
        logger.error(f"Ошибка при проверке подписки: {e}")
        # Если ошибка (например, канал не найден) - разрешаем доступ
        return True


# ==================== РАБОТА С БАЗОЙ ДАННЫХ ====================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            hourly_rate REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
            UNIQUE(user_id, client_id, name)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            task_type TEXT NOT NULL,
            description TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration REAL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")


def add_client(user_id: int, name: str) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO clients (user_id, name, created_at) VALUES (?, ?, ?)',
            (user_id, name, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def get_user_clients(user_id: int) -> List[Tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, created_at FROM clients WHERE user_id = ? ORDER BY name',
        (user_id,)
    )
    clients = cursor.fetchall()
    conn.close()
    return clients


def add_project(user_id: int, client_id: int, name: str, hourly_rate: float) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO projects (user_id, client_id, name, hourly_rate, created_at) VALUES (?, ?, ?, ?, ?)',
            (user_id, client_id, name, hourly_rate, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def get_user_projects(user_id: int) -> List[Tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.name, p.hourly_rate, c.name 
        FROM projects p
        JOIN clients c ON p.client_id = c.id
        WHERE p.user_id = ?
        ORDER BY c.name, p.name
    ''', (user_id,))
    projects = cursor.fetchall()
    conn.close()
    return projects


def get_projects_by_client(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.name, p.name, p.hourly_rate
        FROM projects p
        JOIN clients c ON p.client_id = c.id
        WHERE p.user_id = ?
        ORDER BY c.name, p.name
    ''', (user_id,))
    results = cursor.fetchall()
    conn.close()

    projects_dict = {}
    for client_name, project_name, rate in results:
        if client_name not in projects_dict:
            projects_dict[client_name] = []
        projects_dict[client_name].append((project_name, rate))

    return projects_dict


def start_work(user_id: int, project_id: int, task_type: str, description: str = None) -> bool:
    if get_active_work(user_id):
        return False

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO time_entries (user_id, project_id, task_type, description, start_time) VALUES (?, ?, ?, ?, ?)',
        (user_id, project_id, task_type, description, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True


def get_active_work(user_id: int) -> Optional[Tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT te.id, p.name, te.task_type, te.description, te.start_time, c.name
        FROM time_entries te
        JOIN projects p ON te.project_id = p.id
        JOIN clients c ON p.client_id = c.id
        WHERE te.user_id = ? AND te.end_time IS NULL
    ''', (user_id,))
    work = cursor.fetchone()
    conn.close()
    return work


def stop_work(user_id: int) -> Optional[Tuple]:
    active_work = get_active_work(user_id)
    if not active_work:
        return None

    entry_id, project_name, task_type, description, start_time, client_name = active_work
    end_time = datetime.now()
    start_dt = datetime.fromisoformat(start_time)
    duration = (end_time - start_dt).total_seconds() / 3600

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE time_entries SET end_time = ?, duration = ? WHERE id = ?',
        (end_time.isoformat(), duration, entry_id)
    )
    conn.commit()
    conn.close()

    return (project_name, task_type, description, duration, client_name)


def get_time_entries(user_id: int, days: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_NAME)

    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    query = '''
        SELECT 
            te.start_time,
            c.name as client,
            p.name as project,
            te.task_type,
            te.description,
            te.duration,
            p.hourly_rate
        FROM time_entries te
        JOIN projects p ON te.project_id = p.id
        JOIN clients c ON p.client_id = c.id
        WHERE te.user_id = ? AND te.end_time IS NOT NULL AND te.start_time >= ?
        ORDER BY te.start_time DESC
    '''

    df = pd.read_sql_query(query, conn, params=(user_id, cutoff_date))
    conn.close()

    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'])
        df['cost'] = df['duration'] * df['hourly_rate']

    return df


def format_report(df: pd.DataFrame, title: str) -> str:
    if df.empty:
        return f"*{title}*\n\nНет записей за выбранный период."

    report = f"*{title}*\n\n"

    for (client, project), group in df.groupby(['client', 'project']):
        total_hours = group['duration'].sum()
        total_cost = group['cost'].sum()

        report += f"📁 *{client} → {project}*\n"

        for _, row in group.iterrows():
            task = row['task_type']
            if row['description']:
                task += f" ({row['description']})"
            report += f"  • {task}: {row['duration']:.2f} ч\n"

        report += f"  ⏱ *Итого:* {total_hours:.2f} ч"
        if total_cost > 0:
            report += f" | 💰 *{total_cost:.2f} ₽*"
        report += "\n\n"

    total_hours = df['duration'].sum()
    total_cost = df['cost'].sum()
    report += f"*📊 ВСЕГО:*\n"
    report += f"⏱ Часов: *{total_hours:.2f}*\n"
    if total_cost > 0:
        report += f"💰 Выручка: *{total_cost:.2f} ₽*"

    return report


def format_client_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "*📊 Сводка по клиентам (30 дней)*\n\nНет записей за выбранный период."

    report = "*📊 Сводка по клиентам (30 дней)*\n\n"

    for client, client_group in df.groupby('client'):
        client_hours = client_group['duration'].sum()
        client_cost = client_group['cost'].sum()

        report += f"🏢 *{client}*\n"

        for project, project_group in client_group.groupby('project'):
            project_hours = project_group['duration'].sum()
            project_cost = project_group['cost'].sum()

            report += f"  📁 {project}: {project_hours:.2f} ч"
            if project_cost > 0:
                report += f" | {project_cost:.2f} ₽"
            report += "\n"

        report += f"  *Итого по клиенту:* {client_hours:.2f} ч"
        if client_cost > 0:
            report += f" | *{client_cost:.2f} ₽*"
        report += "\n\n"

    total_hours = df['duration'].sum()
    total_cost = df['cost'].sum()
    report += f"*💼 ОБЩАЯ СТАТИСТИКА:*\n"
    report += f"⏱ Всего часов: *{total_hours:.2f}*\n"
    if total_cost > 0:
        report += f"💰 Общая выручка: *{total_cost:.2f} ₽*"

    return report


def export_to_excel(user_id: int) -> Optional[str]:
    df = get_time_entries(user_id, 30)

    if df.empty:
        return None

    export_df = df.copy()
    export_df['Дата'] = export_df['start_time'].dt.strftime('%Y-%m-%d')
    export_df['Время начала'] = export_df['start_time'].dt.strftime('%H:%M')

    export_df['Задача'] = df.apply(
        lambda row: f"{row['task_type']} ({row['description']})" 
        if pd.notna(row['description']) and row['description'] 
        else row['task_type'], 
        axis=1
    )

    export_df = export_df[[
        'Дата', 'Время начала', 'client', 'project', 
        'Задача', 'duration', 'hourly_rate', 'cost'
    ]]
    export_df.columns = [
        'Дата', 'Время начала', 'Клиент', 'Проект', 
        'Задача', 'Часы', 'Ставка (₽/ч)', 'Стоимость (₽)'
    ]

    filename = f'timetracker_{user_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Учёт времени')

        worksheet = writer.sheets['Учёт времени']
        for idx, col in enumerate(export_df.columns):
            max_length = max(
                export_df[col].astype(str).apply(len).max(),
                len(col)
            )
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)

    return filename


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start и /help с проверкой подписки"""
    user_id = update.effective_user.id
    bot = context.bot

    # *** ПРОВЕРКА ПОДПИСКИ ***
    if not await is_subscribed(user_id, bot):
        await update.message.reply_text(
            f"❌ Для доступа к боту TFL_Biller подпишитесь на канал 'Технологии для юриста':\n"
            f"👉 https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
        )
        return

    # *** ЕСЛИ ПОДПИСАН - ВЫВОДИМ МЕНЮ ***
    help_text = """
👋 *Добро пожаловать в бот учёта рабочего времени!*

📋 *Управление клиентами и проектами:*
/add\\_client — добавить клиента
/add\\_project — добавить проект
/clients — список клиентов
/projects — список проектов

⏱ *Учёт времени:*
/work — начать работу
/stop — завершить работу
/status — текущий статус

📊 *Отчёты:*
/today — отчёт за сегодня
/week — отчёт за неделю
/month — отчёт за месяц
/summary — сводка по клиентам
/export — экспорт в Excel

ℹ️ *Прочее:*
/help — эта справка
/cancel — отменить текущую операцию

Начните с добавления клиента командой /add\\_client!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def add_client_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 *Добавление клиента*\n\nВведите название клиента/компании:", parse_mode='Markdown')
    return WAITING_CLIENT_NAME


async def add_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    client_name = update.message.text.strip()

    if add_client(user_id, client_name):
        await update.message.reply_text(f"✅ Клиент '*{client_name}*' успешно добавлен!", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"⚠️ Клиент '*{client_name}*' уже существует!", parse_mode='Markdown')

    return ConversationHandler.END


async def add_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clients = get_user_clients(user_id)

    if not clients:
        await update.message.reply_text(
            "⚠️ У вас пока нет клиентов!\n\nСначала добавьте клиента командой /add_client"
        )
        return ConversationHandler.END

    keyboard = []
    for client_id, client_name, _ in clients:
        keyboard.append([InlineKeyboardButton(client_name, callback_data=f"client_{client_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📁 *Добавление проекта*\n\nВыберите клиента:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return WAITING_PROJECT_CLIENT


async def add_project_client_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    client_id = int(query.data.split('_')[1])
    context.user_data['project_client_id'] = client_id

    await query.edit_message_text("📝 Введите название проекта:")
    return WAITING_PROJECT_NAME


async def add_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['project_name'] = update.message.text.strip()
    await update.message.reply_text("💰 Введите почасовую ставку в рублях (или 0, если без оплаты):")
    return WAITING_PROJECT_RATE


async def add_project_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rate = float(update.message.text.strip().replace(',', '.'))
        if rate < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Пожалуйста, введите корректное число (например: 1500 или 0)")
        return WAITING_PROJECT_RATE

    user_id = update.effective_user.id
    client_id = context.user_data['project_client_id']
    project_name = context.user_data['project_name']

    if add_project(user_id, client_id, project_name, rate):
        rate_text = f"{rate:.2f} ₽/час" if rate > 0 else "без оплаты"
        await update.message.reply_text(
            f"✅ Проект '*{project_name}*' успешно добавлен!\n💰 Ставка: {rate_text}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"⚠️ Проект '*{project_name}*' для этого клиента уже существует!",
            parse_mode='Markdown'
        )

    context.user_data.clear()
    return ConversationHandler.END


async def list_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clients = get_user_clients(user_id)

    if not clients:
        await update.message.reply_text("📋 У вас пока нет клиентов.\n\nДобавьте клиента командой /add_client")
        return

    text = "*📋 Ваши клиенты:*\n\n"
    for _, name, created_at in clients:
        created_date = datetime.fromisoformat(created_at).strftime('%d.%m.%Y')
        text += f"• {name} _(добавлен {created_date})_\n"

    await update.message.reply_text(text, parse_mode='Markdown')


async def list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    projects_dict = get_projects_by_client(user_id)

    if not projects_dict:
        await update.message.reply_text(
            "📁 У вас пока нет проектов.\n\nДобавьте проект командой /add_project"
        )
        return

    text = "*📁 Ваши проекты:*\n\n"
    for client_name, projects in projects_dict.items():
        text += f"🏢 *{client_name}*\n"
        for project_name, rate in projects:
            rate_text = f"{rate:.2f} ₽/ч" if rate > 0 else "без оплаты"
            text += f"  • {project_name} ({rate_text})\n"
        text += "\n"

    await update.message.reply_text(text, parse_mode='Markdown')


async def work_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    active = get_active_work(user_id)
    if active:
        _, project_name, task_type, description, start_time, client_name = active
        start_dt = datetime.fromisoformat(start_time)
        elapsed = datetime.now() - start_dt
        hours = elapsed.total_seconds() / 3600

        task_text = task_type
        if description:
            task_text += f" ({description})"

        await update.message.reply_text(
            f"⚠️ У вас уже есть активная работа!\n\n"
            f"🏢 Клиент: {client_name}\n"
            f"📁 Проект: {project_name}\n"
            f"📝 Задача: {task_text}\n"
            f"⏱ Прошло: {hours:.2f} ч\n\n"
            f"Завершите её командой /stop"
        )
        return ConversationHandler.END

    projects = get_user_projects(user_id)
    if not projects:
        await update.message.reply_text(
            "⚠️ У вас пока нет проектов!\n\nДобавьте проект командой /add_project"
        )
        return ConversationHandler.END

    keyboard = []
    for project_id, project_name, _, client_name in projects:
        button_text = f"{client_name} → {project_name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"proj_{project_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⏱ *Начало работы*\n\nВыберите проект:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return WAITING_PROJECT_CLIENT


async def work_project_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    project_id = int(query.data.split('_')[1])
    context.user_data['work_project_id'] = project_id

    keyboard = []
    for i, task_type in enumerate(TASK_TYPES):
        keyboard.append([InlineKeyboardButton(task_type, callback_data=f"task_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📝 Выберите тип задачи:",
        reply_markup=reply_markup
    )
    return WAITING_PROJECT_NAME


async def work_task_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    task_idx = int(query.data.split('_')[1])
    task_type = TASK_TYPES[task_idx]

    if task_type == "✍️ Другое":
        context.user_data['work_task_type'] = task_type
        await query.edit_message_text("✍️ Введите описание задачи:")
        return WAITING_CUSTOM_TASK

    user_id = update.effective_user.id
    project_id = context.user_data['work_project_id']

    start_work(user_id, project_id, task_type)

    projects = get_user_projects(user_id)
    project_info = next((p for p in projects if p[0] == project_id), None)

    if project_info:
        _, project_name, _, client_name = project_info
        start_time = datetime.now().strftime('%H:%M')
        await query.edit_message_text(
            f"✅ *Таймер запущен!*\n\n"
            f"🏢 Клиент: {client_name}\n"
            f"📁 Проект: {project_name}\n"
            f"📝 Задача: {task_type}\n"
            f"⏰ Начало: {start_time}",
            parse_mode='Markdown'
        )

    context.user_data.clear()
    return ConversationHandler.END


async def work_custom_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    project_id = context.user_data['work_project_id']
    task_type = context.user_data['work_task_type']
    description = update.message.text.strip()

    start_work(user_id, project_id, task_type, description)

    projects = get_user_projects(user_id)
    project_info = next((p for p in projects if p[0] == project_id), None)

    if project_info:
        _, project_name, _, client_name = project_info
        start_time = datetime.now().strftime('%H:%M')
        await update.message.reply_text(
            f"✅ *Таймер запущен!*\n\n"
            f"🏢 Клиент: {client_name}\n"
            f"📁 Проект: {project_name}\n"
            f"📝 Задача: {task_type} ({description})\n"
            f"⏰ Начало: {start_time}",
            parse_mode='Markdown'
        )

    context.user_data.clear()
    return ConversationHandler.END


async def work_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = stop_work(user_id)

    if not result:
        await update.message.reply_text("⚠️ Нет активной работы для остановки.")
        return

    project_name, task_type, description, duration, client_name = result

    task_text = task_type
    if description:
        task_text += f" ({description})"

    await update.message.reply_text(
        f"✅ *Работа завершена!*\n\n"
        f"🏢 Клиент: {client_name}\n"
        f"📁 Проект: {project_name}\n"
        f"📝 Задача: {task_text}\n"
        f"⏱ Длительность: *{duration:.2f} ч*",
        parse_mode='Markdown'
    )


async def work_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active = get_active_work(user_id)

    if not active:
        await update.message.reply_text("ℹ️ Нет активной работы.\n\nНачните работу командой /work")
        return

    _, project_name, task_type, description, start_time, client_name = active
    start_dt = datetime.fromisoformat(start_time)
    elapsed = datetime.now() - start_dt
    hours = elapsed.total_seconds() / 3600

    task_text = task_type
    if description:
        task_text += f" ({description})"

    start_time_str = start_dt.strftime('%H:%M')

    await update.message.reply_text(
        f"⏱ *Активная работа*\n\n"
        f"🏢 Клиент: {client_name}\n"
        f"📁 Проект: {project_name}\n"
        f"📝 Задача: {task_text}\n"
        f"⏰ Начало: {start_time_str}\n"
        f"⏱ Прошло: *{hours:.2f} ч*",
        parse_mode='Markdown'
    )


async def report_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 1)
    report = format_report(df, "📊 Отчёт за сегодня")
    await update.message.reply_text(report, parse_mode='Markdown')


async def report_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 7)
    report = format_report(df, "📊 Отчёт за неделю")
    await update.message.reply_text(report, parse_mode='Markdown')


async def report_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 30)
    report = format_report(df, "📊 Отчёт за месяц")
    await update.message.reply_text(report, parse_mode='Markdown')


async def report_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 30)
    report = format_client_summary(df)
    await update.message.reply_text(report, parse_mode='Markdown')


async def report_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    await update.message.reply_text("📊 Формирую Excel-файл...")

    filename = export_to_excel(user_id)

    if not filename:
        await update.message.reply_text("⚠️ Нет данных для экспорта.")
        return

    try:
        with open(filename, 'rb') as file:
            await update.message.reply_document(
                document=file,
                filename=filename,
                caption="✅ Отчёт за последние 30 дней"
            )

        import os
        os.remove(filename)
    except Exception as e:
        logger.error(f"Ошибка при отправке файла: {e}")
        await update.message.reply_text("⚠️ Ошибка при создании файла.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END


def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    add_client_handler = ConversationHandler(
        entry_points=[CommandHandler('add_client', add_client_start)],
        states={
            WAITING_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    add_project_handler = ConversationHandler(
        entry_points=[CommandHandler('add_project', add_project_start)],
        states={
            WAITING_PROJECT_CLIENT: [CallbackQueryHandler(add_project_client_selected, pattern='^client_')],
            WAITING_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_name)],
            WAITING_PROJECT_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_rate)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    work_handler = ConversationHandler(
        entry_points=[CommandHandler('work', work_start)],
        states={
            WAITING_PROJECT_CLIENT: [CallbackQueryHandler(work_project_selected, pattern='^proj_')],
            WAITING_PROJECT_NAME: [CallbackQueryHandler(work_task_selected, pattern='^task_')],
            WAITING_CUSTOM_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, work_custom_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler(['start', 'help'], start_command))
    application.add_handler(add_client_handler)
    application.add_handler(add_project_handler)
    application.add_handler(work_handler)
    application.add_handler(CommandHandler('stop', work_stop))
    application.add_handler(CommandHandler('status', work_status))
    application.add_handler(CommandHandler('clients', list_clients))
    application.add_handler(CommandHandler('projects', list_projects))
    application.add_handler(CommandHandler('today', report_today))
    application.add_handler(CommandHandler('week', report_week))
    application.add_handler(CommandHandler('month', report_month))
    application.add_handler(CommandHandler('summary', report_summary))
    application.add_handler(CommandHandler('export', report_export))

    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
