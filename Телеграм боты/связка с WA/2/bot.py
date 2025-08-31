# -*- coding: utf-8 -*-
import os
import threading
import time
import json
import sqlite3
import requests
import telebot
from telebot import types
import concurrent.futures
import requests
from typing import Optional, List, Dict, Tuple
import requests
from requests.exceptions import ReadTimeout, ConnectionError
from requests.exceptions import ReadTimeout, ConnectionError


# Класс-ограничитель скорости (Rate Limiter)
class RateLimiter:
    def __init__(self, calls, period):
        """
        :param calls: Максимальное число вызовов за период.
        :param period: Период в секундах.
        """
        self.calls = calls
        self.period = period
        self.lock = threading.Lock()
        self.call_times = []

    def wait(self):
        """
        Если число вызовов за последний период превышено, ждем нужное время.
        """
        with self.lock:
            now = time.time()
            # Удаляем старые вызовы, вышедшие за пределы периода
            while self.call_times and now - self.call_times[0] > self.period:
                self.call_times.pop(0)
            if len(self.call_times) >= self.calls:
                sleep_time = self.period - (now - self.call_times[0])
                time.sleep(sleep_time)
            self.call_times.append(time.time())

# Создаем глобальный ограничитель скорости:
# Например: 1 вызов в секунду (настройте по необходимости)
rate_limiter = RateLimiter(calls=5, period=1)

def limited_post(
    url: str,
    *,
    params: Optional[Dict] = None,
    data: Optional[Dict] = None,
    files: Optional[Dict] = None,
    timeout: Tuple[int, int] = (5, 36000)   # (connect, read) → 10 ч
) -> requests.Response:
    """
    POST-запрос через общую Session с рейт-лимитом.

    • rate_limiter.wait() – блокирует поток, если превышен лимит
    • timeout – кортеж (connect_timeout, read_timeout)
      5 c   → быстро обрываемся, если сервер не доступен
      36000 → ждём ответ до 10 часов
    """
    rate_limiter.wait()
    return REQUESTS_SES.post(
        url,
        params=params,
        data=data,
        files=files,
        timeout=timeout,
    )

def limited_get(
    url: str,
    *,
    params: Optional[Dict] = None,
    timeout: Tuple[int, int] = (5, 30)
) -> requests.Response:
    """GET-запрос через общую Session с рейт-лимитом."""
    rate_limiter.wait()
    return REQUESTS_SES.get(
        url,
        params=params,
        timeout=timeout,
    )

# -------------------------------------------------------------------
# NEW: для отслеживания прогресса рассылок и мониторинга зависаний
broadcast_progress: Dict[int, int] = {}  # { chat_id: messages_sent }
# -------------------------------------------------------------------


# --- Настройки бота и базы данных ---
TOKEN = "7648352866:AAHbns666v8TYvYLwFHLXrrtpJghwWkIeo4"
bot = telebot.TeleBot(TOKEN)
# ─── Авто-парсинг ───
AUTO_PARSE_ENABLED = False   # по умолчанию выключен
PARSE_INTERVAL      = 300    # интервал в секундах
_parse_timer: Optional[threading.Timer] = None  # сюда будет сохраняться threading.Timer # сюда будет сохраняться threading.Timer
# пул для фоновых задач (рассылки, скачивание фото и пр.)
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# Session с keep-alive и коротким connect-timeout
REQUESTS_SES = requests.Session()
REQUESTS_SES.headers.update({"User-Agent": "wa-mailer/1.0"})
# ——— Настройка БД для парсинга профилей ———
PROFILES_DB = "profiles_bot.db"
p_conn = sqlite3.connect(PROFILES_DB, check_same_thread=False)
p_cur  = p_conn.cursor()
p_cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id         INTEGER PRIMARY KEY,
    role            TEXT    NOT NULL,         
    applied         INTEGER DEFAULT 0,        
    current_account TEXT    DEFAULT 'default'
)
""")
p_cur.execute("""
CREATE TABLE IF NOT EXISTS profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT,
    chat_id       TEXT,
    sender        TEXT,
    content       TEXT,
    timestamp     INTEGER,
    UNIQUE(account_id, chat_id, sender, timestamp)
)
""")
# ─────────────── 1) Миграция: добавление колонки photo_path ───────────────
try:
    p_cur.execute("ALTER TABLE profiles ADD COLUMN photo_path TEXT")
    p_conn.commit()
except sqlite3.OperationalError:
    # колонка уже существует — ничего не делаем
    pass

p_cur.execute("""
CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER,
    text         TEXT,
    status       TEXT    DEFAULT 'pending',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
p_conn.commit()

DB_FILE = "lists.db"
PARSE_API           = "http://localhost:5000/api/parse/{account_id}/messages"
WHATSAPP_SERVER_URL = "http://localhost:5000/api/whatsapp"
# Укажите здесь chat_id администратора (замените на реальный ID)
ADMIN_ID = "7522950558"



# --- Инициализация базы данных ---
def init_db():
    """
    Создаёт все таблицы (если их нет) и добавляет только администратора.
    Убрана автоматическая вставка «default»-аккаунта.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.executescript(f"""
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS group_lists (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id    TEXT NOT NULL,
        list_name  TEXT NOT NULL,
        groups     TEXT NOT NULL,
        account_id INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
        chat_id TEXT PRIMARY KEY,
        role    TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS applications (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id          TEXT NOT NULL,
        application_text TEXT NOT NULL,
        status           TEXT DEFAULT 'pending',
        submitted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS accounts (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    """)
    # Если таблица users ещё без колонок applied/current_account — добавляем их
    try:
        c.execute("ALTER TABLE users ADD COLUMN applied INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN current_account TEXT")
    except sqlite3.OperationalError:
        pass
    # Регистрируем администратора
    c.execute(
        "INSERT OR IGNORE INTO users(chat_id, role) VALUES(?, 'admin')",
        (str(ADMIN_ID),)
    )
    conn.commit()
    conn.close()


init_db()


# --- Функции работы с БД ---
def add_list(chat_id, list_name, groups):
    """
    Всегда требует, чтобы пользователь заранее выбрал WhatsApp-аккаунт.
    """
    acc = get_current_account(chat_id)
    if not acc:
        raise Exception("Не выбран аккаунт WhatsApp")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO group_lists (chat_id, list_name, groups, account_id) VALUES (?, ?, ?, ?)",
        (str(chat_id), list_name, json.dumps(groups), acc)
    )
    conn.commit()
    conn.close()


def get_user(chat_id):
    """
    Возвращает кортеж (role, applied, current_account).
    Если записи нет — создаёт пользователя с ролью «user» и без account.
    current_account возвращается как None, если не задан.
    """
    p_cur.execute(
        "SELECT role, applied, current_account FROM users WHERE chat_id = ?",
        (chat_id,)
    )
    row = p_cur.fetchone()
    if not row:
        p_cur.execute(
            "INSERT INTO users(chat_id, role) VALUES (?, 'user')",
            (chat_id,)
        )
        p_conn.commit()
        return ("user", 0, None)
    role, applied, current_account = row
    if current_account in (None, "", "default"):
        current_account = None
    return (role, applied, current_account)


def set_user_account(chat_id, account_id):
    p_cur.execute(
        "UPDATE users SET current_account = ? WHERE chat_id = ?",
        (account_id, chat_id)
    )
    p_conn.commit()

_db_lock = threading.Lock()

# ─────────────── 2) Сохранение профилей в БД ───────────────
def save_profiles(account_id: int, profiles: List[Dict]) -> None:
    """
    Сохраняет профили в таблицу profiles:
    (account_id, chat_id, sender, content, timestamp, photo_path).
    Игнорирует дубли по UNIQUE(account_id, chat_id, sender, timestamp).
    """
    if not profiles:
        print("[PARSE] Нет профилей для сохранения.")
        return

    with _db_lock:
        try:
            with p_conn:  # начало транзакции
                p_conn.executemany(
                    """
                    INSERT OR IGNORE INTO profiles
                      (account_id, chat_id, sender, content, timestamp, photo_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            str(account_id),
                            str(p["chat_id"]),
                            p["sender"],
                            p["content"],
                            p["timestamp"],
                            p.get("photo_path")
                        ) for p in profiles
                    ]
                )
            print(f"[PARSE] Сохранено {len(profiles)} профилей.")
        except Exception as e:
            print(f"[PARSE] Ошибка при сохранении профилей в БД: {e}")


# ─────────────── 3) Одноразовый парсинг новых профилей ───────────────
def _do_parse_once() -> None:
    """
    Запрашивает новые сообщения из бекенда,
    скачивает фото (если есть mediaUrl → image),
    и сохраняет всё в БД через save_profiles().
    """
    # Получаем текущий аккаунт администратора
    _, _, acc_id = get_user(int(ADMIN_ID))
    if not acc_id:
        print("[PARSE] Не выбран аккаунт администратора.")
        return

    try:
        url = PARSE_API.format(account_id=acc_id)
        resp = limited_get(url, timeout=(5, 45))
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception as e:
            print(f"[PARSE] Ошибка декодирования JSON: {e}")
            return

        msgs = data.get("profiles")
        if msgs is None:
            print("[PARSE] Нет ключа 'profiles' в ответе сервера.")
            return

    except Exception as e:
        print(f"[PARSE] Ошибка HTTP-запроса: {e}")
        return

    profiles_to_save = []

    for m in msgs:
        entry = {
            "chat_id":    m["chat_id"],
            "sender":     m["sender"],
            "content":    m["content"],
            "timestamp":  m["timestamp"],
            "photo_path": None
        }

        media_url  = m.get("mediaUrl")
        media_type = m.get("mediaType", "")

        if media_url and media_type.startswith("image"):
            try:
                img_resp = limited_get(media_url, timeout=(5, 30))
                if img_resp.status_code == 200:
                    save_dir = os.path.join("server", "public", "profile_media", str(acc_id))
                    os.makedirs(save_dir, exist_ok=True)
                    filename = f"{m['sender']}_{m['timestamp']}.jpg"
                    fullpath = os.path.join(save_dir, filename)
                    with open(fullpath, "wb") as f:
                        f.write(img_resp.content)
                    entry["photo_path"] = fullpath
                else:
                    print(f"[PARSE] Ошибка загрузки изображения ({img_resp.status_code}): {media_url}")
            except Exception as ex:
                print(f"[PARSE] Ошибка загрузки {media_url}: {ex}")

        profiles_to_save.append(entry)

    if profiles_to_save:
        try:
            save_profiles(acc_id, profiles_to_save)
            bot.send_message(
                ADMIN_ID,
                f"📥 Импортировано {len(profiles_to_save)} новых профилей."
            )
        except Exception as db_e:
            print(f"[PARSE] Ошибка при сохранении в БД: {db_e}")
    else:
        print("[PARSE] Нет новых профилей для импорта.")


        
def search_profiles(account_id, keyword):
    like_kw = f"%{keyword}%"
    p_cur.execute("""
        SELECT sender, content, datetime(timestamp, 'unixepoch','localtime') AS ts
          FROM profiles
         WHERE account_id = ? AND content LIKE ?
         ORDER BY timestamp DESC
         LIMIT 20
    """, (account_id, like_kw))
    return p_cur.fetchall()


def get_all_accounts() -> List[Tuple[int, str]]:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM accounts")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_lists(chat_id):
    acc = get_current_account(chat_id) or 1
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT id, list_name, groups FROM group_lists WHERE chat_id = ? AND account_id = ?",
        (str(chat_id), acc)
    )
    rows = c.fetchall()
    conn.close()

    lists_out = []
    for row in rows:
        lists_out.append({
            "id": row[0],
            "list_name": row[1],
            "groups": json.loads(row[2])
        })
    return lists_out

