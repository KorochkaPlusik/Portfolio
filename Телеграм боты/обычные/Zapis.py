import sqlite3
import telebot
from telebot import types
import datetime
import time
import threading
import logging

# --- Настройки ---
TOKEN = "8076421586:AAHOfzXV87qtFoyMn_jLQaw4Nhf7DPDc4Ec"  # замените на реальный токен
ADMIN_ID = 794991817      # укажите свой Telegram ID
bot = telebot.TeleBot(TOKEN)

# Глобальные словари для хранения контекста при добавлении записей и услуг администратором
admin_appointments = {}
admin_services = {}

# --- Логирование ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Инициализация базы данных ---
def init_db():
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                full_name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'client'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                duration TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service_id INTEGER,
                date TEXT,
                time TEXT,
                status TEXT DEFAULT 'confirmed',
                notified_1h INTEGER DEFAULT 0,
                notified_24h INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

init_db()

# --- Старт и регистрация ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (message.chat.id,))
        user = cursor.fetchone()

    if not user:
        bot.send_message(message.chat.id, "Привет! Для начала зарегистрируйтесь. Введите ваше ФИО:")
        bot.register_next_step_handler(message, register_name)
    else:
        # Если админ, показать панель администратора, иначе – панель пользователя
        if message.chat.id == ADMIN_ID:
            show_admin_menu(message.chat.id)
        else:
            show_user_menu(message.chat.id)

def register_name(message):
    full_name = message.text.strip()
    if not full_name:
        bot.send_message(message.chat.id, "ФИО не может быть пустым. Введите ваше ФИО:")
        bot.register_next_step_handler(message, register_name)
        return
    bot.send_message(message.chat.id, "Введите ваш номер телефона:")
    bot.register_next_step_handler(message, lambda msg: register_phone(msg, full_name))

def register_phone(message, full_name):
    phone = message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        bot.send_message(message.chat.id, "Некорректный номер телефона. Введите ещё раз:")
        bot.register_next_step_handler(message, lambda msg: register_phone(msg, full_name))
        return

    try:
        with sqlite3.connect("appointments.db") as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (telegram_id, full_name, phone) VALUES (?, ?, ?)",
                           (message.chat.id, full_name, phone))
            conn.commit()
    except sqlite3.IntegrityError:
        bot.send_message(message.chat.id, "Пользователь с таким Telegram ID уже зарегистрирован.")
        show_user_menu(message.chat.id)
        return

    bot.send_message(message.chat.id, "Регистрация завершена!")
    if message.chat.id == ADMIN_ID:
        show_admin_menu(message.chat.id)
    else:
        show_user_menu(message.chat.id)

