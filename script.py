
# Создам полный код Telegram-бота для учёта рабочего времени юристов

bot_code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот для учёта рабочего времени юристов
Версия: 1.0
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

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ ====================
# Токен бота (ЗАМЕНИТЕ на свой токен от @BotFather)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

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

# ==================== РАБОТА С БАЗОЙ ДАННЫХ ====================

def init_db():
    """Инициализация базы данных SQLite"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица клиентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    ''')
    
    # Таблица проектов
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
    
    # Таблица записей времени
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

# ==================== ФУНКЦИИ ДЛЯ КЛИЕНТОВ ====================

def add_client(user_id: int, name: str) -> bool:
    """Добавить клиента"""
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
    """Получить всех клиентов пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, created_at FROM clients WHERE user_id = ? ORDER BY name',
        (user_id,)
    )
    clients = cursor.fetchall()
    conn.close()
    return clients

# ==================== ФУНКЦИИ ДЛЯ ПРОЕКТОВ ====================

def add_project(user_id: int, client_id: int, name: str, hourly_rate: float) -> bool:
    """Добавить проект"""
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
    """Получить все проекты пользователя с информацией о клиентах"""
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
    """Получить проекты, сгруппированные по клиентам"""
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

# ==================== ФУНКЦИИ ДЛЯ УЧЁТА ВРЕМЕНИ ====================

def start_work(user_id: int, project_id: int, task_type: str, description: str = None) -> bool:
    """Начать работу"""
    # Проверяем, нет ли активной работы
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
    """Получить активную запись работы"""
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
    """Остановить работу и вернуть информацию о ней"""
    active_work = get_active_work(user_id)
    if not active_work:
        return None
    
    entry_id, project_name, task_type, description, start_time, client_name = active_work
    end_time = datetime.now()
    start_dt = datetime.fromisoformat(start_time)
    duration = (end_time - start_dt).total_seconds() / 3600  # В часах
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE time_entries SET end_time = ?, duration = ? WHERE id = ?',
        (end_time.isoformat(), duration, entry_id)
    )
    conn.commit()
    conn.close()
    
    return (project_name, task_type, description, duration, client_name)

# ==================== ФУНКЦИИ ДЛЯ ОТЧЁТОВ ====================

def get_time_entries(user_id: int, days: int) -> pd.DataFrame:
    """Получить записи времени за последние N дней"""
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
    """Форматировать отчёт"""
    if df.empty:
        return f"*{title}*\n\nНет записей за выбранный период."
    
    report = f"*{title}*\n\n"
    
    # Группировка по проектам
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
    
    # Общие итоги
    total_hours = df['duration'].sum()
    total_cost = df['cost'].sum()
    report += f"*📊 ВСЕГО:*\n"
    report += f"⏱ Часов: *{total_hours:.2f}*\n"
    if total_cost > 0:
        report += f"💰 Выручка: *{total_cost:.2f} ₽*"
    
    return report

def format_client_summary(df: pd.DataFrame) -> str:
    """Форматировать сводку по клиентам"""
    if df.empty:
        return "*📊 Сводка по клиентам (30 дней)*\n\nНет записей за выбранный период."
    
    report = "*📊 Сводка по клиентам (30 дней)*\n\n"
    
    # Группировка по клиентам и проектам
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
    
    # Общие итоги
    total_hours = df['duration'].sum()
    total_cost = df['cost'].sum()
    report += f"*💼 ОБЩАЯ СТАТИСТИКА:*\n"
    report += f"⏱ Всего часов: *{total_hours:.2f}*\n"
    if total_cost > 0:
        report += f"💰 Общая выручка: *{total_cost:.2f} ₽*"
    
    return report

def export_to_excel(user_id: int) -> Optional[str]:
    """Экспорт данных в Excel"""
    df = get_time_entries(user_id, 30)
    
    if df.empty:
        return None
    
    # Подготовка данных для экспорта
    export_df = df.copy()
    export_df['Дата'] = export_df['start_time'].dt.strftime('%Y-%m-%d')
    export_df['Время начала'] = export_df['start_time'].dt.strftime('%H:%M')
    export_df = export_df[[
        'Дата', 'Время начала', 'client', 'project', 
        'task_type', 'duration', 'hourly_rate', 'cost'
    ]]
    export_df.columns = [
        'Дата', 'Время начала', 'Клиент', 'Проект', 
        'Задача', 'Часы', 'Ставка (₽/ч)', 'Стоимость (₽)'
    ]
    
    # Добавляем описание к задаче если есть
    if 'description' in df.columns:
        export_df['Задача'] = df.apply(
            lambda row: f"{row['task_type']} ({row['description']})" 
            if pd.notna(row['description']) and row['description'] 
            else row['task_type'], 
            axis=1
        )
    
    # Сохранение в Excel
    filename = f'timetracker_{user_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Учёт времени')
        
        # Автоматическая настройка ширины столбцов
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
    """Обработчик команды /start и /help"""
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