def delete_list(chat_id, list_id):
    acc = get_current_account(chat_id) or 1
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "DELETE FROM group_lists WHERE id = ? AND chat_id = ? AND account_id = ?",
        (list_id, str(chat_id), acc)
    )
    conn.commit()
    conn.close()


def add_user(chat_id, role="user"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (chat_id, role) VALUES (?, ?)", (str(chat_id), role))
    except sqlite3.IntegrityError:
        pass  # Пользователь уже зарегистрирован
    conn.commit()
    conn.close()

def is_registered(chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE chat_id = ?", (str(chat_id),))
    result = c.fetchone()
    conn.close()
    return bool(result)

def add_application(chat_id, application_text):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Status установится автоматически в "pending"
    c.execute("INSERT INTO applications (chat_id, application_text) VALUES (?, ?)",
              (str(chat_id), application_text))
    conn.commit()
    conn.close()

def get_applications():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Возвращаем только заявки со статусом "pending"
    c.execute("SELECT id, chat_id, application_text, submitted_at FROM applications WHERE status='pending'")
    rows = c.fetchall()
    conn.close()
    apps = []
    for row in rows:
        apps.append({
            "id": row[0],
            "chat_id": row[1],
            "application_text": row[2],
            "submitted_at": row[3]
        })
    return apps

def update_application_status(app_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
    conn.commit()
    conn.close()
def get_account_name(acc_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name FROM accounts WHERE id = ?", (acc_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "unknown"

def get_current_account(chat_id):
    # Берёт текущий account_id из user_state
    return user_state.get(chat_id, {}).get("current_account")

# --- Вспомогательные функции для пагинации ---
def paginate_items(items, page, per_page=10):
    total_pages = (len(items) - 1) // per_page + 1 if items else 1
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages

def build_saved_lists_markup(lists, page=1, per_page=10, mode="select"):
    markup = types.InlineKeyboardMarkup(row_width=1)
    paginated, total_pages = paginate_items(lists, page, per_page)
    for lst in paginated:
        if mode == "select":
            btn = types.InlineKeyboardButton(text=lst["list_name"], callback_data=f"normal_list_{lst['id']}")
        else:
            btn = types.InlineKeyboardButton(text=lst["list_name"], callback_data=f"edit_list_{lst['id']}")
        markup.add(btn)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"saved_lists_page_{page-1}_{mode}"))
    nav_buttons.append(types.InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"saved_lists_page_{page+1}_{mode}"))
    if nav_buttons:
        markup.add(*nav_buttons)
    markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return markup

def build_paginated_groups_markup(groups, selected, page=1, per_page=10, prefix="list_group_", add_done_button=False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    paginated, total_pages = paginate_items(groups, page, per_page)
    for g in paginated:
        text = g.get("name", "Группа")
        group_id = g.get("id", "")
        if group_id in selected:
            text = "✅ " + text
        btn = types.InlineKeyboardButton(text=text, callback_data=f"{prefix}{group_id}")
        markup.add(btn)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"{prefix}page_{page-1}"))
    nav_buttons.append(types.InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"{prefix}page_{page+1}"))
    if nav_buttons:
        markup.add(*nav_buttons)
    if add_done_button:
        if prefix.startswith("list_group_"):
            done_callback = "list_done"
        elif prefix.startswith("timed_group_"):
            done_callback = "timed_done"
        else:
            done_callback = "done"
        markup.add(types.InlineKeyboardButton("Готово", callback_data=done_callback))
    markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return markup

def build_applications_markup(apps, page=1, per_page=10):
    markup = types.InlineKeyboardMarkup(row_width=1)
    paginated, total_pages = paginate_items(apps, page, per_page)
    for app in paginated:
        text = f"{app['chat_id']}: {app['application_text'][:20]}..."
        btn_accept = types.InlineKeyboardButton("Принять", callback_data=f"accept_{app['id']}")
        btn_decline = types.InlineKeyboardButton("Отклонить", callback_data=f"decline_{app['id']}")
        markup.add(types.InlineKeyboardButton(text=text, callback_data="noop"))
        markup.add(btn_accept, btn_decline)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"applications_page_{page-1}"))
    nav_buttons.append(types.InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"applications_page_{page+1}"))
    if nav_buttons:
        markup.add(*nav_buttons)
    markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return markup

# --- Главное меню ---
def build_main_menu(chat_id=None):
    markup = types.InlineKeyboardMarkup(row_width=3)

    if chat_id and not is_registered(chat_id):
        return markup.add(types.InlineKeyboardButton("Заявка", callback_data="apply_request"))

    # Текущий аккаунт
    if chat_id:
        acc = get_current_account(chat_id)
        if acc:
            name = get_account_name(acc)
            markup.add(
                types.InlineKeyboardButton(f"🔗 Аккаунт: {name}", callback_data="noop")
            )

    # Основные кнопки
    btn_normal = types.InlineKeyboardButton("Рассылка", callback_data="normal_choose_list")
    btn_timed  = types.InlineKeyboardButton("Таймер",   callback_data="toggle_timed")
    btn_lists  = types.InlineKeyboardButton("Списки",   callback_data="manage_lists")

    if str(chat_id) == str(ADMIN_ID):
        btn_app   = types.InlineKeyboardButton("Заявки",       callback_data="view_applications")
        parse_lbl = "⏸️ Откл. авто-парсинг" if AUTO_PARSE_ENABLED else "📥 Вкл. авто-парсинг"
        btn_parse = types.InlineKeyboardButton(parse_lbl,        callback_data="do_parse")
        btn_search= types.InlineKeyboardButton("🔍 Поиск",       callback_data="do_search")
        markup.add(btn_normal, btn_timed, btn_lists, btn_app, btn_parse, btn_search)
    else:
        btn_app = types.InlineKeyboardButton("Заявка", callback_data="apply_request")
        markup.add(btn_normal, btn_timed, btn_lists, btn_app)

    # Управление аккаунтами
    btn_switch = types.InlineKeyboardButton("🔄 Сменить аккаунт", callback_data="switch_account")
    btn_add    = types.InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account")
    btn_login  = types.InlineKeyboardButton("📲 Вход в аккаунт",   callback_data="login_menu")
    markup.add(btn_switch, btn_add, btn_login)

    return markup