# --- Панели меню ---
def show_user_menu(chat_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["📅 Записаться на приём", "📋 Мои записи", "📞 Связаться с администратором", "❓ Помощь"]
    keyboard.add(*buttons)
    bot.send_message(chat_id, "Выберите действие:", reply_markup=keyboard)

def show_admin_menu(chat_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # Админ-панель с набором кнопок
    buttons = ["Добавить услугу", "Добавить запись", "Просмотр всех записей", "Рассылка", "Статистика", "❓ Помощь"]
    keyboard.add(*buttons)
    bot.send_message(chat_id, "Панель администратора. Выберите действие:", reply_markup=keyboard)

# --- Обработка кнопок пользовательской панели ---
@bot.message_handler(func=lambda message: message.text in ["📅 Записаться на приём", "📋 Мои записи", "📞 Связаться с администратором", "❓ Помощь"] and message.chat.id != ADMIN_ID)
def user_menu_handler(message):
    if message.text == "📅 Записаться на приём":
        book_appointment(message)
    elif message.text == "📋 Мои записи":
        show_user_appointments(message)
    elif message.text == "📞 Связаться с администратором":
        contact_admin(message)
    elif message.text == "❓ Помощь":
        show_help(message)

# --- Обработка кнопок админ-панели ---
@bot.message_handler(func=lambda message: message.text in ["Добавить услугу", "Добавить запись", "Просмотр всех записей", "Рассылка", "Статистика", "❓ Помощь"] and message.chat.id == ADMIN_ID)
def admin_menu_handler(message):
    if message.text == "Добавить услугу":
        bot.send_message(message.chat.id, "Введите название услуги:")
        bot.register_next_step_handler(message, admin_get_service_name)
    elif message.text == "Добавить запись":
        admin_add_appointment(message)
    elif message.text == "Просмотр всех записей":
        show_all_appointments(message)
    elif message.text == "Рассылка":
        bot.send_message(message.chat.id, "Введите сообщение для рассылки:")
        bot.register_next_step_handler(message, admin_broadcast)
    elif message.text == "Статистика":
        show_statistics(message)
    elif message.text == "❓ Помощь":
        show_admin_help(message)

# --- Функции для пользователей ---
def book_appointment(message):
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM services")
        services = cursor.fetchall()

    if not services:
        bot.send_message(message.chat.id, "Нет доступных услуг. Обратитесь к администратору.")
        return

    keyboard = types.InlineKeyboardMarkup()
    for service in services:
        keyboard.add(types.InlineKeyboardButton(service[1], callback_data=f"service_{service[0]}"))
    bot.send_message(message.chat.id, "Выберите услугу:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def select_service(call):
    service_id = call.data.split("_")[1]
    bot.send_message(call.message.chat.id, "Введите дату в формате YYYY-MM-DD:")
    bot.register_next_step_handler(call.message, lambda msg: select_date(msg, service_id))

def select_date(message, service_id):
    try:
        datetime.datetime.strptime(message.text, "%Y-%m-%d")
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат даты. Введите дату в формате YYYY-MM-DD:")
        bot.register_next_step_handler(message, lambda msg: select_date(msg, service_id))
        return

    date = message.text
    bot.send_message(message.chat.id, "Введите время в формате HH:MM:")
    bot.register_next_step_handler(message, lambda msg: confirm_booking(msg, service_id, date))

def confirm_booking(message, service_id, date):
    appointment_time = message.text
    try:
        datetime.datetime.strptime(appointment_time, "%H:%M")
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат времени. Введите время в формате HH:MM:")
        bot.register_next_step_handler(message, lambda msg: confirm_booking(msg, service_id, date))
        return

    user_id = message.chat.id
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO appointments (user_id, service_id, date, time, status) VALUES (?, ?, ?, ?, 'confirmed')", 
                       (user_id, service_id, date, appointment_time))
        conn.commit()

    bot.send_message(message.chat.id, "Запись подтверждена!")
    show_user_menu(message.chat.id)

def show_user_appointments(message):
    user_id = message.chat.id
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        query = """
        SELECT a.id, s.name, s.price, a.date, a.time, a.status 
        FROM appointments a 
        JOIN services s ON a.service_id = s.id 
        WHERE a.user_id = ?
        ORDER BY a.date, a.time
        """
        cursor.execute(query, (user_id,))
        appointments = cursor.fetchall()

    if not appointments:
        bot.send_message(message.chat.id, "У вас нет записей.")
        show_user_menu(message.chat.id)
        return

    for appt in appointments:
        appt_id, service_name, price, date, time_str, status = appt
        text = f"ID: {appt_id}\nУслуга: {service_name}\nЦена: {price}\nДата: {date}\nВремя: {time_str}\nСтатус: {status}"
        markup = types.InlineKeyboardMarkup()
        if status == "confirmed":
            markup.add(types.InlineKeyboardButton("Отменить запись", callback_data=f"cancel_{appt_id}"))
        bot.send_message(message.chat.id, text, reply_markup=markup)
    show_user_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_appointment(call):
    appt_id = call.data.split("_")[1]
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appt_id,))
        conn.commit()
    bot.send_message(call.message.chat.id, "Запись отменена.")
    show_user_menu(call.message.chat.id)

def contact_admin(message):
    msg = bot.send_message(message.chat.id, "Введите ваше сообщение для администратора:")
    bot.register_next_step_handler(msg, forward_to_admin)

def forward_to_admin(message):
    forward_text = f"Сообщение от пользователя {message.from_user.id} ({message.from_user.first_name}):\n{message.text}"
    bot.send_message(ADMIN_ID, forward_text)
    bot.send_message(message.chat.id, "Ваше сообщение отправлено администратору.")
    show_user_menu(message.chat.id)

def show_help(message):
    help_text = ("Доступные функции:\n"
                 "📅 Записаться на приём – выбрать услугу и забронировать время\n"
                 "📋 Мои записи – просмотреть и отменить запись\n"
                 "📞 Связаться с администратором – отправить сообщение админу\n"
                 "❓ Помощь – информация о функционале")
    bot.send_message(message.chat.id, help_text)
    show_user_menu(message.chat.id)

# --- Функции для администратора ---