# ==================== ДОБАВЛЕНИЕ КЛИЕНТА ====================

async def add_client_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления клиента"""
    await update.message.reply_text("📋 *Добавление клиента*\n\nВведите название клиента/компании:", parse_mode='Markdown')
    return WAITING_CLIENT_NAME

async def add_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение имени клиента"""
    user_id = update.effective_user.id
    client_name = update.message.text.strip()
    
    if add_client(user_id, client_name):
        await update.message.reply_text(f"✅ Клиент '*{client_name}*' успешно добавлен!", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"⚠️ Клиент '*{client_name}*' уже существует!", parse_mode='Markdown')
    
    return ConversationHandler.END

# ==================== ДОБАВЛЕНИЕ ПРОЕКТА ====================

async def add_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления проекта"""
    user_id = update.effective_user.id
    clients = get_user_clients(user_id)
    
    if not clients:
        await update.message.reply_text(
            "⚠️ У вас пока нет клиентов!\n\nСначала добавьте клиента командой /add_client"
        )
        return ConversationHandler.END
    
    # Создаём кнопки с клиентами
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
    """Клиент выбран, запрашиваем название проекта"""
    query = update.callback_query
    await query.answer()
    
    client_id = int(query.data.split('_')[1])
    context.user_data['project_client_id'] = client_id
    
    await query.edit_message_text("📝 Введите название проекта:")
    return WAITING_PROJECT_NAME

async def add_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение названия проекта, запрос ставки"""
    context.user_data['project_name'] = update.message.text.strip()
    await update.message.reply_text("💰 Введите почасовую ставку в рублях (или 0, если без оплаты):")
    return WAITING_PROJECT_RATE

async def add_project_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение ставки и создание проекта"""
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
    
    # Очистка данных
    context.user_data.clear()
    return ConversationHandler.END

# ==================== ПРОСМОТР СПИСКОВ ====================

async def list_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вывести список клиентов"""
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
    """Вывести список проектов"""
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

# ==================== УЧЁТ ВРЕМЕНИ ====================

async def work_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать работу - выбор проекта"""
    user_id = update.effective_user.id
    
    # Проверка активной работы
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
    
    # Получение проектов
    projects = get_user_projects(user_id)
    if not projects:
        await update.message.reply_text(
            "⚠️ У вас пока нет проектов!\n\nДобавьте проект командой /add_project"
        )
        return ConversationHandler.END
    
    # Создание кнопок с проектами
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
    return WAITING_PROJECT_CLIENT  # Используем это состояние для выбора проекта

async def work_project_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проект выбран, выбор типа задачи"""
    query = update.callback_query
    await query.answer()
    
    project_id = int(query.data.split('_')[1])
    context.user_data['work_project_id'] = project_id
    
    # Создание кнопок с типами задач
    keyboard = []
    for i, task_type in enumerate(TASK_TYPES):
        keyboard.append([InlineKeyboardButton(task_type, callback_data=f"task_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📝 Выберите тип задачи:",
        reply_markup=reply_markup
    )
    return WAITING_PROJECT_NAME  # Используем это состояние для выбора задачи

async def work_task_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Задача выбрана, запуск таймера"""
    query = update.callback_query
    await query.answer()
    
    task_idx = int(query.data.split('_')[1])
    task_type = TASK_TYPES[task_idx]
    
    # Если выбрано "Другое", запрашиваем описание
    if task_type == "✍️ Другое":
        context.user_data['work_task_type'] = task_type
        await query.edit_message_text("✍️ Введите описание задачи:")
        return WAITING_CUSTOM_TASK
    
    # Иначе сразу запускаем таймер
    user_id = update.effective_user.id
    project_id = context.user_data['work_project_id']
    
    start_work(user_id, project_id, task_type)
    
    # Получаем информацию о проекте для сообщения
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
    """Сохранение описания для кастомной задачи"""
    user_id = update.effective_user.id
    project_id = context.user_data['work_project_id']
    task_type = context.user_data['work_task_type']
    description = update.message.text.strip()
    
    start_work(user_id, project_id, task_type, description)
    
    # Получаем информацию о проекте
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
    """Остановить работу"""
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
    """Показать текущий статус"""
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

# ==================== ОТЧЁТЫ ====================

async def report_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отчёт за сегодня"""
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 1)
    report = format_report(df, "📊 Отчёт за сегодня")
    await update.message.reply_text(report, parse_mode='Markdown')

async def report_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отчёт за неделю"""
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 7)
    report = format_report(df, "📊 Отчёт за неделю")
    await update.message.reply_text(report, parse_mode='Markdown')

async def report_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отчёт за месяц"""
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 30)
    report = format_report(df, "📊 Отчёт за месяц")
    await update.message.reply_text(report, parse_mode='Markdown')