# --- Пользовательское состояние ---
user_state = {}

# --- Хендлер команды /start ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    # Сохраняем прежний account, чтобы не потерять его при сбросе состояния
    prev_acc = user_state.get(chat_id, {}).get("current_account")
    user_state[chat_id] = {}
    if prev_acc is not None:
        user_state[chat_id]["current_account"] = prev_acc

    if not is_registered(chat_id):
        bot.send_message(
            chat_id,
            "Привет!\nДля использования бота необходимо подать заявку.\n"
            "Нажмите кнопку «Заявка» и отправьте её текст.",
            reply_markup=build_main_menu(chat_id)
        )
    else:
        bot.send_message(
            chat_id,
            "Привет! Выберите режим работы:",
            reply_markup=build_main_menu(chat_id)
        )


@bot.message_handler(commands=['help'])
def handle_help(message):
    bot.send_message(message.chat.id, "Доступные команды:\n/start – главное меню\n/help – помощь")

@bot.callback_query_handler(func=lambda call: call.data == "back_main")
def handle_back_main(call):
    chat_id = call.message.chat.id
    bot.edit_message_text(chat_id=chat_id,
                          message_id=call.message.message_id,
                          text="Главное меню:",
                          reply_markup=build_main_menu(chat_id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "noop")
def handle_noop(call):
    bot.answer_callback_query(call.id)

def require_registration(chat_id, call_id=None):
    if not is_registered(chat_id):
        if call_id:
            bot.answer_callback_query(call_id, "Сначала подайте заявку.")
        else:
            bot.send_message(chat_id, "Сначала подайте заявку.")
        return False
    return True

# --- Функция последовательной отправки сообщений с задержкой 5 секунд ---
# 2) Унифицированная функция для отправки сообщений через бэкенд




# =============================================================================
# Режим "Обычная рассылка" через сохранённые списки
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "normal_choose_list")
def handle_normal_choose_list(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    lists_db = get_lists(chat_id)
    if lists_db:
        markup = build_saved_lists_markup(lists_db, page=1, per_page=10, mode="select")
    else:
        bot.send_message(chat_id, "Нет сохранённых списков. Нажмите 'Добавить новый список' для создания.",
                         reply_markup=build_main_menu(chat_id))
        return
    btn_new = types.InlineKeyboardButton("Добавить новый список", callback_data="list_create")
    markup.add(btn_new)
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Выберите список для рассылки:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("normal_list_"))
def handle_normal_list_select(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    list_id = call.data.split("normal_list_")[1]
    chosen = None
    for lst in get_lists(chat_id):
        if str(lst["id"]) == list_id:
            chosen = lst
            break
    if not chosen:
        bot.answer_callback_query(call.id, "Список не найден.")
        return
    user_state.setdefault(chat_id, {})["normal"] = {"list": chosen, "awaiting_text": True, "message": "", "photo_path": None}
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text=f"Выбран список: {chosen['list_name']}\nПришлите фото (опционально) и введите текст для рассылки.",
                          reply_markup=build_main_menu(chat_id))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: (msg.chat.id in user_state and "normal" in user_state[msg.chat.id]
                                         and user_state[msg.chat.id]["normal"].get("awaiting_text", False)
                                         and not msg.text.startswith('/')), content_types=['text'])
def handle_normal_text(msg: types.Message) -> None:
    """Запуск обычной рассылки по списку групп (не блокирует основной поток)."""
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return

    st = user_state.get(chat_id, {}).get("normal")
    if not st:
        return

    # Собираем параметры рассылки
    text = msg.text
    groups: List[str] = st["list"].get("groups", [])
    photo_path: Optional[str] = st.get("photo_path")

    if not groups:
        bot.send_message(chat_id, "В выбранном списке нет групп. Возвращаемся в меню.",
                         reply_markup=build_main_menu(chat_id))
        user_state.pop(chat_id, None)
        return

    # NEW: инициализируем прогресс
    broadcast_progress[chat_id] = 0

    def send_and_report() -> None:
        ok: List[str] = []
        bad: List[str] = []
        total = len(groups)
        sent_count = 0

        # отправляем стартовое сообщение
        progress_msg = bot.send_message(chat_id, f"Отправлено 0/{total}")
        progress_msg_id = progress_msg.message_id
        update_every = 5

        for raw in groups:
            # NEW: если монитор пометил зависание — прерываемся
            if broadcast_progress.get(chat_id) == -1:
                break

            group_id = raw.split("@", 1)[0]
            try:
                files = {}
                if photo_path and os.path.exists(photo_path):
                    files['photo'] = open(photo_path, 'rb')
                resp = limited_post(
                    f"{WHATSAPP_SERVER_URL}/{get_current_account(chat_id) or 1}/send",
                    data={"chat_id": group_id, "message": text},
                    files=files
                )
                if resp.ok:
                    ok.append(group_id)
                else:
                    bad.append(f"{group_id}: HTTP {resp.status_code}")
            except Exception as e:
                bad.append(f"{group_id}: {e}")
                if broadcast_progress.get(chat_id) == -1:
                    break
            finally:
                if files.get('photo'):
                    files['photo'].close()

            sent_count += 1
            # NEW: сохраняем прогресс
            broadcast_progress[chat_id] = sent_count

            if sent_count % update_every == 0 or sent_count == total:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg_id,
                    text=f"Отправлено {sent_count}/{total}"
                )
            time.sleep(5)

        # NEW: если зависание — уведомляем и выходим
        if broadcast_progress.get(chat_id) == -1:
            bot.send_message(chat_id,
                             "⚠️ Рассылка зависла, выполнен автоматический перезапуск WhatsApp-сервера.")
            user_state.get(chat_id, {}).pop("normal", None)
            broadcast_progress.pop(chat_id, None)
            return

        # нормальный итог
        success_count = len(ok)
        error_count = len(bad)
        result_text = f"✅ Успешно: {success_count}, ❌ Ошибки: {error_count}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔁 Повторить рассылку", callback_data="repeat_broadcast"))
        bot.send_message(chat_id, result_text, reply_markup=markup)

        user_state.get(chat_id, {}).pop("normal", None)
        broadcast_progress.pop(chat_id, None)

    # запускаем рассылку
    EXECUTOR.submit(send_and_report)

    # NEW: мониторинг прогресса
    def monitor_progress(chat_id: int, total: int):
        prev = 0
        while True:
            time.sleep(30)
            current = broadcast_progress.get(chat_id)
            # если рассылка завершена — выходим
            if current is None:
                break
            # если застыло и не закончено — флаг зависания
            if current == prev and current < total:
                broadcast_progress[chat_id] = -1
                print(f"[MONITOR] Рассылка для chat {chat_id} застыла на {current}/{total}, рестарт...")
                try:
                    requests.post("http://localhost:5000/api/system/restart", timeout=5)
                except Exception as e:
                    print(f"[MONITOR] Ошибка при запросе рестарта: {e}")
                break
            prev = current

    monitor = threading.Thread(target=monitor_progress, args=(chat_id, len(groups)))
    monitor.daemon = True
    monitor.start()


@bot.message_handler(func=lambda msg: (msg.chat.id in user_state and "normal" in user_state[msg.chat.id]
                                         and user_state[msg.chat.id]["normal"].get("awaiting_text", False)
                                         and not msg.text.startswith('/')), content_types=['photo'])
def handle_normal_photo(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    file_info = bot.get_file(msg.photo[-1].file_id)
    dldir = "downloads"
    os.makedirs(dldir, exist_ok=True)
    path = os.path.join(dldir, f"{msg.photo[-1].file_id}.jpg")
    downloaded_file = bot.download_file(file_info.file_path)
    with open(path, "wb") as f:
        f.write(downloaded_file)
    user_state[chat_id]["normal"]["photo_path"] = path
    bot.send_message(chat_id, "Фото получено для обычной рассылки. Теперь введите текст сообщения.")

# =============================================================================
# Управление списками групп
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "manage_lists")
def handle_manage_lists(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_select = types.InlineKeyboardButton("Выбрать существующий список", callback_data="list_select")
    btn_create = types.InlineKeyboardButton("Добавить новый список", callback_data="list_create")
    btn_edit = types.InlineKeyboardButton("Редактировать", callback_data="list_edit")
    markup.add(btn_select, btn_create, btn_edit)
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Управление списками групп:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("saved_lists_page_"))
def handle_saved_lists_page(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    parts = call.data.split("_")
    try:
        page = int(parts[2])
        mode = parts[3]
    except Exception as e:
        bot.answer_callback_query(call.id, "Неверные данные пагинации.")
        return
    lists_db = get_lists(chat_id)
    markup = build_saved_lists_markup(lists_db, page=page, per_page=10, mode=mode)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "list_select")