# Добавление услуги с выбором: бесплатная или платная
def admin_get_service_name(message):
    name = message.text.strip()
    if not name:
        bot.send_message(message.chat.id, "Название не может быть пустым. Введите название услуги:")
        bot.register_next_step_handler(message, admin_get_service_name)
        return
    admin_services[message.chat.id] = {"name": name}
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Да", callback_data="free_yes"),
                 types.InlineKeyboardButton("Нет", callback_data="free_no"))
    bot.send_message(message.chat.id, "Услуга бесплатная?", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data in ["free_yes", "free_no"])
def service_free_option(call):
    context = admin_services.get(call.message.chat.id, {})
    if call.data == "free_yes":
        context["price"] = 0
        bot.send_message(call.message.chat.id, "Укажите продолжительность услуги (например, 30 мин):")
        bot.register_next_step_handler(call.message, admin_get_service_duration)
    else:
        bot.send_message(call.message.chat.id, "Введите цену услуги (числом):")
        bot.register_next_step_handler(call.message, admin_get_service_price)
    admin_services[call.message.chat.id] = context

def admin_get_service_price(message):
    try:
        price = int(message.text)
    except ValueError:
        bot.send_message(message.chat.id, "Цена должна быть числом. Введите цену еще раз:")
        bot.register_next_step_handler(message, admin_get_service_price)
        return
    context = admin_services.get(message.chat.id, {})
    context["price"] = price
    admin_services[message.chat.id] = context
    bot.send_message(message.chat.id, "Укажите продолжительность услуги (например, 30 мин):")
    bot.register_next_step_handler(message, admin_get_service_duration)

def admin_get_service_duration(message):
    duration = message.text.strip()
    context = admin_services.get(message.chat.id, {})
    context["duration"] = duration
    admin_services[message.chat.id] = context
    name = context.get("name")
    price = context.get("price")
    duration = context.get("duration")
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO services (name, price, duration) VALUES (?, ?, ?)", (name, price, duration))
        conn.commit()
    bot.send_message(message.chat.id, f"Услуга '{name}' добавлена.")
    admin_services.pop(message.chat.id, None)
    show_admin_menu(message.chat.id)

# Добавление записи администратором
def admin_add_appointment(message):
    bot.send_message(message.chat.id, "Введите Telegram ID пользователя для записи:")
    bot.register_next_step_handler(message, process_admin_user_id)

def process_admin_user_id(message):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "Неверный Telegram ID. Попробуйте снова:")
        bot.register_next_step_handler(message, process_admin_user_id)
        return

    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        if cursor.fetchone() is None:
            bot.send_message(message.chat.id, "Пользователь не найден. Запись будет добавлена, но пользователь не зарегистрирован.")
    admin_appointments[message.chat.id] = {'user_id': user_id}

    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM services")
        services = cursor.fetchall()
    if not services:
        bot.send_message(message.chat.id, "Нет доступных услуг.")
        return
    keyboard = types.InlineKeyboardMarkup()
    for service in services:
        keyboard.add(types.InlineKeyboardButton(service[1], callback_data=f"admin_service_{service[0]}"))
    bot.send_message(message.chat.id, "Выберите услугу для записи:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_service_"))
def admin_select_service(call):
    service_id = call.data.split("_")[-1]
    context = admin_appointments.get(call.message.chat.id, {})
    context['service_id'] = service_id
    admin_appointments[call.message.chat.id] = context
    bot.send_message(call.message.chat.id, "Введите дату в формате YYYY-MM-DD:")
    bot.register_next_step_handler(call.message, admin_select_date)

def admin_select_date(message):
    try:
        datetime.datetime.strptime(message.text, "%Y-%m-%d")
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат даты. Введите дату в формате YYYY-MM-DD:")
        bot.register_next_step_handler(message, admin_select_date)
        return
    context = admin_appointments.get(message.chat.id, {})
    context['date'] = message.text.strip()
    admin_appointments[message.chat.id] = context
    bot.send_message(message.chat.id, "Введите время в формате HH:MM:")
    bot.register_next_step_handler(message, admin_select_time)

def admin_select_time(message):
    try:
        datetime.datetime.strptime(message.text, "%H:%M")
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат времени. Введите время в формате HH:MM:")
        bot.register_next_step_handler(message, admin_select_time)
        return
    context = admin_appointments.get(message.chat.id, {})
    context['time'] = message.text.strip()
    admin_appointments[message.chat.id] = context

    user_id = context.get('user_id')
    service_id = context.get('service_id')
    date = context.get('date')
    time_str = context.get('time')
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO appointments (user_id, service_id, date, time, status) VALUES (?, ?, ?, ?, 'confirmed')",
                       (user_id, service_id, date, time_str))
        conn.commit()
    bot.send_message(message.chat.id, "Запись успешно добавлена!")
    admin_appointments.pop(message.chat.id, None)
    show_admin_menu(message.chat.id)

