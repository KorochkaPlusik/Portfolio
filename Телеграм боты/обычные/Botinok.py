import sqlite3
import logging
from datetime import datetime, date
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ====== Настройки и константы ======
API_TOKEN     = '8076421586:AAHOfzXV87qtFoyMn_jLQaw4Nhf7DPDc4Ec'
MAIN_ADMIN_ID = 794991817  # замените на настоящий user_id главного администратора
TZ            = pytz.timezone('Europe/Moscow')

BOT_DB        = 'bot.db'
TODO_DB       = 'todo.db'

# Поля анкеты
FIELDS = [
    'name', 'surname', 'age', 'position',
    'phone', 'salary', 'pay_date',
    'sign_date', 'bank', 'comment'
]

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(API_TOKEN)

# хранит текущее состояние пользователя
user_state = {}  # user_id -> dict

# ====== Инициализация баз ======
def init_db():
    # основная БД для анкет и админов
    con = sqlite3.connect(BOT_DB)
    cur = con.cursor()
    cur.execute('''
      CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        photo_file_id TEXT,
        name TEXT, surname TEXT, age INTEGER,
        position TEXT, phone TEXT, salary REAL,
        pay_date TEXT, sign_date TEXT,
        bank TEXT, comment TEXT
      );
    ''')
    cur.execute('''
      CREATE TABLE IF NOT EXISTS admin_requests (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        status TEXT  -- 'pending', 'approved', 'rejected'
      );
    ''')
    cur.execute('''
      INSERT OR IGNORE INTO admin_requests(user_id, name, status)
      VALUES (?, ?, 'approved')
    ''', (MAIN_ADMIN_ID, 'Главный Админ'))
    con.commit()
    con.close()

    # БД для специальностей и дел
    tcon = sqlite3.connect(TODO_DB)
    tcur = tcon.cursor()
    tcur.execute('''
      CREATE TABLE IF NOT EXISTS specialties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL
      );
    ''')
    tcur.execute('''
      CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        spec_id INTEGER,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(spec_id) REFERENCES specialties(id)
      );
    ''')
    tcon.commit()
    tcon.close()

def is_admin(user_id: int) -> bool:
    con = sqlite3.connect(BOT_DB)
    cur = con.cursor()
    cur.execute("SELECT status FROM admin_requests WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    con.close()
    return bool(row and row[0] == 'approved')

# ====== Меню ======
def send_main_menu(chat_id):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Добавить анкету", callback_data="add"),
            InlineKeyboardButton("Редактировать анкету", callback_data="edit")
        ],
        [
            InlineKeyboardButton("Поиск анкет", callback_data="search"),
            InlineKeyboardButton("Подать заявку на админа", callback_data="become_admin")
        ],
        [
            InlineKeyboardButton("Список дел", callback_data="todo")
        ]
    ])
    bot.send_message(chat_id, "👋 Главное меню:", reply_markup=kb)

def send_todo_menu(chat_id):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить задачу", callback_data="todo_add")],
        [InlineKeyboardButton("Показать задачи", callback_data="todo_list")],
        [InlineKeyboardButton("Добавить специальность", callback_data="spec_add")],
        [InlineKeyboardButton("Выбрать специальность", callback_data="spec_list")],
        [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
    ])
    bot.send_message(chat_id, "📋 Меню списка дел:", reply_markup=kb)

# ====== Ежедневное уведомление ======
def daily_check():
    today = date.today().strftime('%Y-%m-%d')
    con = sqlite3.connect(BOT_DB)
    cur = con.cursor()
    cur.execute("SELECT id, name, surname FROM profiles WHERE pay_date=?", (today,))
    rows = cur.fetchall()
    if rows:
        text = "💰 Анкеты с выплатой сегодня:\n" + "\n".join(f"ID={r[0]} {r[1]} {r[2]}" for r in rows)
        cur.execute("SELECT user_id FROM admin_requests WHERE status='approved'")
        admins = [r[0] for r in cur.fetchall()]
        for aid in admins:
            try:
                bot.send_message(aid, text)
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление {aid}: {e}")
    con.close()

# ====== Обработчики команд ======
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    send_main_menu(msg.chat.id)

@bot.message_handler(commands=['become_admin'])
def cmd_become_admin(msg):
    uid = msg.from_user.id
    name = msg.from_user.full_name
    con = sqlite3.connect(BOT_DB)
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO admin_requests(user_id, name, status) VALUES (?, ?, 'pending')",
        (uid, name)
    )
    con.commit(); con.close()
    bot.send_message(uid, "✅ Заявка отправлена. Ожидайте решения.")
    # уведомим текущих админов
    con = sqlite3.connect(BOT_DB)
    cur = con.cursor()
    cur.execute("SELECT user_id FROM admin_requests WHERE status='approved' AND user_id!=?", (uid,))
    for (aid,) in cur.fetchall():
        bot.send_message(aid,
            f"📢 Новая заявка от {name} (ID={uid}).\nОдобрить: /approve_{uid}\nОтклонить: /reject_{uid}"
        )
    con.close()

