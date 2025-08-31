import telebot
import sqlite3
from telebot import types

# Токен вашего бота
API_TOKEN = '6086015096:AAHPz5xlR7kdoDN-GXhPNIJeFydbMn2m-Es'  # Замените на свой токен
bot = telebot.TeleBot(API_TOKEN)

# Подключение к базе данных
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц для хранения пользователей, постов и комментариев
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    password TEXT,
    is_admin BOOLEAN
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo TEXT,
    text TEXT,
    position INTEGER
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER,
    user_id INTEGER,
    comment TEXT
)''')

conn.commit()

# Пароли и администраторский ID
ADMIN_ID = 794991817  # Замените на ваш ID администратора
admin_password = "Adme"
user_passwords = {
    111111111: "useme1",
    222222222: "useme2",
    333333333: "useme3"
}

# Хранение состояний пользователей
user_states = {}

# Функция для показа меню
def show_menu(chat_id, is_admin=False):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    if is_admin:
        markup.add('Добавить пост', 'Показать посты', 'Редактировать посты', 'Удалить пост', 'Переместить пост', 'Выход')
    else:
        markup.add('Показать посты', 'Добавить комментарий', 'Выход')
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

# Проверка пароля
@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "Привет! Введите пароль для доступа.")
    user_states[message.chat.id] = 'awaiting_password'

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_password')
def password_handler(message):
    user_id = message.from_user.id
    entered_password = message.text

    # Проверка на администратора
    if user_id == ADMIN_ID and entered_password == admin_password:
        bot.send_message(message.chat.id, "Пароль администратора верный! Добро пожаловать.")
        user_states[message.chat.id] = 'admin_authenticated'
        show_menu(message.chat.id, is_admin=True)
        return

    # Проверка на обычного пользователя
    if user_passwords.get(user_id) == entered_password:
        bot.send_message(message.chat.id, "Пароль верный! Добро пожаловать.")
        user_states[message.chat.id] = 'user_authenticated'
        show_menu(message.chat.id, is_admin=False)
    else:
        bot.send_message(message.chat.id, "Неверный пароль! Попробуйте снова.")
        user_states[message.chat.id] = 'awaiting_password'

# Обработчик добавления поста (только для админа)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Добавить пост')
def add_post_handler(message):
    msg = bot.send_message(message.chat.id, "Отправьте фото и текст.")
    bot.register_next_step_handler(msg, process_photo_and_text)

def process_photo_and_text(message):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        photo_path = f"photos/{message.photo[-1].file_id}.jpg"

        with open(photo_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        caption = message.caption or ''
        cursor.execute("INSERT INTO posts (user_id, photo, text, position) VALUES (?, ?, ?, ?)", 
                       (message.from_user.id, photo_path, caption, 0))  # Позиция по умолчанию
        conn.commit()
        
        bot.send_message(message.chat.id, "Фото и текст успешно сохранены!")
        show_menu(message.chat.id, is_admin=True)
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
        # Обработчик для показа постов
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Показать посты')
def show_posts_handler(message):
    cursor.execute("SELECT * FROM posts ORDER BY position ASC")
    posts = cursor.fetchall()
    if posts:
        for post in posts:
            bot.send_photo(message.chat.id, open(post[2], 'rb'), caption=post[3])
    else:
        bot.send_message(message.chat.id, "Постов нет.")

# Обработчик для редактирования постов
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Редактировать посты')
def edit_posts_handler(message):
    cursor.execute("SELECT * FROM posts ORDER BY position ASC")
    posts = cursor.fetchall()
    if posts:
        markup = types.InlineKeyboardMarkup()
        for post in posts:
            markup.add(types.InlineKeyboardButton(f"Редактировать {post[0]}", callback_data=f"edit_{post[0]}"))
        bot.send_message(message.chat.id, "Выберите пост для редактирования:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "У вас нет постов.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def edit_post_callback(call):
    post_id = int(call.data.split('_')[1])
    msg = bot.send_message(call.message.chat.id, "Отправьте новый текст для поста.")
    bot.register_next_step_handler(msg, lambda message: update_post(message, post_id))

def update_post(message, post_id):
    new_text = message.text
    cursor.execute("UPDATE posts SET text=? WHERE id=?", (new_text, post_id))
    conn.commit()
    bot.send_message(message.chat.id, "Пост успешно обновлен.")

# Обработчик для удаления постов
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Удалить пост')
def delete_post_handler(message):
    cursor.execute("SELECT * FROM posts ORDER BY position ASC")
    posts = cursor.fetchall()
    if posts:
        markup = types.InlineKeyboardMarkup()
        for post in posts:
            markup.add(types.InlineKeyboardButton(f"Удалить {post[0]}", callback_data=f"delete_{post[0]}"))
        bot.send_message(message.chat.id, "Выберите пост для удаления:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "У вас нет постов.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def delete_post_callback(call):
    post_id = int(call.data.split('_')[1])
    cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()
    bot.send_message(call.message.chat.id, f"Пост {post_id} удален.")

# Обработчик для перемещения постов
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'admin_authenticated' and message.text == 'Переместить пост')
def move_post_handler(message):
    cursor.execute("SELECT * FROM posts ORDER BY position ASC")
    posts = cursor.fetchall()
    if posts:
        markup = types.InlineKeyboardMarkup()
        for post in posts:
            markup.add(types.InlineKeyboardButton(f"Вверх {post[0]}", callback_data=f"move_up_{post[0]}"))
            markup.add(types.InlineKeyboardButton(f"Вниз {post[0]}", callback_data=f"move_down_{post[0]}"))
        bot.send_message(message.chat.id, "Выберите пост для перемещения:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "У вас нет постов.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('move_up_') or call.data.startswith('move_down_'))
def move_post_callback(call):
    post_id = int(call.data.split('_')[2])
    
    cursor.execute("SELECT position FROM posts WHERE id=?", (post_id,))
    post_data = cursor.fetchone()
    
    if post_data is None:
        bot.send_message(call.message.chat.id, "Пост не найден.")
        return
    
    current_position = post_data[0]
    if call.data.startswith('move_up_'):
        if current_position > 0:
            new_position = current_position - 1
            cursor.execute("UPDATE posts SET position=? WHERE id=?", (new_position, post_id))
            cursor.execute("UPDATE posts SET position=? WHERE position=?", (current_position, new_position))
        else:
            bot.send_message(call.message.chat.id, "Нельзя переместить пост выше.")
            return

    elif call.data.startswith('move_down_'):
        cursor.execute("SELECT MAX(position) FROM posts")
        max_position = cursor.fetchone()[0]

        if current_position < max_position:
            new_position = current_position + 1
            cursor.execute("UPDATE posts SET position=? WHERE id=?", (new_position, post_id))
            cursor.execute("UPDATE posts SET position=? WHERE position=?", (current_position, new_position))
    else:
            bot.send_message(call.message.chat.id, "Нельзя переместить пост ниже.")
            return

    conn.commit()
    bot.send_message(call.message.chat.id, f"Пост {post_id} перемещен.")

# Обработчик добавления комментариев (для пользователей)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'user_authenticated' and message.text == 'Добавить комментарий')
def add_comment_handler(message):
    cursor.execute("SELECT * FROM posts ORDER BY position ASC")
    posts = cursor.fetchall()
    if posts:
        markup = types.InlineKeyboardMarkup()
        for post in posts:
            markup.add(types.InlineKeyboardButton(f"Комментировать {post[0]}", callback_data=f"comment_{post[0]}"))
        bot.send_message(message.chat.id, "Выберите пост для комментария:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Нет доступных постов для комментариев.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('comment_'))
def comment_post_callback(call):
    post_id = int(call.data.split('_')[1])
    msg = bot.send_message(call.message.chat.id, "Введите ваш комментарий.")
    bot.register_next_step_handler(msg, lambda message: add_comment(message, post_id))

def add_comment(message, post_id):
    comment_text = message.text
    user_id = message.from_user.id
    cursor.execute("INSERT INTO comments (post_id, user_id, comment) VALUES (?, ?, ?)", 
                   (post_id, user_id, comment_text))
    conn.commit()
    bot.send_message(message.chat.id, "Комментарий успешно добавлен!")

# Обработчик для просмотра комментариев к постам
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'user_authenticated' and message.text == 'Показать посты')
def show_posts_with_comments_handler(message):
    cursor.execute("SELECT * FROM posts ORDER BY position ASC")
    posts = cursor.fetchall()
    if posts:
        for post in posts:
            bot.send_photo(message.chat.id, open(post[2], 'rb'), caption=post[3])
            cursor.execute("SELECT * FROM comments WHERE post_id=?", (post[0],))
            comments = cursor.fetchall()
            if comments:
                comment_texts = "\n".join([f"{c[2]}: {c[3]}" for c in comments])
                bot.send_message(message.chat.id, f"Комментарии:\n{comment_texts}")
            else:
                bot.send_message(message.chat.id, "Комментариев нет.")
    else:
        bot.send_message(message.chat.id, "Постов нет.")

# Обработчик для выхода
@bot.message_handler(func=lambda message: message.text == 'Выход')
def exit_handler(message):
    bot.send_message(message.chat.id, "Вы вышли из меню.")
    user_states[message.chat.id] = None

# Запуск бота
bot.polling(none_stop=True)