def handle_list_select(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    lists_db = get_lists(chat_id)
    if not lists_db:
        bot.send_message(chat_id, "Нет сохранённых списков. Нажмите 'Добавить новый список' для создания.",
                         reply_markup=build_main_menu(chat_id))
        return
    markup = build_saved_lists_markup(lists_db, page=1, per_page=10, mode="select")
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Выберите список для рассылки:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "list_create")
def handle_list_create(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    user_state.setdefault(chat_id, {})["list_creation"] = {"awaiting_name": True}
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Введите название нового списка групп:",
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("Главное меню", callback_data="back_main")
                          ))
    bot.answer_callback_query(call.id)

from requests.exceptions import ReadTimeout, ConnectionError

@bot.message_handler(
    func=lambda msg: (
        msg.chat.id in user_state and
        "list_creation" in user_state[msg.chat.id] and
        user_state[msg.chat.id]["list_creation"].get("awaiting_name", False) and
        not msg.text.startswith('/')
    ),
    content_types=['text']
)
def handle_list_name(msg: types.Message) -> None:
    chat_id = msg.chat.id

    # 1) Подтверждаем, что пользователь может продолжать
    if not require_registration(chat_id):
        return

    # 2) Сохраняем название нового списка
    list_name = msg.text.strip()
    if not list_name:
        bot.send_message(
            chat_id,
            "❗ Название не может быть пустым. Введите корректное название:",
            reply_markup=build_main_menu(chat_id)
        )
        return

    state = user_state[chat_id]["list_creation"]
    state["list_name"]     = list_name
    state["awaiting_name"] = False

    # 3) Делаем запрос в ваш бэкенд, дольше ждём чтения ответа
    acc = get_current_account(chat_id) or 1
    url = f"{WHATSAPP_SERVER_URL}/{acc}/groups"

    try:
        # connect timeout = 5s, read timeout = 60s
        resp = limited_get(url, timeout=(5, 60))
        resp.raise_for_status()
    except ReadTimeout:
        bot.send_message(
            chat_id,
            "⌛ Сервер WhatsApp не ответил за 60 секунд. Попробуйте, пожалуйста, чуть позже.",
            reply_markup=build_main_menu(chat_id)
        )
        return
    except ConnectionError as e:
        bot.send_message(
            chat_id,
            f"❌ Не удалось соединиться с сервером WhatsApp: {e}",
            reply_markup=build_main_menu(chat_id)
        )
        return
    except Exception as e:
        bot.send_message(
            chat_id,
            f"❗ Ошибка при запросе списка групп: {e}",
            reply_markup=build_main_menu(chat_id)
        )
        return

    data = resp.json()

    # 4) Если клиент ещё не готов, просим отсканировать QR
    if data.get("status") == "pending":
        bot.send_message(
            chat_id,
            "⚠️ WhatsApp-клиент ещё не готов.\n"
            f"Отсканируйте QR-код по ссылке:\n"
            f"{WHATSAPP_SERVER_URL}/{acc}/new_account_qr?account_id={acc}",
            reply_markup=build_main_menu(chat_id)
        )
        return

    # 5) Получаем список групп
    groups = data.get("groups", [])
    if not groups:
        bot.send_message(
            chat_id,
            "ℹ️ В вашем WhatsApp-аккаунте нет ни одной группы.",
            reply_markup=build_main_menu(chat_id)
        )
        return

    # 6) Сохраняем группы в состоянии и показываем inline-клавиатуру
    state["groups"]       = groups
    state["selected"]     = []
    state["current_page"] = 1

    markup = build_paginated_groups_markup(
        groups,
        selected=[],
        page=1,
        per_page=10,
        prefix="list_group_",
        add_done_button=True
    )
    bot.send_message(
        chat_id,
        "Выберите группы для нового списка (после выбора нажмите «Готово»):",
        reply_markup=markup
    )



@bot.callback_query_handler(func=lambda call: call.data.startswith("list_group_") or call.data == "list_done")
def handle_list_group_selection(call):
    chat_id = call.message.chat.id
    state = user_state.get(chat_id, {})

    # 1) Убедимся, что мы в режиме создания списка
    if "list_creation" not in state:
        bot.answer_callback_query(call.id, "Сначала создайте новый список.")
        return

    # 2) Обработка кнопок пагинации
    if call.data.startswith("list_group_page_"):
        try:
            page = int(call.data.split("list_group_page_")[1])
        except ValueError:
            page = 1
        state["list_creation"]["current_page"] = page

        groups = state["list_creation"]["groups"]
        selected = state["list_creation"].get("selected", [])
        markup = build_paginated_groups_markup(
            groups,
            selected,
            page=page,
            per_page=10,
            prefix="list_group_",
            add_done_button=True
        )
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        return

    # 3) Нажата кнопка "Готово" — сохраняем список
    if call.data == "list_done":
        selected = state["list_creation"].get("selected", [])
        if not selected:
            bot.answer_callback_query(call.id, "Ни одна группа не выбрана.")
            return

        list_name = state["list_creation"]["list_name"]
        try:
            add_list(chat_id, list_name, selected)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"Список «{list_name}» сохранён.",
                reply_markup=build_main_menu(chat_id)
            )
        except Exception as e:
            bot.send_message(chat_id, f"Ошибка сохранения списка: {e}")

        # удаляем только состояние создания списка, но не текущий аккаунт
        user_state[chat_id].pop("list_creation", None)
        bot.answer_callback_query(call.id)
        return

    # 4) Выбор/снятие галочки у конкретной группы
    group_id = call.data.split("list_group_")[1]
    selected = state["list_creation"].setdefault("selected", [])
    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.append(group_id)

    # 5) Обновляем клавиатуру с учётом нового selected
    current_page = state["list_creation"].get("current_page", 1)
    groups = state["list_creation"]["groups"]
    markup = build_paginated_groups_markup(
        groups,
        selected,
        page=current_page,
        per_page=10,
        prefix="list_group_",
        add_done_button=True
    )
    bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)



# =============================================================================
# Режим редактирования списков (удаление)
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "list_edit")
def handle_list_edit(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    lists_db = get_lists(chat_id)
    if not lists_db:
        bot.send_message(chat_id, "Нет сохранённых списков для редактирования.", reply_markup=build_main_menu(chat_id))
        return
    markup = build_saved_lists_markup(lists_db, page=1, per_page=10, mode="edit")
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Выберите список для удаления:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_list_"))
def handle_edit_list(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    list_id = call.data.split("edit_list_")[1]
    lists_db = get_lists(chat_id)
    selected_list = next((lst for lst in lists_db if str(lst["id"]) == list_id), None)
    if not selected_list:
        bot.answer_callback_query(call.id, "Список не найден.")
        return
    text = f"Вы уверены, что хотите удалить список '{selected_list['list_name']}'?"
    markup = types.InlineKeyboardMarkup()
    btn_confirm = types.InlineKeyboardButton("Удалить", callback_data=f"confirm_delete_{list_id}")
    btn_cancel = types.InlineKeyboardButton("Главное меню", callback_data="back_main")
    markup.add(btn_confirm, btn_cancel)
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text=text, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"))
def handle_confirm_delete(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    list_id = call.data.split("confirm_delete_")[1]
    try:
        delete_list(chat_id, list_id)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                           text="Список удалён.", reply_markup=build_main_menu(chat_id))
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка удаления списка: {e}")
    bot.answer_callback_query(call.id)

# =============================================================================
# Режим "Timed рассылка" (с использованием списка или прямой загрузкой)
# =============================================================================
def build_time_unit_markup():
    """Кнопки для выбора единицы времени."""
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("Секунды", callback_data="time_unit_seconds"),
        types.InlineKeyboardButton("Минуты",  callback_data="time_unit_minutes"),
        types.InlineKeyboardButton("Часы",    callback_data="time_unit_hours")
    )
    kb.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data == "toggle_timed")
def handle_toggle_timed(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    if chat_id not in user_state:
        user_state[chat_id] = {}
    if "timed" not in user_state[chat_id]:
        user_state[chat_id]["timed"] = {
            "enabled": False,
            "mode": None,
            "selected": [],
            "photo_path": None
        }
    if user_state[chat_id]["timed"].get("enabled", False):
        user_state[chat_id]["timed"]["enabled"] = False
        bot.edit_message_text(chat_id=chat_id,
                              message_id=call.message.message_id,
                              text="Timed рассылка отключена.",
                              reply_markup=build_main_menu(chat_id))
        bot.answer_callback_query(call.id, "Timed рассылка отключена.")
    else:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_list = types.InlineKeyboardButton("Использовать список", callback_data="timed_list_select")
        btn_load = types.InlineKeyboardButton("Загрузить группы", callback_data="timed_load")
        markup.add(btn_list, btn_load)
        markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
        bot.edit_message_text(chat_id=chat_id,
                              message_id=call.message.message_id,
                              text="Выберите способ настройки timed рассылки:",
                              reply_markup=markup)
        bot.answer_callback_query(call.id)

# Показываем пользователю сохранённые списки для timed-рассылки
# 1) Показываем пользователю его сохранённые списки специально для timed-режима
@bot.callback_query_handler(func=lambda c: c.data == "timed_list_select")
def handle_timed_setup_mode_list(c: types.CallbackQuery):
    chat_id = c.message.chat.id
    if not require_registration(chat_id, c.id):
        return

    lists_db = get_lists(chat_id)
    if not lists_db:
        bot.send_message(
            chat_id,
            "У вас пока нет ни одного сохранённого списка. Сначала создайте его в разделе «Списки».",
            reply_markup=build_main_menu(chat_id)
        )
        return

    # Строим свою клавиатуру именно с префиксом timed_list_
    kb = types.InlineKeyboardMarkup(row_width=1)
    for lst in lists_db:
        kb.add(
            types.InlineKeyboardButton(
                text=lst["list_name"],
                callback_data=f"timed_list_{lst['id']}"
            )
        )
    kb.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))

    bot.edit_message_text(
        "Выберите список для **timed-рассылки**:",
        chat_id=chat_id,
        message_id=c.message.message_id,
        parse_mode="Markdown",
        reply_markup=kb
    )
    bot.answer_callback_query(c.id)