@bot.message_handler(regexp=r'^/approve_(\d+)$')
def cmd_approve(msg):
    if not is_admin(msg.from_user.id): return
    target = int(msg.text.split('_',1)[1])
    con = sqlite3.connect(BOT_DB); cur = con.cursor()
    cur.execute("UPDATE admin_requests SET status='approved' WHERE user_id=?", (target,))
    con.commit(); con.close()
    bot.send_message(target, "✅ Ваша заявка одобрена.")
    bot.reply_to(msg, f"Пользователь {target} теперь админ.")

@bot.message_handler(regexp=r'^/reject_(\d+)$')
def cmd_reject(msg):
    if not is_admin(msg.from_user.id): return
    target = int(msg.text.split('_',1)[1])
    con = sqlite3.connect(BOT_DB); cur = con.cursor()
    cur.execute("UPDATE admin_requests SET status='rejected' WHERE user_id=?", (target,))
    con.commit(); con.close()
    bot.send_message(target, "❌ Ваша заявка отклонена.")
    bot.reply_to(msg, f"Пользователь {target} отклонён.")

# ====== Главное меню: inline-кнопки ======
@bot.callback_query_handler(func=lambda cq: cq.data in (
    "main_menu","add","edit","search","become_admin","todo"
))
def menu_callback(cq):
    bot.answer_callback_query(cq.id)
    user_id = cq.from_user.id
    chat_id = cq.message.chat.id

    if cq.data == "main_menu":
        send_main_menu(chat_id)

    elif cq.data == "todo":
        send_todo_menu(chat_id)

    elif cq.data == "add":
        if not is_admin(user_id):
            bot.send_message(chat_id, "🚫 Только администратор может добавлять анкеты.")
            return
        user_state[user_id] = {'action': 'adding', 'data': {}, 'field_idx': -1}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="main_menu")]])
        bot.send_message(chat_id, "📸 Отправьте фото анкеты.", reply_markup=kb)

    elif cq.data == "edit":
        if not is_admin(user_id):
            bot.send_message(chat_id, "🚫 Только администратор может редактировать анкеты.")
            return
        user_state[user_id] = {'action': 'editing', 'step': 'await_id'}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="main_menu")]])
        bot.send_message(chat_id, "Введите ID анкеты для редактирования:", reply_markup=kb)

    elif cq.data == "search":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="main_menu")]])
        bot.send_message(chat_id,
            "Введите критерии поиска (поле=значение через пробел).\n"
            "Поля: " + ', '.join(FIELDS),
            reply_markup=kb
        )
        user_state[user_id] = {'action': 'search'}

    elif cq.data == "become_admin":
        fake = cq.message
        fake.from_user = cq.from_user
        cmd_become_admin(fake)

# ====== Обработчик списка дел и спец. ======
@bot.callback_query_handler(func=lambda cq: cq.data in (
    "todo_add","todo_list","todo_cancel","spec_add","spec_list"
))
def callback_todo(cq):
    bot.answer_callback_query(cq.id)
    uid = cq.from_user.id
    chat_id = cq.message.chat.id

    if cq.data == "todo_add":
        # инициируем выбор специальности
        bot.send_message(chat_id, "Пожалуйста, выберите специальность:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Выбрать специальность", callback_data="spec_list")],
            [InlineKeyboardButton("Отмена", callback_data="todo_cancel")]
        ]))
        return

    if cq.data == "todo_list":
        tcon = sqlite3.connect(TODO_DB); tcur = tcon.cursor()
        tcur.execute("""
            SELECT t.id, COALESCE(s.name,'Без категории'), t.description, t.created_at, t.completed
            FROM todos t
            LEFT JOIN specialties s ON t.spec_id = s.id
            WHERE t.user_id=?
            ORDER BY t.created_at DESC
        """, (uid,))
        rows = tcur.fetchall(); tcon.close()
        if not rows:
            bot.send_message(chat_id, "✅ У вас пока нет задач.")
        else:
            text = "\n".join(
                f"{r[0]}. [{'✔' if r[4] else ' '}] [{r[3]}] ({r[1]}) {r[2]}"
                for r in rows
            )
            bot.send_message(chat_id, text)
        send_todo_menu(chat_id)
        return

    if cq.data == "spec_add":
        user_state[uid] = {'action': 'spec_adding'}
        bot.send_message(chat_id, "✏️ Введите название новой специальности:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Отмена", callback_data="todo_cancel")]
        ]))
        return

    if cq.data == "spec_list":
        tcon = sqlite3.connect(TODO_DB); tcur = tcon.cursor()
        tcur.execute("SELECT id, name FROM specialties WHERE user_id=?", (uid,))
        specs = tcur.fetchall(); tcon.close()
        if not specs:
            bot.send_message(chat_id, "ℹ️ У вас нет специальностей. Добавьте через «Добавить специальность».")
            send_todo_menu(chat_id)
            return
        kb = InlineKeyboardMarkup()
        for sid, name in specs:
            kb.add(InlineKeyboardButton(name, callback_data=f"spec|{sid}"))
        kb.add(InlineKeyboardButton("Главное меню", callback_data="main_menu"))
        bot.send_message(chat_id, "📂 Выберите специальность:", reply_markup=kb)
        return

    if cq.data == "todo_cancel":
        user_state.pop(uid, None)
        send_todo_menu(chat_id)
        return