def show_all_appointments(message):
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        query = """
        SELECT a.id, u.full_name, s.name, s.price, a.date, a.time, a.status 
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.telegram_id
        JOIN services s ON a.service_id = s.id
        ORDER BY a.date, a.time
        """
        cursor.execute(query)
        appointments = cursor.fetchall()
    if not appointments:
        bot.send_message(message.chat.id, "Записей не найдено.")
    else:
        for appt in appointments:
            appt_id, full_name, service_name, price, date, time_str, status = appt
            text = f"ID: {appt_id}\nПользователь: {full_name}\nУслуга: {service_name}\nЦена: {price}\nДата: {date}\nВремя: {time_str}\nСтатус: {status}"
            bot.send_message(message.chat.id, text)
    show_admin_menu(message.chat.id)

def admin_broadcast(message):
    broadcast_text = message.text
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM users")
        users = cursor.fetchall()
    for user in users:
        bot.send_message(user[0], f"[Рассылка]: {broadcast_text}")
    bot.send_message(message.chat.id, "Рассылка отправлена.")
    show_admin_menu(message.chat.id)

def show_admin_help(message):
    help_text = ("Админ-панель:\n"
                 "Добавить услугу – добавить новую услугу (выбор: бесплатная или платная, с указанием цены и длительности)\n"
                 "Добавить запись – добавить запись для пользователя\n"
                 "Просмотр всех записей – увидеть все записи\n"
                 "Рассылка – отправить сообщение всем пользователям\n"
                 "Статистика – сводная информация по записям\n"
                 "❓ Помощь – информация о функционале")
    bot.send_message(message.chat.id, help_text)
    show_admin_menu(message.chat.id)

def show_statistics(message):
    with sqlite3.connect("appointments.db") as conn:
        cursor = conn.cursor()
        # Общее количество записей
        cursor.execute("SELECT COUNT(*) FROM appointments")
        total = cursor.fetchone()[0]
        # Количество подтвержденных записей
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'confirmed'")
        confirmed = cursor.fetchone()[0]
        # Количество отмененных записей
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'cancelled'")
        cancelled = cursor.fetchone()[0]
        # Суммарный доход (услуги с ценой больше 0)
        cursor.execute("""
            SELECT SUM(s.price) FROM appointments a 
            JOIN services s ON a.service_id = s.id 
            WHERE a.status = 'confirmed' AND s.price > 0
        """)
        income = cursor.fetchone()[0]
        if income is None:
            income = 0

    stat_text = (f"Статистика записей:\n"
                 f"Общее количество записей: {total}\n"
                 f"Подтвержденных: {confirmed}\n"
                 f"Отменено: {cancelled}\n"
                 f"Суммарный доход: {income}")
    bot.send_message(message.chat.id, stat_text)
    show_admin_menu(message.chat.id)

# --- Фоновая функция отправки напоминаний ---
def send_reminders():
    while True:
        now = datetime.datetime.now()
        with sqlite3.connect("appointments.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, user_id, date, time, notified_1h, notified_24h FROM appointments WHERE status = 'confirmed'")
            appointments = cursor.fetchall()

        for appt in appointments:
            appt_id, user_id, date, appt_time, notified_1h, notified_24h = appt
            appointment_datetime_str = f"{date} {appt_time}"
            try:
                appointment_datetime = datetime.datetime.strptime(appointment_datetime_str, "%Y-%m-%d %H:%M")
            except ValueError:
                continue

            time_diff = (appointment_datetime - now).total_seconds()

            if 86340 <= time_diff <= 86460 and not notified_24h:
                bot.send_message(user_id, "🔔 Напоминание: у вас запись завтра!")
                with sqlite3.connect("appointments.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE appointments SET notified_24h = 1 WHERE id = ?", (appt_id,))
                    conn.commit()

            if 3540 <= time_diff <= 3660 and not notified_1h:
                bot.send_message(user_id, "🔔 Напоминание: у вас запись через 1 час!")
                with sqlite3.connect("appointments.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE appointments SET notified_1h = 1 WHERE id = ?", (appt_id,))
                    conn.commit()
        time.sleep(60)

# --- Запуск бота ---
if __name__ == "__main__":
    reminder_thread = threading.Thread(target=send_reminders, daemon=True)
    reminder_thread.start()
    bot.polling(none_stop=True)