@bot.callback_query_handler(func=lambda call: call.data == "timed_load")
def handle_timed_setup_mode_load(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return

    # Получаем текущий аккаунт (или дефолт 1)
    acc = get_current_account(chat_id) or 1
    try:
        response = limited_get(
            f"{WHATSAPP_SERVER_URL}/groups",
            params={"account_id": acc}
        )
        response.raise_for_status()
        groups = response.json().get("groups", [])
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка получения групп с бэка: {e}", reply_markup=build_main_menu(chat_id))
        return

    if not groups:
        bot.send_message(chat_id, "Не удалось получить список групп с WhatsApp.", reply_markup=build_main_menu(chat_id))
        return

    user_state[chat_id]["timed"] = {
        "enabled": False,
        "mode": "direct",
        "groups": groups,
        "selected": [],
        "photo_path": None,
        "unit": None,
        "interval": None,
        "message": "",
        "awaiting_interval": False,
        "awaiting_timed_message": False,
        "job": None
    }

    markup = build_paginated_groups_markup(
        groups, [], page=1, per_page=10,
        prefix="timed_group_", add_done_button=True
    )
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text="Выберите группы для timed рассылки:",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)


# Обрабатываем выбор конкретного списка и запускаем выбор единицы времени
# 2) Обрабатываем именно выбор списка для timed и сразу идём к выбору единицы времени
@bot.callback_query_handler(func=lambda c: c.data.startswith("timed_list_"))
def handle_timed_list_picked(c: types.CallbackQuery):
    chat_id = c.message.chat.id
    if not require_registration(chat_id, c.id):
        return

    list_id = c.data.split("timed_list_")[1]
    # находим в get_lists
    chosen = next((l for l in get_lists(chat_id) if str(l["id"]) == list_id), None)
    if not chosen:
        bot.answer_callback_query(c.id, "Список не найден.")
        return

    # инициализируем state.timed
    st = user_state.setdefault(chat_id, {})
    st["timed"] = {
        "enabled": False,
        "mode":   "list",
        "selected": chosen["groups"],
        "photo_path": None,
        "unit": None,
        "interval": None,
        "message": "",
        "awaiting_interval": False,
        "awaiting_timed_message": False
    }

    # сразу предлагаем выбрать секунды/минуты/часы
    bot.edit_message_text(
        f"Список «{chosen['list_name']}» выбран.\nВыберите единицу времени для интервала:",
        chat_id=chat_id,
        message_id=c.message.message_id,
        reply_markup=build_time_unit_markup()
    )
    bot.answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("timed_group_") or call.data == "timed_done")
def handle_timed_group_selection(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    if call.data.startswith("timed_group_page_"):
        try:
            page = int(call.data.split("timed_group_page_")[1])
        except Exception:
            page = 1
        user_state[chat_id]["timed"]["current_page"] = page
        groups = user_state[chat_id]["timed"].get("groups", [])
        selected = user_state[chat_id]["timed"].get("selected", [])
        markup = build_paginated_groups_markup(groups, selected, page=page, per_page=10, prefix="timed_group_", add_done_button=True)
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return
    if call.data == "timed_done":
        selected = user_state[chat_id]["timed"].get("selected", [])
        if not selected:
            bot.answer_callback_query(call.id, "Ни одна группа не выбрана.")
            return
        if not user_state[chat_id]["timed"].get("unit"):
            bot.edit_message_text(chat_id=chat_id,
                                  message_id=call.message.message_id,
                                  text="Выберите единицу времени:",
                                  reply_markup=build_time_unit_markup())
        else:
            bot.send_message(chat_id, f"Введите числовое значение интервала в {user_state[chat_id]['timed']['unit']} (например, 2):",
                             reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Главное меню", callback_data="back_main")))
            user_state[chat_id]["timed"]["awaiting_interval"] = True
        bot.answer_callback_query(call.id)
        return
    # Обработка выбора/отмены выбора конкретной группы
    group_id = call.data.split("timed_group_")[1]
    selected = user_state[chat_id]["timed"].get("selected", [])
    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.append(group_id)
    user_state[chat_id]["timed"]["selected"] = selected
    current_page = user_state[chat_id]["timed"].get("current_page", 1)
    groups = user_state[chat_id]["timed"].get("groups", [])
    markup = build_paginated_groups_markup(groups, selected, page=current_page, per_page=10, prefix="timed_group_", add_done_button=True)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("time_unit_"))
def handle_time_unit(call):
    """
    Обработка выбора единицы времени.
    После выбора единицы спрашиваем у пользователя число.
    """
    chat_id = call.message.chat.id
    unit = call.data.split("time_unit_")[1]  # seconds, minutes или hours

    timed = user_state.get(chat_id, {}).get("timed")
    if not timed:
        return bot.answer_callback_query(call.id, "Сначала настройте таймер.")

    # Сохраняем единицу
    timed["unit"] = unit
    bot.answer_callback_query(call.id, f"Выбраны {unit}")

    # Просим ввести числовой интервал
    bot.send_message(
        chat_id,
        f"Введите числовое значение интервала в {unit} (например, 2):",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Главное меню", callback_data="back_main")
        )
    )
    timed["awaiting_interval"] = True
@bot.message_handler(
    func=lambda msg: (
        msg.chat.id in user_state and 
        "timed" in user_state[msg.chat.id] and 
        not msg.text.startswith('/') and 
        (user_state[msg.chat.id]["timed"].get("awaiting_interval", False) or 
         user_state[msg.chat.id]["timed"].get("awaiting_timed_message", False))
    ),
    content_types=['text']
)
def handle_timed_text(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    timed = user_state[chat_id]["timed"]
    if timed.get("awaiting_interval", False):
        try:
            value = float(msg.text)
            unit = timed.get("unit", "seconds")
            if unit == "seconds":
                interval = value
            elif unit == "minutes":
                interval = value * 60
            elif unit == "hours":
                interval = value * 3600
            else:
                interval = value
            timed["interval"] = interval
            timed["awaiting_interval"] = False
            bot.send_message(
                chat_id, 
                "Введите текст сообщения для timed рассылки:",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("Главное меню", callback_data="back_main")
                )
            )
            timed["awaiting_timed_message"] = True
        except ValueError:
            bot.send_message(chat_id, "Введите корректное числовое значение.")
        return
    if timed.get("awaiting_timed_message", False):
        timed["message"] = msg.text
        timed["awaiting_timed_message"] = False
        timed["enabled"] = True
        bot.send_message(
            chat_id,
            f"Timed рассылка включена. Сообщение будет отправляться каждые {timed['interval']} секунд.\n"
            "Чтобы остановить, нажмите кнопку ниже.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("Остановить timed рассылку", callback_data="toggle_timed_off"),
                types.InlineKeyboardButton("Главное меню", callback_data="back_main")
            )
        )
        if "job" not in timed or timed["job"] is None:
            t = threading.Thread(target=timed_broadcast_job, args=(chat_id,))
            t.daemon = True
            timed["job"] = t
            t.start()
        return
    bot.send_message(chat_id, "Введите /start для возврата в главное меню.")