# ====== Добавление специальности ======
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get('action') == 'spec_adding')
def handle_spec_add(msg):
    uid  = msg.from_user.id
    name = msg.text.strip()
    tcon = sqlite3.connect(TODO_DB); tcur = tcon.cursor()
    tcur.execute("INSERT INTO specialties(user_id, name) VALUES (?, ?)", (uid, name))
    tcon.commit(); tcon.close()
    bot.send_message(msg.chat.id, f"✅ Специальность «{name}» добавлена.")
    # показать список спец. для показа кнопок
    callback = telebot.types.CallbackQuery()
    callback.from_user = msg.from_user
    callback.message = msg
    callback.data = "spec_list"
    callback_todo(callback)

# ====== Выбор специальности ======
@bot.callback_query_handler(func=lambda cq: cq.data.startswith('spec|'))
def callback_select_spec(cq):
    bot.answer_callback_query(cq.id)
    uid = cq.from_user.id
    chat_id = cq.message.chat.id
    spec_id = int(cq.data.split('|',1)[1])
    tcon = sqlite3.connect(TODO_DB); tcur = tcon.cursor()
    tcur.execute("SELECT name FROM specialties WHERE id=?", (spec_id,))
    name = tcur.fetchone()[0]
    tcon.close()
    user_state[uid] = {'action': 'todo_adding', 'spec_id': spec_id}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="todo_cancel")]])
    bot.send_message(chat_id, f"✏️ Введите описание задачи для «{name}»:", reply_markup=kb)

# ====== Добавление задачи ======
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get('action') == 'todo_adding')
def handle_todo_add(msg):
    uid  = msg.from_user.id
    desc = msg.text.strip()
    spec_id = user_state[uid].get('spec_id')
    now = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
    tcon = sqlite3.connect(TODO_DB); tcur = tcon.cursor()
    tcur.execute(
        "INSERT INTO todos(user_id, spec_id, description, created_at) VALUES (?, ?, ?, ?)",
        (uid, spec_id, desc, now)
    )
    tcon.commit(); tcon.close()
    bot.send_message(msg.chat.id, "✅ Задача добавлена.")
    user_state.pop(uid, None)
    send_todo_menu(msg.chat.id)

# ====== Добавление анкеты ======
@bot.message_handler(content_types=['photo'])
def handle_photo(msg):
    uid = msg.from_user.id
    state = user_state.get(uid)
    if not state or state.get('action') != 'adding':
        return
    state['data']['photo_file_id'] = msg.photo[-1].file_id
    state['field_idx'] = 0
    field = FIELDS[0]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="main_menu")]])
    bot.send_message(uid, f"Введите {field.replace('_',' ')}:", reply_markup=kb)

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get('action') == 'adding')
def handle_add_fields(msg):
    uid = msg.from_user.id
    state = user_state[uid]
    idx = state['field_idx']
    state['data'][FIELDS[idx]] = msg.text.strip()
    idx += 1
    if idx < len(FIELDS):
        state['field_idx'] = idx
        field = FIELDS[idx]
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="main_menu")]])
        bot.send_message(uid, f"Введите {field.replace('_',' ')}:", reply_markup=kb)
    else:
        # сохраняем в БД
        vals = [ state['data'][f] for f in FIELDS ]
        vals.insert(0, state['data']['photo_file_id'])
        con = sqlite3.connect(BOT_DB); cur = con.cursor()
        placeholders = ','.join('?' for _ in range(len(FIELDS)+1))
        columns = 'photo_file_id,' + ','.join(FIELDS)
        cur.execute(f"INSERT INTO profiles({columns}) VALUES({placeholders})", vals)
        con.commit(); con.close()
        bot.send_message(uid, "✅ Анкета сохранена.")
        user_state.pop(uid, None)
        send_main_menu(uid)

# ====== Редактирование анкеты ======
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get('action') == 'editing'
                                 and user_state[m.from_user.id]['step'] == 'await_id')
