import telebot
import sqlite3
from telebot import types
import os

# Токен вашего бота
API_TOKEN = '7798627260:AAFM3rXChFaMtkJokmuVUMIUv5VhH51cJm8'
bot = telebot.TeleBot(API_TOKEN)

# Подключение к базе данных
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()

# Создание директории для сохранения фотографий
PHOTOS_DIR = 'photos'
if not os.path.exists(PHOTOS_DIR):
    os.makedirs(PHOTOS_DIR)

# Создание таблиц для хранения пользователей, анкет и комментариев
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    password TEXT,
    is_admin BOOLEAN
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    params TEXT,
    visit_date TEXT,
    user_id INTEGER,
    photo TEXT,
    photo2 TEXT,           
    comment TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER,
    user_id INTEGER,
    comment TEXT,
    is_admin BOOLEAN
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS forwarded_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER,
    forwarded_text TEXT
)''')

conn.commit()

# Админский ID и пароли
ADMIN_IDS = [6664891663, 1067251594, 7202416836, 768690148, 787079026, ]  # Добавляем новые ID админов
admin_passwords = {
    6664891663: "rЮ!a9*к№уD:b",
    7202416836: "fN6dy5V$hiLeNJbQjQDQE3",  # Пароль для нового админа
    1067251594: "^RhY4qk^2^QiBk4T",  # Еще один пароль для другого админа
    768690148: "тXЩtRд5-nЧCМ",
    787079026: "Sof&911bduUee64"
}

user_passwords = {
    123456789: "zkvjihsea",
    1235667: "uaiefhi",
    9988877544: "osducu3297q",
}

# Хранение состояний пользователей
user_states = {}

# Функция для показа меню
def show_menu(chat_id, is_admin=False):
    # Получение количества анкет в базе данных
    cursor.execute("SELECT COUNT(*) FROM profiles")
    profile_count = cursor.fetchone()[0]

    # Формируем текст сообщения с информацией
    user_id = chat_id
    menu_text = (
        f"Ваш Telegram ID: {user_id}\n"
        f"Количество анкет в базе данных: {profile_count}\n\n"
        f"Выберите действие:"
    )

    # Создаём inline-кнопки
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Поиск анкеты", callback_data="Поиск анкеты"))
    markup.add(types.InlineKeyboardButton("Добавить анкету", callback_data="Добавить анкету"))
    markup.add(types.InlineKeyboardButton("Выход", callback_data="Выход"))

    # Отправляем сообщение с inline-кнопками
    bot.send_message(chat_id, menu_text, reply_markup=markup)

# Обработка нажатия на кнопки из главного меню
@bot.callback_query_handler(func=lambda call: call.data in ["Поиск анкеты", "Добавить анкету", "Выход"])
def handle_main_menu_callbacks(call):
    if call.data == "Поиск анкеты":
        search_profile_handler(call.message)
    elif call.data == "Добавить анкету":
        add_profile_handler(call.message)
    elif call.data == "Выход":
        exit_handler(call.message)


# Проверка пароля
@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "Привет! Введите пароль для доступа.")
    user_states[message.chat.id] = 'awaiting_password'

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_password')
def password_handler(message):
    user_id = message.from_user.id
    entered_password = message.text

    # Проверяем, является ли пользователь администратором
    if user_id in ADMIN_IDS and admin_passwords.get(user_id) == entered_password:
        bot.send_message(message.chat.id, "Пароль администратора верный! Добро пожаловать.")
        user_states[message.chat.id] = 'admin_authenticated'
        show_menu(message.chat.id, is_admin=True)
    # Проверяем, является ли пользователь обычным пользователем
    elif user_passwords.get(user_id) == entered_password:
        bot.send_message(message.chat.id, "Пароль верный! Добро пожаловать.")
        user_states[message.chat.id] = 'user_authenticated'
        show_menu(message.chat.id, is_admin=False)
    else:
        bot.send_message(message.chat.id, "Неверный пароль! Попробуйте снова.")
        user_states[message.chat.id] = 'awaiting_password'

# Функция для добавления анкеты (только для администратора)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Добавить анкету')
def add_profile_handler(message):
    bot.send_message(message.chat.id, "Отправьте первое фото анкеты.")
    bot.register_next_step_handler(message, process_photo1)

def process_photo1(message):
    try:
        if message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            photo1_path = f"{PHOTOS_DIR}/{message.photo[-1].file_id}.jpg"

            with open(photo1_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            # Создаем inline-кнопки "Да" и "Нет"
            markup = types.InlineKeyboardMarkup()
            yes_button = types.InlineKeyboardButton('Да', callback_data=f'add_second_photo_yes:{photo1_path}')
            no_button = types.InlineKeyboardButton('Нет', callback_data=f'add_second_photo_no:{photo1_path}')
            markup.add(yes_button, no_button)

            # Спрашиваем, хочет ли пользователь добавить второе фото с inline-кнопками
            bot.send_message(message.chat.id, "Хотите добавить второе фото?", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
            show_menu(message.chat.id, is_admin=True)
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")
        show_menu(message.chat.id, is_admin=True)

@bot.callback_query_handler(func=lambda call: call.data in ['add_second_photo_yes', 'add_second_photo_no'])
def process_second_photo_callback(call):
    # Получаем путь к первой фотографии из словаря
    photo1_path = photo_paths.get(call.message.chat.id)

    if call.data == 'add_second_photo_yes':
        bot.send_message(call.message.chat.id, "Отправьте второе фото анкеты.")
        bot.register_next_step_handler(call.message, process_photo2, photo1_path)
    elif call.data == 'add_second_photo_no':
        # После ответа "Нет" запрашиваем данные анкеты
        msg = bot.send_message(call.message.chat.id, "Введите данные в формате:\nИмя\nФамилия:\nТелефон:\nПараметры:\nДата посещения:")
        bot.register_next_step_handler(msg, lambda msg: process_profile_data(msg, photo1_path, None))

def process_photo2(message, photo1_path):
    try:
        if message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            photo2_path = f"{PHOTOS_DIR}/{message.photo[-1].file_id}.jpg"

            with open(photo2_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            # После получения второго фото, запрашиваем данные анкеты
            msg = bot.send_message(message.chat.id, "Введите данные в формате:\nИмя\nФамилия:\nТелефон:\nПараметры:\nДата посещения:")
            bot.register_next_step_handler(msg, lambda msg: process_profile_data(msg, photo1_path, photo2_path))
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
            bot.register_next_step_handler(message, process_photo2, photo1_path)
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")
        show_menu(message.chat.id, is_admin=True)

def process_profile_data(message, photo1_path, photo2_path):
    try:
        data = message.text.split()
        if len(data) < 5:
            bot.send_message(message.chat.id, "Введите все данные корректно: Имя Фамилия Телефон Параметры Дата посещения")
            return

        first_name, last_name, phone, params, visit_date = data[0], data[1], data[2], " ".join(data[3:-1]), data[-1]

        # Сохраняем анкету с двумя фотографиями (или одной, если второй нет)
        cursor.execute('''INSERT INTO profiles (first_name, last_name, phone, params, visit_date, user_id, photo, photo2, comment) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (first_name, last_name, phone, params, visit_date, message.from_user.id, photo1_path, photo2_path, ''))
        conn.commit()
        bot.send_message(message.chat.id, "Анкета успешно добавлена!")
        show_menu(message.chat.id, is_admin=True)
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка при добавлении анкеты: {str(e)}")
        show_menu(message.chat.id, is_admin=True)