@bot.message_handler(content_types=['photo'])
def handle_photo(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    if chat_id in user_state:
        if "timed" in user_state[chat_id]:
            file_info = bot.get_file(msg.photo[-1].file_id)
            dldir = "downloads"
            os.makedirs(dldir, exist_ok=True)
            path = os.path.join(dldir, f"{msg.photo[-1].file_id}.jpg")
            with open(path, "wb") as f:
                f.write(bot.download_file(file_info.file_path))
            user_state[chat_id]["timed"]["photo_path"] = path
            bot.send_message(chat_id, "Фото получено для timed рассылки. Теперь введите текст или интервал.")
            return
        if "normal" in user_state[chat_id]:
            file_info = bot.get_file(msg.photo[-1].file_id)
            dldir = "downloads"
            os.makedirs(dldir, exist_ok=True)
            path = os.path.join(dldir, f"{msg.photo[-1].file_id}.jpg")
            with open(path, "wb") as f:
                f.write(bot.download_file(file_info.file_path))
            user_state[chat_id]["normal"]["photo_path"] = path
            bot.send_message(chat_id, "Фото получено для обычной рассылки. Теперь введите текст сообщения.")
            return
    bot.send_message(chat_id, "Сначала выберите режим рассылки, затем отправьте фото.", reply_markup=build_main_menu(chat_id))

# Функция отправки сообщений по группам с задержкой 5 секунд между отправками
def send_messages_sequentially(
    chat_id: int,
    groups: List[str],
    message_text: str,
    photo_path: Optional[str] = None,
    delay: int = 5,
) -> Tuple[List[str], List[str]]:
    """
    Отправляет message_text во все группы через бэкенд,
    делает паузу delay секунд между отправками.
    Возвращает кортеж (успешные, ошибки).
    """
    acc = get_current_account(chat_id) or 1
    ok: List[str] = []
    bad: List[str] = []

    for raw in groups:
        group_id = raw.split("@", 1)[0]
        url = f"{WHATSAPP_SERVER_URL}/{acc}/send"

        opened: Dict[str, any] = {}
        try:
            if photo_path and os.path.exists(photo_path):
                opened["photo"] = open(photo_path, "rb")

            resp = limited_post(
                url,
                data={"chat_id": group_id, "message": message_text},
                files=opened
            )
            if resp.ok:
                ok.append(group_id)
            else:
                bad.append(f"{group_id}: HTTP {resp.status_code}")
        except Exception as exc:
            bad.append(f"{group_id}: {exc}")
        finally:
            if "photo" in opened:
                opened["photo"].close()

        time.sleep(delay)

    return ok, bad






# … функция фонового задания для таймера (timed_broadcast_job) …

def schedule_timed_broadcast(chat_id):
    timed = user_state.get(chat_id, {}).get("timed", {})
    if not timed:
        return

    # Инициализируем счётчик, если ещё нет
    if "sent_count" not in timed:
        timed["sent_count"] = 0

    # Если пользователь выключил рассылку — сообщаем об итогах и выходим
    if not timed.get("enabled", False):
        sent = timed.get("sent_count", 0)
        bot.send_message(
            chat_id,
            f"✅ Timed-рассылка остановлена.\nВсего отправлено сообщений: {sent}",
            reply_markup=build_main_menu(chat_id)
        )
        # чистим всё состояние
        user_state.pop(chat_id, None)
        return

    acc       = get_current_account(chat_id) or 1
    interval  = timed.get("interval", 0)
    msg_text  = timed.get("message", "")
    photo     = timed.get("photo_path")
    errors    = []

    # Пробегаемся по чистому списку групп (id без домена)
    for group_id in timed.get("selected", []):
        url  = f"{WHATSAPP_SERVER_URL}/{acc}/send"
        data = {"chat_id": group_id, "message": msg_text}
        files = {}
        if photo and os.path.exists(photo):
            files["photo"] = open(photo, "rb")

        try:
            resp = limited_post(url, data=data, files=files)
            if resp.status_code == 200:
                timed["sent_count"] += 1
            else:
                errors.append(f"{group_id}: HTTP {resp.status_code}")
        except Exception as e:
            errors.append(f"{group_id}: {e}")
        finally:
            if "photo" in files:
                files["photo"].close()

        time.sleep(5)

    # Если были ошибки — напомним о них сразу
    if errors:
        bot.send_message(chat_id, "⚠ Ошибки при отправке:\n" + "\n".join(errors))

    # Планируем следующий запуск через interval секунд
    t = threading.Timer(interval, schedule_timed_broadcast, args=(chat_id,))
    t.daemon = True
    timed["timer"] = t
    t.start()




# =============================================================================
# Изменения для обычной рассылки: последовательная отправка с задержкой
# =============================================================================

# =============================================================================
# Режим "Timed рассылка" с задержкой 5 секунд между отправками в группы
# =============================================================================
# 3) Внутри timed_broadcast_job тоже используем бэкенд-URL
def timed_broadcast_job(chat_id):
    """
    Фоновая функция для отправки сообщений по таймеру.
    Работает до тех пор, пока user_state[chat_id]['timed']['enabled'] == True.
    После каждой итерации всех групп ждет `interval` секунд,
    а при остановке шлет итоговое уведомление.
    """
    # Извлекаем состояние рассылки один раз (будем обновлять внутри цикла)
    timed = user_state.get(chat_id, {}).get("timed", {})
    total_sent = 0
    total_fail = 0

    # Пока пользователь не отключил timed-рассылку
    while timed.get("enabled", False):
        # Определяем интервал и остальные параметры внутри цикла
        interval = timed.get("interval", 0)
        msg_text = timed.get("message", "")
        selected = timed.get("selected", [])
        photo    = timed.get("photo_path")

        # Если нет обязательных параметров — выходим
        if not (interval and msg_text and selected):
            break

        # Отправляем сообщение по каждой группе с задержкой 5 сек между ними
        for raw in selected:
            group_id = raw.split('@', 1)[0]
            url = f"{WHATSAPP_SERVER_URL}/{get_current_account(chat_id) or 1}/send"
            data = {"chat_id": group_id, "message": msg_text}
            files = {}
            if photo and os.path.exists(photo):
                files["photo"] = open(photo, "rb")

            try:
                resp = limited_post(url, data=data, files=files)
                if resp.status_code == 200:
                    total_sent += 1
                else:
                    total_fail += 1
            except Exception:
                total_fail += 1
            finally:
                if "photo" in files:
                    files["photo"].close()

            time.sleep(5)  # пауза между отправками

        # Ждем перед следующей итерацией по interval секундам
        time.sleep(interval)   # <--- здесь interval уже определен

        # Обновляем состояние на случай, если пользователь его изменил
        timed = user_state.get(chat_id, {}).get("timed", {})

    # После выхода из цикла — уведомляем об итогах и чистим состояние
    bot.send_message(
        chat_id,
        f"✅ Timed-рассылка остановлена.\n✅ Успешно: {total_sent}, ❌ Ошибки: {total_fail}",
        reply_markup=build_main_menu(chat_id)
    )
    user_state.pop(chat_id, None)










@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_timed_off"))
def handle_toggle_timed_off(call):
    """
    Останавливает timed-рассылку: выключает флаг, отменяет таймер и чистит state.
    """
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return

    timed = user_state.get(chat_id, {}).get("timed")
    if not timed:
        return bot.answer_callback_query(call.id, "Timed ещё не запущен.")

    # выключаем и отменяем уже запланированный таймер
    timed["enabled"] = False
    timer = timed.get("timer")
    if timer:
        timer.cancel()

    # чистим состояние
    user_state[chat_id].pop("timed", None)

    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text="✅ Timed-рассылка остановлена.",
        reply_markup=build_main_menu(chat_id)
    )
    bot.answer_callback_query(call.id)



# В хендлере, когда вы уже собрали параметр interval, message и selected:
# (обычно сразу после установки timed["enabled"] = True)
def enable_timed(call):
    chat_id = call.message.chat.id
    timed = user_state[chat_id]["timed"]
    timed["enabled"] = True

    # запускаем первый цикл рассылки
    schedule_timed_broadcast(chat_id)

    bot.send_message(
        chat_id,
        f"✅ Timed рассылка запущена. Сообщение будет уходить каждые {timed['interval']} секунд.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Остановить timed", callback_data="toggle_timed_off")
        )
    )

# =============================================================================
# Логика подачи заявки / регистрация пользователей
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "apply_request")
def handle_apply_request(call):
    chat_id = call.message.chat.id
    if is_registered(chat_id):
        bot.answer_callback_query(call.id, "Вы уже зарегистрированы!")
        return
    user_state.setdefault(chat_id, {})["application"] = {"awaiting_text": True}
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Введите текст заявки:",
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("Главное меню", callback_data="back_main")
                          ))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: (msg.chat.id in user_state and "application" in user_state[msg.chat.id]
                                        and user_state[msg.chat.id]["application"].get("awaiting_text", False)
                                        and not msg.text.startswith('/')), content_types=['text'])
def handle_application_text(msg):
    chat_id = msg.chat.id
    app_text = msg.text.strip()
    if not app_text:
        bot.send_message(chat_id, "Текст заявки не может быть пустым. Введите корректный текст:")
        return
    add_application(chat_id, app_text)  # status по умолчанию "pending"
    user_state.pop(chat_id, None)
    bot.send_message(chat_id, "Ваша заявка отправлена. Ожидайте одобрения. Пока ваша заявка не принята, вы не можете пользоваться ботом.",
                     reply_markup=build_main_menu(chat_id))
    try:
        bot.send_message(ADMIN_ID, f"Новая заявка от {chat_id}:\n{app_text}")
    except Exception as e:
        print("Ошибка уведомления администратора:", e)