def handle_edit_id(msg):
    uid = msg.from_user.id
    pid = msg.text.strip()
    con = sqlite3.connect(BOT_DB); cur = con.cursor()
    cur.execute("SELECT id FROM profiles WHERE id=?", (pid,))
    if not cur.fetchone():
        bot.send_message(uid, "❌ Анкета не найдена.")
        con.close()
        return
    con.close()
    user_state[uid].update({'profile_id': pid, 'step': 'choose_field'})
    kb = InlineKeyboardMarkup([
        *[[InlineKeyboardButton(f.replace('_',' '), callback_data=f"edit|{f}|{pid}")] for f in FIELDS],
        [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
    ])
    bot.send_message(uid, "Выберите поле для редактирования:", reply_markup=kb)

@bot.callback_query_handler(func=lambda cq: cq.data.startswith('edit|'))
def callback_edit_field(cq):
    bot.answer_callback_query(cq.id)
    _, field, pid = cq.data.split('|')
    uid = cq.from_user.id
    user_state[uid] = {'action': 'editing', 'profile_id': pid, 'field': field, 'step': 'await_value'}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="main_menu")]])
    bot.send_message(uid, f"Введите новое значение для {field.replace('_',' ')}:", reply_markup=kb)

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get('action') == 'editing'
                                 and user_state[m.from_user.id]['step'] == 'await_value')
def handle_edit_value(msg):
    uid = msg.from_user.id
    state = user_state[uid]
    field = state['field']
    pid   = state['profile_id']
    new_val = msg.text.strip()
    con = sqlite3.connect(BOT_DB); cur = con.cursor()
    cur.execute(f"UPDATE profiles SET {field}=? WHERE id=?", (new_val, pid))
    con.commit(); con.close()
    bot.send_message(uid, "✅ Поле обновлено.")
    user_state.pop(uid, None)
    send_main_menu(uid)

# ====== Поиск анкеты ======
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get('action') == 'search')
def handle_search(msg):
    text = msg.text.strip()
    tokens = text.split()
    clauses, vals = [], []
    for tok in tokens:
        if '=' in tok:
            f, v = tok.split('=', 1)
            if f in FIELDS:
                clauses.append(f"{f} LIKE ?")
                vals.append(f"%{v}%")
                continue
        sub = []
        for f in ['name','surname','age','position','phone','salary','pay_date']:
            sub.append(f"{f} LIKE ?")
            vals.append(f"%{tok}%")
        clauses.append("(" + " OR ".join(sub) + ")")
    if not clauses:
        bot.send_message(msg.chat.id, "❌ Нечего искать.")
        return
    query = "SELECT id, name, surname FROM profiles WHERE " + " AND ".join(clauses)
    con = sqlite3.connect(BOT_DB); cur = con.cursor()
    cur.execute(query, vals)
    rows = cur.fetchall(); con.close()
    if not rows:
        bot.send_message(msg.chat.id, "🔍 Ничего не найдено.")
    else:
        for pid, name, surname in rows:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Развернуть", callback_data=f"show|{pid}")],
                [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
            ])
            bot.send_message(msg.chat.id, f"ID={pid}: {name} {surname}", reply_markup=kb)
    user_state.pop(msg.from_user.id, None)

@bot.callback_query_handler(func=lambda cq: cq.data.startswith('show|'))
def callback_show_profile(cq):
    bot.answer_callback_query(cq.id)
    pid = cq.data.split('|',1)[1]
    con = sqlite3.connect(BOT_DB); cur = con.cursor()
    cur.execute("SELECT * FROM profiles WHERE id=?", (pid,))
    row = cur.fetchone(); con.close()
    if not row:
        bot.send_message(cq.message.chat.id, "❌ Анкета не найдена.")
        return
    _, photo_id, name, surname, age, position, phone, salary, pay_date, sign_date, bank, comment = row
    caption = (
        f"🆔 ID: {pid}\n"
        f"👤 Имя: {name}\n"
        f"👥 Фамилия: {surname}\n"
        f"🎂 Возраст: {age}\n"
        f"💼 Должность: {position}\n"
        f"📞 Телефон: {phone}\n"
        f"💰 Зарплата: {salary}\n"
        f"📅 Дата выдачи ЗП: {pay_date}\n"
        f"✍️ Дата подписания: {sign_date}\n"
        f"🏦 Банк: {bank}\n"
        f"📝 Комментарий: {comment}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Главное меню", callback_data="main_menu")]])
    bot.send_photo(cq.message.chat.id, photo_id, caption=caption, reply_markup=kb)

# ====== Запуск бота ======
if __name__ == '__main__':
    init_db()
    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(daily_check, 'cron', hour=9, minute=0)
    scheduler.start()
    bot.infinity_polling()