async def report_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сводка по клиентам"""
    user_id = update.effective_user.id
    df = get_time_entries(user_id, 30)
    report = format_client_summary(df)
    await update.message.reply_text(report, parse_mode='Markdown')

async def report_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт в Excel"""
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
        
        # Удаляем файл после отправки
        import os
        os.remove(filename)
    except Exception as e:
        logger.error(f"Ошибка при отправке файла: {e}")
        await update.message.reply_text("⚠️ Ошибка при создании файла.")

# ==================== ОТМЕНА ====================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    context.user_data.clear()
    await update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================

def main():
    """Запуск бота"""
    # Инициализация БД
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчик добавления клиента
    add_client_handler = ConversationHandler(
        entry_points=[CommandHandler('add_client', add_client_start)],
        states={
            WAITING_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Обработчик добавления проекта
    add_project_handler = ConversationHandler(
        entry_points=[CommandHandler('add_project', add_project_start)],
        states={
            WAITING_PROJECT_CLIENT: [CallbackQueryHandler(add_project_client_selected, pattern='^client_')],
            WAITING_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_name)],
            WAITING_PROJECT_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_rate)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Обработчик начала работы
    work_handler = ConversationHandler(
        entry_points=[CommandHandler('work', work_start)],
        states={
            WAITING_PROJECT_CLIENT: [CallbackQueryHandler(work_project_selected, pattern='^proj_')],
            WAITING_PROJECT_NAME: [CallbackQueryHandler(work_task_selected, pattern='^task_')],
            WAITING_CUSTOM_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, work_custom_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Добавление обработчиков
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
    
    # Запуск бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
'''

# Сохраняем код в файл
with open('lawyer_timetracker_bot.py', 'w', encoding='utf-8') as f:
    f.write(bot_code)

print("✅ Файл lawyer_timetracker_bot.py создан")

# Создаём файл requirements.txt
requirements = '''python-telegram-bot==20.7
pandas==2.2.0
openpyxl==3.1.2
'''

with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.write(requirements)

print("✅ Файл requirements.txt создан")

# Создаём инструкцию по установке
installation_guide = '''# Инструкция по установке и запуску Telegram-бота учёта рабочего времени

## Шаг 1: Подготовка

### 1.1. Установите Python
- Скачайте Python 3.9 или новее с официального сайта: https://www.python.org/downloads/
- При установке обязательно отметьте "Add Python to PATH"

### 1.2. Проверьте установку
Откройте командную строку (Windows) или терминал (Linux/Mac) и выполните:
```bash
python --version
```

## Шаг 2: Создание бота в Telegram

1. Найдите в Telegram бота @BotFather
2. Отправьте команду `/newbot`
3. Введите имя бота (например: "Мой учёт времени")
4. Введите username бота (должен заканчиваться на 'bot', например: `my_timetracker_bot`)
5. BotFather отправит вам токен - это длинная строка вида: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
6. **СОХРАНИТЕ ЭТОТ ТОКЕН!** Он понадобится в следующем шаге

## Шаг 3: Настройка файлов

### 3.1. Создайте папку для бота
```bash
mkdir lawyer_timetracker
cd lawyer_timetracker
```

### 3.2. Скопируйте файлы
Поместите в эту папку файлы:
- `lawyer_timetracker_bot.py`
- `requirements.txt`

### 3.3. Откройте файл lawyer_timetracker_bot.py
Найдите строку (примерно строка 37):
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

Замените `YOUR_BOT_TOKEN_HERE` на токен, который вы получили от BotFather, например:
```python
BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
```

Сохраните файл.

## Шаг 4: Установка зависимостей

Откройте командную строку/терминал в папке с ботом и выполните:

```bash
pip install -r requirements.txt
```

Дождитесь окончания установки всех библиотек.

## Шаг 5: Запуск бота

В той же папке выполните:

```bash
python lawyer_timetracker_bot.py
```

Если всё настроено правильно, вы увидите сообщение:
```
INFO - Бот запущен!
```

## Шаг 6: Использование бота

1. Найдите вашего бота в Telegram по username, который вы создали
2. Нажмите "Start" или отправьте команду `/start`
3. Следуйте инструкциям бота

### Первые шаги:
1. Добавьте клиента: `/add_client`
2. Добавьте проект: `/add_project`
3. Начните работу: `/work`
4. Завершите работу: `/stop`
5. Посмотрите отчёт: `/today`, `/week`, `/month`

## Остановка бота

Для остановки бота нажмите `Ctrl+C` в командной строке/терминале.

## Автоматический запуск (опционально)

### На Windows:
Создайте файл `start_bot.bat` с содержимым:
```batch
@echo off
cd /d %~dp0
python lawyer_timetracker_bot.py
pause
```

Теперь бот можно запускать двойным кликом по этому файлу.

### На Linux/Mac:
Создайте файл `start_bot.sh` с содержимым:
```bash
#!/bin/bash
cd "$(dirname "$0")"
python3 lawyer_timetracker_bot.py
```

Сделайте его исполняемым:
```bash
chmod +x start_bot.sh
```

Запуск:
```bash
./start_bot.sh
```

## Запуск на сервере (Timeweb или другой хостинг)

### Если вы используете VPS/сервер:

1. Подключитесь к серверу по SSH
2. Установите Python:
```bash
sudo apt update
sudo apt install python3 python3-pip
```

3. Загрузите файлы на сервер (через SFTP или git)

4. Установите зависимости:
```bash
pip3 install -r requirements.txt
```

5. Запустите бота в фоновом режиме с помощью screen:
```bash
screen -S timetracker
python3 lawyer_timetracker_bot.py
```

6. Отключитесь от screen: нажмите `Ctrl+A`, затем `D`

7. Бот продолжит работать даже после отключения от сервера

Для возврата к боту:
```bash
screen -r timetracker
```

## Решение проблем

### Ошибка: "No module named 'telegram'"
```bash
pip install python-telegram-bot --upgrade
```

### Ошибка: "Unauthorized" или "Invalid token"
Проверьте, что токен в коде точно совпадает с токеном от BotFather.

### Бот не отвечает
1. Убедитесь, что бот запущен (видите "Бот запущен!")
2. Проверьте интернет-соединение
3. Перезапустите бота

### База данных повреждена
Удалите файл `lawyer_timetracker.db` и перезапустите бота (все данные будут потеряны!)

## Резервное копирование

Файл `lawyer_timetracker.db` содержит все ваши данные. Регулярно делайте его резервные копии!

```bash
# Linux/Mac
cp lawyer_timetracker.db lawyer_timetracker.db.backup

# Windows
copy lawyer_timetracker.db lawyer_timetracker.db.backup
```

## Поддержка

Если возникли проблемы:
1. Проверьте, что используется Python 3.9+
2. Убедитесь, что все библиотеки установлены
3. Проверьте логи в консоли на наличие ошибок
4. Убедитесь, что токен бота указан правильно
'''

with open('INSTALLATION.md', 'w', encoding='utf-8') as f:
    f.write(installation_guide)

print("✅ Файл INSTALLATION.md создан")

# Создаём краткое руководство пользователя
user_guide = '''# Руководство пользователя: Telegram-бот учёта рабочего времени

## Команды бота

### 📋 Управление клиентами и проектами

**`/add_client`** — Добавить нового клиента
- Бот попросит ввести название клиента/компании
- Пример: "ООО Рога и копыта", "Иванов И.И."

**`/add_project`** — Добавить новый проект
- Выберите клиента из списка
- Введите название проекта
- Укажите почасовую ставку (₽/час) или 0, если без оплаты

**`/clients`** — Просмотр всех клиентов
- Показывает список ваших клиентов с датой добавления

**`/projects`** — Просмотр всех проектов
- Показывает проекты, сгруппированные по клиентам
- Отображает ставку для каждого проекта

### ⏱ Учёт рабочего времени

**`/work`** — Начать работу
1. Выберите проект из списка
2. Выберите тип задачи:
   - 📝 Подготовка иска
   - 📄 Подготовка договора
   - 💬 Консультация
   - 📚 Изучение материалов
   - ⚖️ Судебное заседание
   - 📞 Переговоры
   - 🔍 Анализ документов
   - ✉️ Переписка с клиентом
   - 🔎 Исследование практики
   - 📋 Подготовка заявления
   - ✍️ Другое (можно ввести свое описание)
3. Таймер запустится автоматически

**`/stop`** — Завершить работу
- Останавливает текущий таймер
- Показывает общую длительность работы

**`/status`** — Текущий статус
- Показывает, работаете ли вы сейчас
- Отображает проект, задачу и прошедшее время

### 📊 Отчёты

**`/today`** — Отчёт за сегодня
- Группировка по проектам и задачам
- Общее количество часов за день

**`/week`** — Отчёт за неделю (последние 7 дней)
- Детализация по проектам и задачам
- Суммарное время за неделю

**`/month`** — Отчёт за месяц (последние 30 дней)
- Полная детализация
- Расчёт стоимости работ (если указана ставка)
- Итоговая выручка

**`/summary`** — Сводка по клиентам (30 дней)
- Группировка по клиентам → проектам
- Часы и выручка по каждому клиенту
- Общая статистика

**`/export`** — Экспорт в Excel
- Создаёт Excel-файл с детальной информацией
- Столбцы: Дата, Время, Клиент, Проект, Задача, Часы, Ставка, Стоимость
- Удобно для отправки клиентам или бухгалтерии

### ℹ️ Прочее

**`/start`** или **`/help`** — Справка
- Показывает список всех команд

**`/cancel`** — Отменить операцию
- Прерывает текущий диалог с ботом

## Примеры использования

### Сценарий 1: Первый день работы

```
Вы: /add_client
Бот: 📋 Введите название клиента:
Вы: ООО Рога и копыта
Бот: ✅ Клиент 'ООО Рога и копыта' добавлен!

Вы: /add_project
Бот: 📁 Выберите клиента: [кнопка: ООО Рога и копыта]
Вы: [нажимаете кнопку]
Бот: 📝 Введите название проекта:
Вы: Судебный спор о взыскании
Бот: 💰 Введите ставку (₽/час) или 0:
Вы: 2500
Бот: ✅ Проект 'Судебный спор о взыскании' добавлен! Ставка: 2500 ₽/час
```

### Сценарий 2: Обычный рабочий день

**9:00 — Начало работы над иском:**
```
Вы: /work
Бот: [показывает список проектов]
Вы: [выбираете "Судебный спор о взыскании"]
Бот: [показывает типы задач]
Вы: [выбираете "📝 Подготовка иска"]
Бот: ✅ Таймер запущен! Проект: Судебный спор о взыскании, Задача: 📝 Подготовка иска, Начало: 09:00
```

**11:30 — Завершение работы:**
```
Вы: /stop
Бот: ✅ Работа завершена! Проект: Судебный спор о взыскании, Задача: 📝 Подготовка иска, Длительность: 2.5 ч
```

**12:00 — Консультация клиента:**
```
Вы: /work
Бот: [выбираете проект]
Вы: [выбираете "💬 Консультация"]
Бот: ✅ Таймер запущен!
```

**13:00 — Проверка статуса:**
```
Вы: /status
Бот: ⏱ Активная работа
     📁 Проект: Судебный спор о взыскании
     📝 Задача: 💬 Консультация
     ⏰ Начало: 12:00
     ⏱ Прошло: 1.0 ч
```

**14:00 — Завершение консультации:**
```
Вы: /stop
Бот: ✅ Работа завершена! Длительность: 2.0 ч
```

**18:00 — Отчёт за день:**
```
Вы: /today
Бот: 📊 Отчёт за сегодня
     
     📁 ООО Рога и копыта → Судебный спор о взыскании
       • 📝 Подготовка иска: 2.50 ч
       • 💬 Консультация: 2.00 ч
       ⏱ Итого: 4.50 ч | 💰 11,250.00 ₽
     
     📊 ВСЕГО:
     ⏱ Часов: 4.50
     💰 Выручка: 11,250.00 ₽
```

### Сценарий 3: Конец месяца — отчёты

**Сводка по всем клиентам:**
```
Вы: /summary
Бот: 📊 Сводка по клиентам (30 дней)
     
     🏢 ООО Рога и копыта
       📁 Судебный спор о взыскании: 45.5 ч | 113,750 ₽
       📁 Договор поставки: 12.0 ч | 30,000 ₽
       Итого по клиенту: 57.5 ч | 143,750 ₽
     
     🏢 ИП Сидоров
       📁 Регистрация ООО: 8.0 ч | 20,000 ₽
       Итого по клиенту: 8.0 ч | 20,000 ₽
     
     💼 ОБЩАЯ СТАТИСТИКА:
     ⏱ Всего часов: 65.5
     💰 Общая выручка: 163,750 ₽
```

**Экспорт для бухгалтерии:**
```
Вы: /export
Бот: 📊 Формирую Excel-файл...
Бот: [отправляет файл] ✅ Отчёт за последние 30 дней
```

## Советы по работе

### 🎯 Лучшие практики

1. **Начинайте работу сразу:** Запускайте `/work` как только начинаете задачу
2. **Не забывайте останавливать:** Всегда делайте `/stop` после завершения
3. **Проверяйте статус:** Используйте `/status`, чтобы не забыть о включенном таймере
4. **Регулярные отчёты:** Проверяйте `/today` в конце дня
5. **Экспорт для клиентов:** Используйте `/export` для формирования счетов

### ⚠️ Важные ограничения

- **Одна задача:** Нельзя работать над несколькими задачами одновременно
- **Нет паузы:** Если нужно прерваться — сделайте `/stop`, потом `/work` снова
- **База данных:** Все данные хранятся локально в файле `lawyer_timetracker.db`
- **Резервные копии:** Регулярно сохраняйте файл базы данных

### 💡 Полезные идеи

**Для разных видов работы:**
- Создавайте отдельные проекты для разных дел одного клиента
- Используйте понятные названия проектов ("Дело №А40-12345" вместо просто "Иск")
- Указывайте реальные ставки для точного расчёта выручки

**Для отчётности:**
- Делайте `/export` в конце месяца для счетов
- Используйте `/summary` для анализа загрузки по клиентам
- Проверяйте `/week` для планирования следующей недели

**Для эффективности:**
- Выбирайте точные типы задач — это поможет анализировать, на что уходит время
- Для нестандартных задач используйте "✍️ Другое" с описанием
- Регулярно проверяйте отчёты, чтобы понимать структуру рабочего времени

## Часто задаваемые вопросы

**Q: Можно ли изменить/удалить клиента или проект?**
A: В текущей версии нет — только добавление. Для изменений нужно редактировать базу данных напрямую.

**Q: Что делать, если забыл остановить таймер?**
A: Сделайте `/stop` — время будет записано с момента запуска до остановки. К сожалению, нельзя отредактировать задним числом.

**Q: Можно ли добавить запись вручную за прошлое время?**
A: Нет, в текущей версии это не предусмотрено.

**Q: Где хранятся данные?**
A: В файле `lawyer_timetracker.db` в папке с ботом.

**Q: Можно ли использовать бота с разных устройств?**
A: Да, если бот запущен на сервере — работайте с любого устройства через Telegram.

**Q: Безопасны ли мои данные?**
A: Данные хранятся локально. При работе на личном компьютере — да, безопасны. На сервере — используйте VPS только от надёжных провайдеров.

**Q: Как добавить второго пользователя?**
A: Каждый пользователь автоматически работает со своими данными. Просто дайте ссылку на бота другому юристу.

## Обновления и доработка

Этот бот — базовая версия. Возможные доработки:
- Редактирование/удаление клиентов и проектов
- Добавление записей за прошлое время
- Пауза/возобновление работы
- Настройка типов задач
- Графики и визуализация
- Интеграция с календарём
- Напоминания о незавершённых задачах

Для доработок обращайтесь к разработчику!
'''

with open('USER_GUIDE.md', 'w', encoding='utf-8') as f:
    f.write(user_guide)

print("✅ Файл USER_GUIDE.md создан")
print("\n" + "="*60)
print("ВСЕ ФАЙЛЫ УСПЕШНО СОЗДАНЫ!")
print("="*60)
print("\nСозданы следующие файлы:")
print("1. lawyer_timetracker_bot.py - основной код бота")
print("2. requirements.txt - список зависимостей")
print("3. INSTALLATION.md - инструкция по установке")
print("4. USER_GUIDE.md - руководство пользователя")