# Для администратора – просмотр заявок с возможностью принятия/отклонения
@bot.callback_query_handler(func=lambda c: c.data == "view_applications")
def handle_view_applications(c: types.CallbackQuery) -> None:
    """
    Список заявок (pending) с постраничной навигацией.
    Показывается только ADMIN_ID.
    """
    if str(c.from_user.id) != str(ADMIN_ID):
        return bot.answer_callback_query(c.id, "Доступ запрещён.", show_alert=True)

    # получаем все pending-заявки отсортированные по времени
    apps = get_applications()                 # [(id, chat_id, text, submitted_at), ...]

    if not apps:
        bot.edit_message_text(
            "✅ Заявок нет.",
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            reply_markup=build_main_menu(c.message.chat.id)
        )
        return bot.answer_callback_query(c.id)

    # первая страница
    markup = build_applications_markup(apps, page=1, per_page=10)
    bot.edit_message_text(
        "📋 Список заявок:",
        chat_id=c.message.chat.id,
        message_id=c.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("applications_page_"))
def handle_applications_page(call):
    chat_id = call.message.chat.id
    if str(chat_id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "Доступ запрещён.")
        return
    try:
        page = int(call.data.split("applications_page_")[1])
    except:
        page = 1
    apps = get_applications()
    markup = build_applications_markup(apps, page=page, per_page=10)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

# Хендлер для принятия заявки
@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_"))
def handle_accept(call):
    app_id = call.data.split("accept_")[1]
    update_application_status(app_id, "accepted")
    # Извлекаем chat_id заявителя
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM applications WHERE id = ?", (app_id,))
    row = c.fetchone()
    conn.close()
    if row:
        applicant = row[0]
        add_user(applicant, role="user")
        bot.send_message(applicant, "Ваша заявка принята. Теперь вы можете пользоваться ботом!")
    bot.answer_callback_query(call.id, "Заявка принята.")

# Хендлер для отклонения заявки
@bot.callback_query_handler(func=lambda call: call.data.startswith("decline_"))
def handle_decline(call):
    app_id = call.data.split("decline_")[1]
    update_application_status(app_id, "declined")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM applications WHERE id = ?", (app_id,))
    row = c.fetchone()
    conn.close()
    if row:
        applicant = row[0]
        bot.send_message(applicant, "Ваша заявка отклонена. Вы не можете пользоваться ботом.")
    bot.answer_callback_query(call.id, "Заявка отклонена.")
@bot.callback_query_handler(func=lambda c: c.data == "switch_account")
def handle_switch_account(call):
    cid = call.message.chat.id
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM accounts")
    accts = cur.fetchall()
    conn.close()

    if not accts:
        bot.answer_callback_query(call.id)
        bot.send_message(cid, "⚠ Сначала добавьте аккаунт.", reply_markup=build_main_menu(cid))
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    for aid, aname in accts:
        kb.add(types.InlineKeyboardButton(aname, callback_data=f"select_account_{aid}"))
    kb.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    bot.edit_message_text("Выберите аккаунт:", chat_id=cid,
                          message_id=call.message.message_id,
                          reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("select_account_"))
def handle_select_account(call):
    """
    Переключает пользователя на выбранный ранее аккаунт и сохраняет это в БД.
    """
    cid = call.message.chat.id
    aid = int(call.data.split("_")[-1])

    # Обновляем в памяти и в БД
    user_state.setdefault(cid, {})["current_account"] = aid
    set_user_account(cid, aid)

    bot.edit_message_text(
        "✅ Аккаунт переключён.",
        chat_id=cid,
        message_id=call.message.message_id,
        reply_markup=build_main_menu(cid)
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "add_account")
def handle_add_account(call):
    """
    Начинает процесс создания нового WhatsApp-аккаунта.
    Удаляет старый QR (если был) и запрашивает от сервера новый.
    """
    cid = call.message.chat.id
    # Если был незавершённый аккаунт — удаляем его QR
    prev = user_state.get(cid, {}).get("current_account")
    if prev is not None:
        qr_path = os.path.join("public", f"qr_{prev}.png")
        if os.path.exists(qr_path):
            os.remove(qr_path)

    # Ставим флаг, что ждём названия нового аккаунта
    user_state.setdefault(cid, {})["awaiting_new_account"] = True

    bot.edit_message_text(
        "Введите название нового аккаунта:",
        chat_id=cid,
        message_id=call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Главное меню", callback_data="back_main")
        )
    )
    bot.answer_callback_query(call.id)


@bot.message_handler(
    func=lambda m: (
        m.chat.id in user_state and
        user_state[m.chat.id].get("awaiting_new_account")
    ),
    content_types=['text']
)
def handle_new_account(msg):
    """
    Получает имя нового аккаунта, создаёт запись в БД,
    сразу выставляет его как текущий, запрашивает QR и отправляет его пользователю.
    """
    cid = msg.chat.id
    name = msg.text.strip()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO accounts(name) VALUES(?)", (name,))
        conn.commit()
        aid = cur.lastrowid
    except sqlite3.IntegrityError:
        bot.send_message(cid, f"Аккаунт «{name}» уже существует.", reply_markup=build_main_menu(cid))
        conn.close()
        user_state[cid].pop("awaiting_new_account", None)
        return
    conn.close()

    # Снимаем флаг ожидания и сохраняем аккаунт
    user_state[cid].pop("awaiting_new_account", None)
    user_state.setdefault(cid, {})["current_account"] = aid
    set_user_account(cid, aid)

    # Запрашиваем QR от сервера
    try:
        qr_resp = limited_get(
            f"{WHATSAPP_SERVER_URL}/{aid}/new_account_qr",
            timeout=(5, 60)
        )
    except Exception as e:
        bot.send_message(cid, f"Ошибка получения QR: {e}", reply_markup=build_main_menu(cid))
        return

    if qr_resp.status_code == 202:
        bot.send_message(cid, "QR-код генерируется, повторите через секунду...", reply_markup=build_main_menu(cid))
        return

    ct = qr_resp.headers.get("Content-Type", "")
    if qr_resp.status_code == 200 and ct.startswith("image"):
        bot.send_photo(cid, photo=qr_resp.content, caption="📲 Отсканируйте этот QR-код")
    elif qr_resp.status_code == 200 and ct.startswith("application/json"):
        bot.send_message(cid, qr_resp.json().get("message", "Уже авторизован."), reply_markup=build_main_menu(cid))
    else:
        bot.send_message(cid, f"Не удалось получить QR (HTTP {qr_resp.status_code})", reply_markup=build_main_menu(cid))


# ————————————————————————————
# 1) PARSE
# ————————————————————————————
def _schedule_auto_parse() -> None:
    """Запускает _do_parse_once и перепланирует себя."""
    global _parse_timer
    if not AUTO_PARSE_ENABLED:
        return

    # выполняем работу
    _do_parse_once()

    # планируем следующий запуск
    _parse_timer = threading.Timer(PARSE_INTERVAL, _schedule_auto_parse)
    _parse_timer.daemon = True
    _parse_timer.start()

@bot.callback_query_handler(func=lambda c: c.data == "do_parse")
def cq_toggle_auto_parse(c: types.CallbackQuery) -> None:
    """Вкл/выкл авто-парсер (только администратор)."""
    if str(c.from_user.id) != str(ADMIN_ID):
        return bot.answer_callback_query(c.id, "❌ Только админ.", show_alert=True)

    global AUTO_PARSE_ENABLED, _parse_timer
    AUTO_PARSE_ENABLED = not AUTO_PARSE_ENABLED

    if AUTO_PARSE_ENABLED:
        _schedule_auto_parse()
        label = "⏸️  Остановить авто-парсинг"
    else:
        if _parse_timer:
            _parse_timer.cancel()
        label = "📥  Запустить авто-парсинг"

    bot.edit_message_text(
        label,
        chat_id=c.message.chat.id,
        message_id=c.message.message_id,
        reply_markup=build_main_menu(c.message.chat.id)
    )
    bot.answer_callback_query(c.id)





@bot.callback_query_handler(func=lambda c: c.data == "do_search")
def cq_search(c: types.CallbackQuery):
    role, _, _ = get_user(c.message.chat.id)
    if role != "admin":
        return bot.answer_callback_query(c.id, "❌ Только админ.", show_alert=True)
    user_state.setdefault(c.message.chat.id, {})["search"] = True
    bot.edit_message_text(
        "🔍 Введите ключевое слово(а) для поиска (например: Вася 19):",
        chat_id=c.message.chat.id,
        message_id=c.message.message_id
    )
    bot.answer_callback_query(c.id)