# Словарь для хранения путей к фотографиям
photo_paths = {}

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Добавить анкету')
def add_profile_handler(message):
    bot.send_message(message.chat.id, "Отправьте первое фото анкеты.")
    bot.register_next_step_handler(message, process_photo1)

def process_photo1(message):
    try:
        if message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            photo1_path = f"{PHOTOS_DIR}/{message.photo[-1].file_id}.jpg"

            with open(photo1_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            # Сохраняем путь к первой фотографии в словарь
            photo_paths[message.chat.id] = photo1_path

            # Создаем inline-кнопки "Да" и "Нет"
            markup = types.InlineKeyboardMarkup()
            yes_button = types.InlineKeyboardButton('Да', callback_data='add_second_photo_yes')
            no_button = types.InlineKeyboardButton('Нет', callback_data='add_second_photo_no')
            markup.add(yes_button, no_button)

            # Спрашиваем, хочет ли пользователь добавить второе фото с inline-кнопками
            bot.send_message(message.chat.id, "Хотите добавить второе фото?", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
            show_menu(message.chat.id, is_admin=True)
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")
        show_menu(message.chat.id, is_admin=True)

@bot.callback_query_handler(func=lambda call: call.data in ['add_second_photo_yes', 'add_second_photo_no'])
def process_second_photo_callback(call):
    # Получаем путь к первой фотографии из словаря
    photo1_path = photo_paths.get(call.message.chat.id)

    if call.data == 'add_second_photo_yes':
        bot.send_message(call.message.chat.id, "Отправьте второе фото анкеты.")
        bot.register_next_step_handler(call.message, process_photo2, photo1_path)
    elif call.data == 'add_second_photo_no':
        # После ответа "Нет" запрашиваем данные анкеты
        msg = bot.send_message(call.message.chat.id, "Введите данные в формате:\nИмя\nФамилия:\nТелефон:\nПараметры:\nДата посещения:")
        bot.register_next_step_handler(msg, lambda msg: process_profile_data(msg, photo1_path, None))

def process_photo2(message, photo1_path):
    try:
        if message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            photo2_path = f"{PHOTOS_DIR}/{message.photo[-1].file_id}.jpg"

            with open(photo2_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            # После получения второго фото, запрашиваем данные анкеты
            msg = bot.send_message(message.chat.id, "Введите данные в формате:\nИмя\nФамилия:\nТелефон:\nПараметры:\nДата посещения:")
            bot.register_next_step_handler(msg, lambda msg: process_profile_data(msg, photo1_path, photo2_path))
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
            bot.register_next_step_handler(message, process_photo2, photo1_path)
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")
        show_menu(message.chat.id, is_admin=True)

def process_profile_data(message, photo1_path, photo2_path):
    try:
        data = message.text.split()
        if len(data) < 5:
            bot.send_message(message.chat.id, "Введите все данные корректно: Имя Фамилия Телефон Параметры Дата посещения")
            return

        first_name, last_name, phone, params, visit_date = data[0], data[1], data[2], " ".join(data[3:-1]), data[-1]
        # Сохраняем анкету с двумя фотографиями (или одной, если второй нет)
        cursor.execute('''INSERT INTO profiles (first_name, last_name, phone, params, visit_date, user_id, photo, photo2, comment) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (first_name, last_name, phone, params, visit_date, message.from_user.id, photo1_path, photo2_path, ''))
        conn.commit()
        bot.send_message(message.chat.id, "Анкета успешно добавлена!")
        show_menu(message.chat.id, is_admin=True)
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка при добавлении анкеты: {str(e)}")
        show_menu(message.chat.id, is_admin=True)

@bot.callback_query_handler(func=lambda call: call.data == "exit_to_main_menu")
def exit_to_main_menu(call):
    user_id = call.from_user.id
    is_admin = (user_id in ADMIN_IDS)  # Исправление проверки
    bot.send_message(call.message.chat.id, "Вы возвращены в главное меню.")

    
    # Переход к главному меню
    show_menu(call.message.chat.id, is_admin=is_admin)
# Функция для удаления анкеты (только для администратора)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Удалить анкету')
def delete_profile_handler(message):
    bot.send_message(message.chat.id, "Введите ФИО или телефон анкеты для удаления:")
    bot.register_next_step_handler(message, process_profile_deletion)

def process_profile_deletion(message):
    search_criteria = message.text
    cursor.execute("SELECT * FROM profiles WHERE first_name  ' '  last_name LIKE ? OR phone LIKE ?", 
                   (f'%{search_criteria}%', f'%{search_criteria}%'))
    profiles = cursor.fetchall()

    if profiles:
        markup = types.InlineKeyboardMarkup()
        for profile in profiles:
            markup.add(types.InlineKeyboardButton(f"Удалить {profile[1]} {profile[2]}", callback_data=f"delete_{profile[0]}"))
        bot.send_message(message.chat.id, "Выберите анкету для удаления:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Анкеты не найдены.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def delete_profile_callback(call):
    profile_id = int(call.data.split('_')[1])
    cursor.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
    conn.commit()
    bot.send_message(call.message.chat.id, "Анкета удалена.")
    show_menu(call.message.chat.id, is_admin=True)

# Функция поиска анкеты
# Функция поиска анкеты
@bot.message_handler(func=lambda message: message.text == 'Поиск анкеты')
def search_profile_handler(message):
    bot.send_message(message.chat.id, "Введите ключевые слова для поиска (ФИО, телефон и т.д.):")
    bot.register_next_step_handler(message, process_profile_search)

def process_profile_search(message):
    search_criteria = message.text.split()
    
    # Строим запрос на поиск анкет по введенным критериям
    query = "SELECT * FROM profiles WHERE " + " OR ".join([
        "first_name LIKE ?",
        "last_name LIKE ?",
        "phone LIKE ?",
        "params LIKE ?",
        "visit_date LIKE ?"
    ])
    
    # Генерируем список поисковых терминов
    search_terms = [f"%{term}%" for term in search_criteria for _ in range(5)]
    
    # Выполняем запрос в базу данных
    cursor.execute(query, search_terms)
    profiles = cursor.fetchall()

    # Проверяем, найдены ли анкеты
    if profiles:
        for profile in profiles:
            profile_info = (
                f"Имя: {profile[1]}\n"
                f"Фамилия: {profile[2]}\n"
                f"Телефон: {profile[3]}\n"
                f"Параметры: {profile[4]}\n"
                f"Дата посещения: {profile[5]}\n"
                f"Комментарии: {profile[9]}"
            )
            
            # Отправляем первую фотографию, если она есть
            if profile[7]:  # Если есть первая фотография
                bot.send_photo(message.chat.id, open(profile[7], 'rb'))

            # Отправляем вторую фотографию, если она есть
            if profile[8]:  # Если есть вторая фотография
                bot.send_photo(message.chat.id, open(profile[8], 'rb'))

            # Отправляем информацию об анкете
            bot.send_message(message.chat.id, profile_info)
            
            # Добавляем проверку на наличие пересланных сообщений
            cursor.execute("SELECT forwarded_text FROM forwarded_texts WHERE profile_id = ?", (profile[0],))
            forwarded_texts = cursor.fetchall()

            if forwarded_texts:
                # Выводим пересланные сообщения одно за другим
                for forwarded_text in forwarded_texts:
                    bot.send_message(message.chat.id, f"Дополнительная информация:\n{forwarded_text[0]}")
            else:
                bot.send_message(message.chat.id, "Дополнительной информации к анкете нет.")
            
            # Создаем клавиатуру с опциями для редактирования и удаления анкеты
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"Редактировать {profile[1]} {profile[2]}", callback_data=f"edit_{profile[0]}"))
            markup.add(types.InlineKeyboardButton(f"Добавить комментарий {profile[1]} {profile[2]}", callback_data=f"comment_{profile[0]}"))
            markup.add(types.InlineKeyboardButton(f"Удалить {profile[1]} {profile[2]}", callback_data=f"delete_{profile[0]}"))
            markup.add(types.InlineKeyboardButton(f"Выход в главное меню", callback_data="go_to_main_menu"))
            markup.add(types.InlineKeyboardButton(f"Добавить глаз бога {profile[1]} {profile[2]}", callback_data=f"GlasP{profile[0]}"))
            
            # Отправляем сообщение с клавиатурой для действий
            bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

    else:
        # Если анкеты не найдены, добавляем кнопку "Назад"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Назад", callback_data="go_back"))
        bot.send_message(message.chat.id, "Анкета не найдена.", reply_markup=markup)

# Обработка нажатия на кнопку "Назад"
@bot.callback_query_handler(func=lambda call: call.data == "go_back")
def go_back_to_menu(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Возврат в главное меню.")
    show_menu(call.message.chat.id, is_admin=False)  # Показываем главное меню
        # Функция для выбора анкеты и выполнения действий (редактирование, добавление комментария, удаление)
@bot.callback_query_handler(func=lambda call: call.data.startswith('select_'))
def select_profile_callback(call):
    try:
        profile_id = int(call.data.split('_')[1])
        cursor.execute("SELECT * FROM profiles WHERE id=?", (profile_id,))
        profile = cursor.fetchone()

        if profile:
            profile_info = f"Имя: {profile[1]}\nФамилия: {profile[2]}\nТелефон: {profile[3]}\nПараметры: {profile[4]}\nДата посещения: {profile[5]}\nКомментарии: {profile[8]}"
            bot.send_message(call.message.chat.id, f"Анкета выбрана:\n\n{profile_info}")

            # Добавляем кнопки для редактирования, удаления и добавления комментария
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Редактировать", callback_data=f"edit_{profile_id}"))
            markup.add(types.InlineKeyboardButton("Добавить глаз бога", callback=f"eyeGod_{profile_id}"))
            markup.add(types.InlineKeyboardButton("Добавить комментарий", callback_data=f"comment_{profile_id}"))
            markup.add(types.InlineKeyboardButton("Удалить", callback_data=f"delete_{profile_id}"))
            markup.add(types.InlineKeyboardButton("Главное меню", callback_data="main_menu"))
            bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, "Анкета не найдена.")
            show_menu(call.message.chat.id)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при выборе анкеты: {str(e)}")

# Обработка пересланного сообщения и сохранение его в базу данных
@bot.message_handler(func=lambda message: user_states.get(message.chat.id, '').startswith('GlasP') and message.forward_from)
def handle_forwarded_message(message):
    try:
        # Получаем ID анкеты, с которой связано пересланное сообщение
        profile_id = int(user_states[message.chat.id].split('_')[1])

        # Получаем текст пересланного сообщения
        forwarded_text = message.text
        if forwarded_text:
            # Сохраняем пересланный текст в базу данных
            cursor.execute('''INSERT INTO forwarded_texts (profile_id, forwarded_text) 
                              VALUES (?, ?)''', (profile_id, forwarded_text))
            conn.commit()

            bot.send_message(message.chat.id, "Дополнительная информация успешно добавлена!")
        else:
            bot.send_message(message.chat.id, "Пересланное сообщение не содержит текста.")

        # Возвращаем пользователя в главное меню
        show_menu(message.chat.id, is_admin=True)

    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")
        show_menu(message.chat.id, is_admin=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('GlasP'))
def add_eye_of_god(call):
    try:
        profile_id = int(call.data.split('GlasP')[1])
        
        # Устанавливаем состояние пользователя для ожидания пересланного сообщения
        user_states[call.message.chat.id] = f"GlasP_{profile_id}"
        
        bot.send_message(call.message.chat.id, "Пожалуйста, пересылайте текст или медиа с другого бота для сохранения.")
    
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при обработке: {str(e)}")
        show_menu(call.message.chat.id, is_admin=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith == "main_menu")
def return_to_main_menu(call):
    chat_id = call.message.chat.id
    user_state = user_states.get(chat_id)
    
    if user_state == 'admin_authenticated':
        show_menu(chat_id, is_admin=True)
    else:
        show_menu(chat_id, is_admin=False)

# Обработка удаления анкеты
@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def delete_profile_callback(call):
    try:
        profile_id = int(call.data.split('_')[1])
        cursor.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        conn.commit()
        bot.send_message(call.message.chat.id, "Анкета удалена.")
        show_menu(call.message.chat.id, is_admin=(user_states.get(call.message.chat.id) == 'admin_authenticated'))
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при удалении анкеты: {str(e)}")

# Редактирование анкеты
# Функция обработки выбора анкеты для редактирования
@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_') and not call.data.startswith('edit_field_'))
def edit_profile_callback(call):
    try:
        # Выводим данные колбэка для отладки
        
        # Разбираем идентификатор профиля
        profile_id = int(call.data.split('_')[1])
        
        # Выводим идентификатор профиля для проверки
        bot.send_message(call.message.chat.id, f"Идентификатор профиля: {profile_id}")
        
        # Отправляем кнопки для редактирования отдельных полей
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text='Редактировать Имя', callback_data=f'edit_field_first_name_{profile_id}'))
        markup.add(types.InlineKeyboardButton(text='Редактировать Фамилию', callback_data=f'edit_field_last_name_{profile_id}'))
        markup.add(types.InlineKeyboardButton(text='Редактировать Телефон', callback_data=f'edit_field_phone_{profile_id}'))
        markup.add(types.InlineKeyboardButton(text='Редактировать Параметры', callback_data=f'edit_field_params_{profile_id}'))
        markup.add(types.InlineKeyboardButton(text='Редактировать Дату посещения', callback_data=f'edit_field_visit_date_{profile_id}'))
        markup.add(types.InlineKeyboardButton(text='Редактировать Комментарий', callback_data=f'edit_field_comment_{profile_id}'))
        
        bot.send_message(call.message.chat.id, "Выберите поле для редактирования:", reply_markup=markup)
    
    except (ValueError, IndexError) as e:
        # Выводим информацию об ошибке для отладки
        bot.send_message(call.message.chat.id, f"Ошибка при выборе анкеты: {str(e)}. Данные колбэка: {call.data}")

# Обработчик кнопок для редактирования полей анкеты
# Обработчик кнопок для редактирования полей анкеты
@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_field_'))
def edit_field_callback(call):
    try:
        # Разбираем данные колбэка
        data_parts = call.data.split('_')

        # Соединяем все части, относящиеся к полю, кроме последней (она должна быть ID)
        field = '_'.join(data_parts[2:-1])
        profile_id = int(data_parts[-1])  # Последняя часть — это ID профиля

        # Подсказки для каждого поля
        field_prompts = {
            'first_name': 'Введите новое имя:',
            'last_name': 'Введите новую фамилию:',
            'phone': 'Введите новый телефон:',
            'params': 'Введите новые параметры:',
            'visit_date': 'Введите новую дату посещения:',
            'comment': 'Введите новый комментарий:'
        }

        # Проверяем, есть ли такое поле в словаре
        if field in field_prompts:
            # Если поле существует, отправляем подсказку
            bot.send_message(call.message.chat.id, field_prompts[field])
            bot.register_next_step_handler(call.message, lambda msg: update_field(msg, profile_id, field))
        else:
            # Если поле некорректное, выводим сообщение об ошибке
            bot.send_message(call.message.chat.id, f"Некорректное поле для редактирования: {field}")

    except (ValueError, IndexError) as e:
        # Обработка ошибок с выводом сообщения об ошибке
        bot.send_message(call.message.chat.id, f"Ошибка при выборе поля. Пожалуйста, попробуйте ещё раз.")

# Функция обновления отдельного поля анкеты
def update_field(message, profile_id, field):
    new_value = message.text

    try:
        if field == 'phone' and not validate_phone(new_value):
            bot.send_message(message.chat.id, "Неверный формат телефона! Попробуйте снова.")
            return
        
        # Обновляем соответствующее поле в базе данных
        cursor.execute(f"UPDATE profiles SET {field} = ? WHERE id = ?", (new_value, profile_id))
        conn.commit()
        
        bot.send_message(message.chat.id, f" успешно обновлено!")
        show_menu(message.chat.id)

    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка при обновлении поля {field}: {str(e)}")
        show_menu(message.chat.id)

# Пример валидации телефона (можно расширить по необходимости)
def validate_phone(phone):
    # Простая валидация: номер должен начинаться с +7 или 8 и содержать только цифры
    return (phone.startswith('+7') or phone.startswith('8')) and phone[1:].isdigit()
        
# Обработка удаления анкеты
@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def delete_profile_callback(call):
    profile_id = int(call.data.split('_')[1])
    cursor.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
    conn.commit()
    bot.send_message(call.message.chat.id, "Анкета удалена.")
    show_menu(call.message.chat.id, is_admin=(user_states.get(call.message.chat.id) == 'admin_authenticated'))
    

@bot.callback_query_handler(func=lambda call: call.data == 'go_to_main_menu')
def go_to_main_menu_callback(call):
    bot.send_message(call.message.chat.id, "Возвращаюсь в главное меню...")
    show_menu(call.message.chat.id, is_admin=True)  # Передаем информацию о том, админ ли пользователь

@bot.callback_query_handler(func=lambda call: call.data.startswith("comment_"))
def handle_add_comment(call):
    profile_id = call.data.split("_")[1]  # Извлекаем ID профиля
    bot.send_message(call.message.chat.id, "Введите новый комментарий:")
    
    # Передаем profile_id в следующий шаг
    bot.register_next_step_handler(call.message, process_comment, profile_id)

def process_comment(message, profile_id):
    comment = message.text
    user_id = message.from_user.id
    is_admin = user_id == ADMIN_IDS

    # Добавляем комментарий в таблицу comments
    cursor.execute("INSERT INTO comments (profile_id, user_id, comment, is_admin) VALUES (?, ?, ?, ?)", 
                   (profile_id, user_id, comment, is_admin))
    conn.commit()

    # Получаем уже существующий комментарий в профиле (если он есть)
    cursor.execute("SELECT comment FROM profiles WHERE id=?", (profile_id,))
    existing_comment = cursor.fetchone()[0]

    # Если нет существующих комментариев, создаем пустую строку
    if existing_comment is None:
        existing_comment = ""

    # Добавляем новый комментарий к существующим
    updated_comment = existing_comment + "\n" + comment

    # Обновляем поле комментария в таблице profiles
    cursor.execute("UPDATE profiles SET comment=? WHERE id=?", (updated_comment, profile_id))
    conn.commit()

    bot.send_message(message.chat.id, "Комментарий успешно добавлен!")

    # Возвращаем пользователя в главное меню
    show_menu(message.chat.id, is_admin=(user_states.get(message.chat.id) == 'admin_authenticated'))

# Функция для редактирования комментария
# Функция для редактирования комментария
@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_comment_"))
def handle_edit_comment(call):
    profile_id = call.data.split("_")[2]  # Извлекаем ID профиля

    # Запрашиваем новый комментарий
    msg = bot.send_message(call.message.chat.id, "Введите новый комментарий:")
    
    # Сохраняем состояние для дальнейшей обработки, передаем ID профиля
    bot.register_next_step_handler(msg, process_edit_comment, profile_id)

def process_edit_comment(message, profile_id):
    new_comment = message.text  # Новый комментарий
    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором
    is_admin = (user_id == ADMIN_IDS)

    # Обновляем комментарий в таблице comments (если она есть)
    cursor.execute("UPDATE comments SET comment=? WHERE profile_id=? AND user_id=?", 
                   (new_comment, profile_id, user_id))
    
    # Обновляем комментарий в профиле
    cursor.execute("UPDATE profiles SET comment=? WHERE id=?", (new_comment, profile_id))
    conn.commit()

    bot.send_message(message.chat.id, "Комментарий успешно обновлен.")
    
    # Показываем главное меню, если пользователь администратор
    if is_admin:
        show_menu(message.chat.id, is_admin=True)
    else:
        show_menu(message.chat.id)
    # Функция для удаления комментария
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_comment_"))
def handle_delete_comment(call):
    profile_id = call.data.split("_")[2]  # Извлекаем ID профиля
    user_id = call.from_user.id

    # Удаляем комментарий из таблицы comments (если она используется)
    cursor.execute("DELETE FROM comments WHERE profile_id=? AND user_id=?", (profile_id, user_id))

    # Очищаем поле комментария в профиле
    cursor.execute("UPDATE profiles SET comment=NULL WHERE id=?", (profile_id,))
    conn.commit()

    bot.send_message(call.message.chat.id, "Комментарий удален.")
    show_menu(call.message.chat.id, is_admin=(user_states.get(call.message.chat.id) == 'admin_authenticated'))

# Функция для выхода
@bot.message_handler(func=lambda message: message.text == 'Выход')
def exit_handler(message):
    bot.send_message(message.chat.id, "До свидания!")
    user_states.pop(message.chat.id, None)

# Запуск бота
bot.polling(none_stop=True)