@bot.message_handler(
    func=lambda m: (
        m.chat.id in user_state and
        isinstance(user_state[m.chat.id], dict) and
        user_state[m.chat.id].pop("search", False)
    ),
    content_types=['text']
)
def handle_search(m: types.Message):
    terms = m.text.strip().split()
    if not terms:
        return bot.send_message(m.chat.id, "❗ Введите хотя бы одно слово.")

    # Получаем текущий WhatsApp-аккаунт пользователя
    _, _, current_account = get_user(m.chat.id)

    # Строим WHERE: сначала account_id, потом content LIKE по каждому терму
    cond_parts = ["account_id = ?"] + ["content LIKE ?" for _ in terms]
    cond_sql   = " AND ".join(cond_parts)
    sql = (
        f"SELECT id, sender, content, datetime(timestamp,'unixepoch','localtime') AS ts "
        f"FROM profiles WHERE {cond_sql} ORDER BY timestamp DESC LIMIT 20"
    )
    params = [current_account] + [f"%{t}%" for t in terms]

    p_cur.execute(sql, params)
    results = p_cur.fetchall()

    if not results:
        bot.send_message(m.chat.id, f"🔍 Ничего не найдено для аккаунта «{current_account}».")
    elif len(results) == 1:
        pid, sender, content, ts = results[0]
        bot.send_message(
            m.chat.id,
            f"👤 <b>{sender}</b>\n{content}\n🕒 <i>{ts}</i>",
            parse_mode="HTML"
        )
    else:
        kb = types.InlineKeyboardMarkup()
        for pid, sender, content, ts in results:
            label = f"{sender} ({ts})"
            kb.add(types.InlineKeyboardButton(label, callback_data=f"profile_{pid}"))
        bot.send_message(m.chat.id, "🔍 Найдено несколько анкет. Выберите:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("profile_"))
def handle_profile_select(c: types.CallbackQuery):
    pid = int(c.data.split("_", 1)[1])
    # Тот же account, что при поиске
    _, _, current_account = get_user(c.message.chat.id)

    p_cur.execute(
        "SELECT sender, content, datetime(timestamp,'unixepoch','localtime') "
        "FROM profiles WHERE id = ? AND account_id = ?",
        (pid, current_account)
    )
    row = p_cur.fetchone()
    if not row:
        return bot.answer_callback_query(c.id, "❌ Профиль не найден для этого аккаунта.", show_alert=True)

    sender, content, ts = row
    bot.send_message(
        c.message.chat.id,
        f"👤 <b>{sender}</b>\n{content}\n🕒 <i>{ts}</i>",
        parse_mode="HTML"
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda call: call.data == "repeat_broadcast")
def handle_repeat_broadcast(call):
    """Обработчик нажатия inline-кнопки 'Повторить рассылку'."""
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    bot.answer_callback_query(call.id)  # убираем "часики" на кнопке

    # Получаем сохраненные параметры последней рассылки
    state = user_state.get(chat_id, {}).get("last_broadcast")
    if not state:
        bot.send_message(chat_id, "Данные последней рассылки не найдены.")
        return
    text = state.get("text", "")
    groups = state.get("groups", [])
    photo_path = state.get("photo_path")
    if not groups:
        bot.send_message(chat_id, "Нет групп для повторной рассылки.")
        return

    # Функция повторной отправки (логика аналогична send_and_report)
    def resend_messages():
        ok: list[str] = []
        bad: list[str] = []
        total = len(groups)
        sent_count = 0
        progress_msg = bot.send_message(chat_id, f"Отправлено 0/{total}")
        progress_msg_id = progress_msg.message_id

        update_every = 5
        for raw in groups:
            group_id = raw.split("@", 1)[0]
            try:
                opened = {}
                if photo_path and os.path.exists(photo_path):
                    opened["photo"] = open(photo_path, "rb")
                resp = limited_post(
                    f"{WHATSAPP_SERVER_URL}/{get_current_account(chat_id) or 1}/send",
                    data={"chat_id": group_id, "message": text},
                    files=opened
                )
                if resp.ok:
                    ok.append(group_id)
                else:
                    bad.append(f"{group_id}: HTTP {resp.status_code}")
            except Exception as exc:
                bad.append(f"{group_id}: {exc}")
            finally:
                if opened.get('photo'):
                    opened['photo'].close()

            sent_count += 1
            if sent_count % update_every == 0 or sent_count == total:
                bot.edit_message_text(chat_id=chat_id, message_id=progress_msg_id,
                                       text=f"Отправлено {sent_count}/{total}")
            time.sleep(5)

        success_count = len(ok)
        error_count = len(bad)
        result_text = f"✅ Успешно: {success_count}, ❌ Ошибки: {error_count}"
        # Повторно показываем кнопку для ещё одного повтора, если нужно
        markup = types.InlineKeyboardMarkup()
        btn_repeat = types.InlineKeyboardButton("🔁 Повторить рассылку", callback_data="repeat_broadcast")
        markup.add(btn_repeat)
        bot.send_message(chat_id, result_text, reply_markup=markup)

    # **Запускаем повторную рассылку в отдельном потоке**
    EXECUTOR.submit(resend_messages)
# Хендлер для команды /restart (только для администратора)
@bot.message_handler(commands=['restart'])
def handle_restart(message: types.Message):
    chat_id = message.chat.id
    # Проверяем, что команду вызывает админ (сопоставляем с ADMIN_ID)
    if str(chat_id) != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return
    # Пытаемся вызвать API перезапуска сервера
    try:
        resp = requests.post("http://localhost:5000/api/system/restart", timeout=5)
        # Если получен ответ, уведомляем об инициации перезапуска
        bot.reply_to(message, "♻️ Перезапуск системы инициирован...")
    except Exception as e:
        # В случае ошибки (например, нет ответа из-за мгновенного выключения сервера)
        bot.reply_to(message, "♻️ Перезапуск системы выполняется (возможно без ответа).")

@bot.callback_query_handler(func=lambda c: c.data == "login_menu")
def cq_login_menu(c: types.CallbackQuery):
    # 1) Отвечаем Telegram сразу, чтобы callback не успевал истечь
    try:
        bot.answer_callback_query(c.id)
    except Exception:
        pass

    chat_id = c.message.chat.id
    # 2) Проверяем регистрацию
    if not require_registration(chat_id, c.id):
        return

    # 3) Получаем список аккаунтов
    accts = get_all_accounts()
    if not accts:
        bot.send_message(
            chat_id,
            "Нет ни одного WhatsApp-аккаунта. Сначала добавьте его.",
            reply_markup=build_main_menu(chat_id)
        )
        return

    # 4) Строим клавиатуру выбора аккаунта
    kb = types.InlineKeyboardMarkup(row_width=1)
    for aid, name in accts:
        kb.add(types.InlineKeyboardButton(name, callback_data=f"login_{aid}"))
    kb.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))

    # 5) Редактируем текст сообщения с кнопками
    bot.edit_message_text(
        "Выберите аккаунт для получения QR-кода:",
        chat_id=chat_id,
        message_id=c.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("login_"))
def cq_login_account(call: types.CallbackQuery):
    # 1) Аcknowledge callback immediately
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return

    # 2) Save selected account
    aid = call.data.split("_", 1)[1]
    user_state.setdefault(chat_id, {})["current_account"] = aid
    set_user_account(chat_id, aid)

    # 3) Notify user
    bot.send_message(chat_id, "Запрашиваю QR-код, подождите…")

    # 4) Request QR with extended read timeout
    try:
        resp = limited_get(
            f"{WHATSAPP_SERVER_URL}/{aid}/new_account_qr",
            timeout=(5, 60)  # connect=5s, read=60s
        )
        if resp.status_code == 202:
            bot.send_message(
                chat_id,
                "⌛ QR-код генерируется. Повторите запрос через несколько секунд.",
                reply_markup=build_main_menu(chat_id)
            )
        elif resp.status_code == 200:
            ct = resp.headers.get("Content-Type", "")
            if ct.startswith("image"):
                bot.send_photo(
                    chat_id,
                    resp.content,
                    caption=f"📲 Отсканируйте QR для аккаунта «{get_account_name(aid)}»"
                )
            elif ct.startswith("application/json"):
                msg = resp.json().get("message", "Неизвестный ответ сервера.")
                bot.send_message(chat_id, msg, reply_markup=build_main_menu(chat_id))
            else:
                bot.send_message(
                    chat_id,
                    f"❗ Не удалось получить QR-код (HTTP {resp.status_code}).",
                    reply_markup=build_main_menu(chat_id)
                )
        else:
            bot.send_message(
                chat_id,
                f"❗ HTTP {resp.status_code} при получении QR-кода.",
                reply_markup=build_main_menu(chat_id)
            )

    except ReadTimeout:
        bot.send_message(
            chat_id,
            "⌛ Сервер не ответил за 60 секунд. Попробуйте позже.",
            reply_markup=build_main_menu(chat_id)
        )
    except ConnectionError as e:
        bot.send_message(
            chat_id,
            f"❌ Не удалось соединиться с сервером: {e}",
            reply_markup=build_main_menu(chat_id)
        )
    except Exception as e:
        bot.send_message(
            chat_id,
            f"❗ Ошибка при запросе QR-кода: {e}",
            reply_markup=build_main_menu(chat_id)
        )

    # 5) Return to main menu
    bot.send_message(chat_id, "Главное меню:", reply_markup=build_main_menu(chat_id))


if __name__ == "__main__":
    # было так:
    # bot.infinity_polling(timeout=20, long_polling_timeout=10, num_threads=4)

    # делаем так:
    bot.infinity_polling(timeout=20, long_polling_timeout=10)

