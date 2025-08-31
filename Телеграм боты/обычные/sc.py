import os
import sqlite3
import telebot
from telebot import types
import time
import logging
import traceback

##############################################################################
#                             КОНФИГУРАЦИЯ                                    #
##############################################################################

BOT_TOKEN = "7840958839:AAEbsB5Iit22XU0T5g7pgj6gwEPCYPHcpVs"

# Главный администратор (ID Telegram). Все «супер-возможности» доступны только ему.
MAIN_ADMIN_ID = 794991817  # ← Замените на реальный user_id

# Юзернейм главного админа (для обращения в поддержку)
MAIN_ADMIN_USERNAME = "@i_love_angeliny_blin"

# Папки для хранения фото и архивов
PHOTOS_FOLDER = "photos"
FILES_FOLDER  = "codes"

# Лог-файл (для отладочных сообщений)
logging.basicConfig(
    filename="kupikod_debug.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Реквизиты оплаты (можно указать несколько, разделяя символами / или |)
PAYMENT_CARD_DETAILS = "Тинькофф: 2200 7010 7559 3431 | Сбербанк: 4279 3806 2542 6293"

##############################################################################
#                   СПРАВОЧНИКИ/КОНСТАНТЫ ДЛЯ ФИЛЬТРОВ                         #
##############################################################################

CATEGORIES = {
    "Сайт":       ["JS+React", "Flask+React", "PHP+Go", "Flask+Django"],
    "Приложение": ["C++", "Python"],
    "ТГ Бот":     ["Python+telebot"]
}

PRICE_FILTERS = {
    "asc":  "📉 Цена: ниже → выше",
    "desc": "📈 Цена: выше → ниже"
}

##############################################################################
#                             КЛАСС DBManager                                 #
##############################################################################

class DBManager:
    """
    Класс для управления подключением к базе данных SQLite и 
    выполнения основных операций (CRUD).
    """
    def __init__(self, db_path: str = "kupikod.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """
        Создаёт (или проверяет существование) таблиц в базе.
        + Поле created_at в purchases для даты/времени
        """
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Пользователи
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                role INTEGER DEFAULT 0,
                is_approved INTEGER DEFAULT 1
            )
        """)

        # Товары (codes)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS codes (
                code_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                category TEXT,
                subcategory TEXT,
                description TEXT,
                price REAL,
                photo_path TEXT,
                file_path TEXT,
                is_sold INTEGER DEFAULT 0
            )
        """)

        # Избранное
        cur.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code_id INTEGER
            )
        """)

        # Покупки: добавлено created_at
        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code_id INTEGER,
                fio TEXT,
                is_paid INTEGER DEFAULT 0,
                is_waiting_admin_approval INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        # Логи
        cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_id INTEGER,
                action TEXT,
                extra TEXT
            )
        """)

        conn.commit()
        conn.close()

    def execute(self, query, params=(), fetchone=False, fetchall=False, commit=False):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        result = None
        try:
            cur.execute(query, params)
            if query.strip().upper().startswith("INSERT") and commit:
                result = cur.lastrowid
            elif fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()
            if commit:
                conn.commit()
        except Exception as e:
            logging.error(f"DB error: {str(e)}")
        finally:
            conn.close()
        return result

    def ensure_user(self, user_id, username):
        row = self.execute(
            "SELECT user_id FROM users WHERE user_id=?",
            (user_id,),
            fetchone=True
        )
        if not row:
            role = 2 if user_id == MAIN_ADMIN_ID else 0
            self.execute(
                "INSERT INTO users (user_id, username, role) VALUES (?, ?, ?)",
                (user_id, username, role),
                commit=True
            )
        else:
            self.execute(
                "UPDATE users SET username=? WHERE user_id=?",
                (username, user_id),
                commit=True
            )

    def get_user_role(self, user_id: int):
        row = self.execute(
            "SELECT role FROM users WHERE user_id=?",
            (user_id,),
            fetchone=True
        )
        if row:
            return row[0]
        return None

    def update_user_role(self, user_id, new_role):
        self.execute(
            "UPDATE users SET role=? WHERE user_id=?",
            (new_role, user_id),
            commit=True
        )

    def add_log(self, user_id, action, extra=""):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.execute(
            "INSERT INTO logs (timestamp, user_id, action, extra) VALUES (?, ?, ?, ?)",
            (timestamp, user_id, action, extra),
            commit=True
        )

##############################################################################
#                           КЛАСС BotLogic                                   #
##############################################################################

class BotLogic:
    """
    Основная логика бота: добавление кода, поиск, покупка, подтверждение, 
    просмотр покупок и т.д.
    """
    def __init__(self, db_manager: DBManager, bot: telebot.TeleBot):
        self.db = db_manager
        self.bot = bot
        self.user_states = {}

        for folder in (PHOTOS_FOLDER, FILES_FOLDER):
            if not os.path.exists(folder):
                os.makedirs(folder)

    def is_main_admin(self, user_id: int) -> bool:
        return user_id == MAIN_ADMIN_ID

    def start_state(self, user_id, action):
        self.user_states[user_id] = {"action": action, "data": {}}

    def get_state_action(self, user_id):
        return self.user_states.get(user_id, {}).get("action")

    def get_state_data(self, user_id):
        return self.user_states.setdefault(user_id, {}).setdefault("data", {})

    def clear_state(self, user_id):
        if user_id in self.user_states:
            del self.user_states[user_id]

    ########################################################################
    #                    ГЛАВНОЕ МЕНЮ (ReplyKeyboard)                       #
    ########################################################################

    def get_main_menu(self, user_id):
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        row1 = [types.KeyboardButton("🔎 Поиск анкет кодов"), types.KeyboardButton("⭐ Избранные")]
        row2 = [types.KeyboardButton("🛍 Мои покупки"), types.KeyboardButton("👤 Личный кабинет")]
        row3 = [types.KeyboardButton("🛠 Заказать код"), types.KeyboardButton("💬 Поддержка")]
        kb.add(*row1)
        kb.add(*row2)
        kb.add(*row3)

        role = self.db.get_user_role(user_id)
        if role in (1, 2):
            kb.add("➕ Добавить код")
            kb.add("👑 Админ-меню")

        return kb

    def handle_main_menu_message(self, message: telebot.types.Message):
        user_id = message.from_user.id
        text = message.text

        if text == "🔎 Поиск анкет кодов":
            self.handle_search_codes_start(message)
        elif text == "⭐ Избранные":
            self.handle_favorites(message)
        elif text == "🛍 Мои покупки":
            self.handle_my_purchases_button(message)
        elif text == "👤 Личный кабинет":
            self.handle_cabinet_button(message)
        elif text == "🛠 Заказать код":
            self.handle_order_code_button(message)
        elif text == "💬 Поддержка":
            self.handle_support_button(message)
        elif text == "➕ Добавить код":
            self.handle_add_code_start(message)
        elif text == "👑 Админ-меню":
            self.handle_admin_menu_button(message)
        else:
            self.bot.send_message(user_id, "Неизвестная кнопка. Попробуйте другую.")

    ########################################################################
    #                    ЛИЧНЫЙ КАБИНЕТ, ЗАЯВКА НА АДМИНА                  #
    ########################################################################

    def handle_cabinet_button(self, message: telebot.types.Message):
        user_id = message.from_user.id
        role = self.db.get_user_role(user_id)
        text = f"Ваш ID: {user_id}\n"
        if role == 2:
            text += "Роль: Главный админ"
        elif role == 1:
            text += "Роль: Младший админ"
        else:
            text += "Роль: Обычный пользователь"

        kb = types.InlineKeyboardMarkup()
        if role == 0:
            kb.add(types.InlineKeyboardButton("⚠ Подать заявку на админа", callback_data="apply_admin"))

        self.bot.send_message(user_id, text, reply_markup=kb)

    def callback_apply_admin(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        self.bot.answer_callback_query(call.id, "Заявка отправлена.")
        self.bot.send_message(MAIN_ADMIN_ID, f"Пользователь {user_id} хочет стать младшим админом.")
        self.db.add_log(user_id, "APPLY_ADMIN", "User requests admin role")

        try:
            self.bot.edit_message_text(
                "Заявка отправлена. Ожидайте решения.",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception as e:
            logging.error(f"Error editing message after apply_admin: {str(e)}")

    ########################################################################
    #                    АДМИН-МЕНЮ (Просмотр, утверждение)                 #
    ########################################################################

    def handle_admin_menu_button(self, message: telebot.types.Message):
        user_id = message.from_user.id
        role = self.db.get_user_role(user_id)
        if role not in (1, 2):
            self.bot.send_message(user_id, "У вас нет прав для входа в админ-меню.")
            return

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📊 Посмотреть все продажи", callback_data="admin_sales"))
        kb.add(types.InlineKeyboardButton("Просмотр всех покупок пользователей (оплаченных)",
                                          callback_data="admin_paid_purchases"))
        if user_id == MAIN_ADMIN_ID:
            kb.add(types.InlineKeyboardButton("Оповестить об обновлении", callback_data="notify_update"))

        kb.add(types.InlineKeyboardButton("Утвердить пользователя в админы", callback_data="admin_approve_user"))
        self.bot.send_message(user_id, "Админ-меню:", reply_markup=kb)

    def callback_admin_menu_sales(self, call: telebot.types.CallbackQuery):
        rows = self.db.execute("""
            SELECT p.purchase_id, p.user_id, c.name, c.price, p.is_paid
            FROM purchases p
            JOIN codes c ON p.code_id = c.code_id
        """, fetchall=True)
        if not rows:
            self.bot.edit_message_text("Пока нет покупок.", call.message.chat.id, call.message.message_id)
            return

        text = "Все покупки (включая неоплаченные):\n\n"
        for (pid, buyer_id, code_name, code_price, is_paid) in rows:
            status = "Оплачено" if is_paid else "Не оплачено"
            text += f"#{pid}: {buyer_id}, {code_name}, {code_price} руб. [{status}]\n"

        try:
            self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
        except Exception as e:
            logging.error(f"Error editing admin_sales message: {str(e)}")
            self.bot.send_message(call.message.chat.id, text)

    ########################################################################
    #     Просмотр ОПЛАЧЕННЫХ покупок (постраничный) — admin_paid_purchases #
    ########################################################################

    def callback_admin_paid_purchases(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        sql = """
        SELECT p.purchase_id, p.user_id, p.fio, c.name, c.category, p.created_at
        FROM purchases p
        JOIN codes c ON p.code_id = c.code_id
        WHERE p.is_paid=1
        ORDER BY p.created_at DESC
        """
        rows = self.db.execute(sql, fetchall=True)
        if not rows:
            self.bot.edit_message_text("Пока нет оплаченных покупок.", call.message.chat.id, call.message.message_id)
            return

        # Инициализируем состояние для пагинации
        self.user_states.setdefault(user_id, {})
        self.user_states[user_id]["paid_purchases"] = rows
        self.user_states[user_id]["paid_page"] = 0
        self.show_paid_purchases_page(user_id, call.message.message_id)

    def show_paid_purchases_page(self, user_id, message_id):
        purchases = self.user_states[user_id].get("paid_purchases", [])
        page = self.user_states[user_id].get("paid_page", 0)

        PAGE_SIZE = 5
        total = len(purchases)
        max_page = (total - 1) // PAGE_SIZE if total > 0 else 0
        page = max(0, min(page, max_page))
        self.user_states[user_id]["paid_page"] = page

        start_i = page * PAGE_SIZE
        end_i = start_i + PAGE_SIZE
        subset = purchases[start_i:end_i]

        text_lines = []
        text_lines.append("Оплаченные покупки (новые сверху):\n")
        for (pid, buyer_id, fio, code_name, category, created_at) in subset:
            line = (f"• Покупка #{pid} от {buyer_id} (FIO: {fio})\n"
                    f"  Проект: {code_name} / {category}\n"
                    f"  Дата: {created_at}\n")
            text_lines.append(line)
        text_lines.append(f"\nСтраница {page+1} из {max_page+1}. Всего: {total} покупок.")

        text_msg = "\n".join(text_lines)

        markup = types.InlineKeyboardMarkup()
        btn_prev = types.InlineKeyboardButton("← Назад", callback_data="admin_paid_prev")
        btn_page = types.InlineKeyboardButton(f"{page+1}/{max_page+1}", callback_data="admin_paid_noop")
        btn_next = types.InlineKeyboardButton("Вперёд →", callback_data="admin_paid_next")
        markup.row(btn_prev, btn_page, btn_next)

        try:
            self.bot.edit_message_text(
                text_msg,
                user_id,
                message_id,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.error(f"Error editing paid purchases message: {str(e)}")
            self.bot.send_message(
                user_id,
                text_msg,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True
            )

    def callback_admin_paid_prev(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        self.user_states[user_id]["paid_page"] -= 1
        self.show_paid_purchases_page(user_id, call.message.message_id)
        self.bot.answer_callback_query(call.id)

    def callback_admin_paid_next(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        self.user_states[user_id]["paid_page"] += 1
        self.show_paid_purchases_page(user_id, call.message.message_id)
        self.bot.answer_callback_query(call.id)

    def callback_admin_paid_noop(self, call: telebot.types.CallbackQuery):
        self.bot.answer_callback_query(call.id, "Страница.")

    ########################################################################
    #           Новая логика: "notify_update" - рассылка всем              #
    ########################################################################

    def start_broadcast_mode(self, user_id):
        self.start_state(user_id, "notify_update")
        self.bot.send_message(user_id, "Введите текст, который вы хотите разослать всем пользователям:")

    def handle_broadcast_text(self, message: telebot.types.Message):
        user_id = message.from_user.id
        text_for_broadcast = message.text

        rows = self.db.execute("SELECT user_id FROM users", fetchall=True)
        broadcast_count = 0
        for (uid,) in rows:
            try:
                self.bot.send_message(uid, f"Оповещение от админа:\n\n{text_for_broadcast}")
                broadcast_count += 1
            except Exception as e:
                logging.warning(f"Не удалось отправить сообщение пользователю {uid}: {str(e)}")

        self.bot.send_message(user_id, f"Рассылка завершена. Отправлено {broadcast_count} пользователям.")
        self.clear_state(user_id)

    def handle_admin_approve_user_input(self, message: telebot.types.Message):
        user_id = message.from_user.id
        try:
            target_id = int(message.text.strip())
        except:
            self.bot.send_message(user_id, "Некорректный ID. Попробуйте снова.")
            return

        # Проверяем, существует ли пользователь
        if not self.db.execute("SELECT user_id FROM users WHERE user_id=?", (target_id,), fetchone=True):
            self.bot.send_message(user_id, "Пользователь не найден.")
            return

        self.db.update_user_role(target_id, 1)
        self.db.add_log(user_id, "APPROVE_ADMIN", f"target_user={target_id}")
        self.bot.send_message(user_id, f"Пользователь {target_id} назначен младшим администратором.")
        self.clear_state(user_id)

    ########################################################################
    #               МОИ ПОКУПКИ (кнопка «Мои покупки»)                      #
    ########################################################################

    def handle_my_purchases_button(self, message: telebot.types.Message):
        user_id = message.from_user.id
        rows = self.db.execute("""
            SELECT p.purchase_id, c.name, c.price, p.is_paid, p.is_waiting_admin_approval
            FROM purchases p
            JOIN codes c ON p.code_id = c.code_id
            WHERE p.user_id=?
        """, (user_id,), fetchall=True)

        if not rows:
            self.bot.send_message(user_id, "У вас нет покупок.")
            return

        text = "Ваши покупки:\n\n"
        for (purchase_id, code_name, code_price, is_paid, waiting) in rows:
            if is_paid:
                status = "✅ Оплачено"
            else:
                if waiting:
                    status = "⌛ Ожидает подтверждения админом"
                else:
                    status = "Не оплачено"
            text += f"#{purchase_id}: {code_name}, {code_price} руб. — {status}\n"

        self.bot.send_message(user_id, text)

    ########################################################################
    #                 ЗАКАЗАТЬ КОД (заглушка)                               #
    ########################################################################

    def handle_order_code_button(self, message: telebot.types.Message):
        user_id = message.from_user.id
        self.bot.send_message(
            user_id,
            "Здесь могла бы быть логика индивидуального заказа.\n"
            "Пока это заглушка. Обратитесь к администратору."
        )

    ########################################################################
    #                         ПОДДЕРЖКА                                     #
    ########################################################################

    def handle_support_button(self, message: telebot.types.Message):
        user_id = message.from_user.id
        text = (
            f"Если у вас возникли вопросы, напишите {MAIN_ADMIN_USERNAME}\n"
            "Мы поможем как можно скорее!"
        )
        self.bot.send_message(user_id, text)

    ########################################################################
    #                 ДОБАВЛЕНИЕ КОДА (по кнопке «Добавить»)                #
    ########################################################################

    def handle_add_code_start(self, message: telebot.types.Message):
        user_id = message.from_user.id
        role = self.db.get_user_role(user_id)
        if role not in (1, 2):
            self.bot.send_message(user_id, "У вас нет прав добавлять код.")
            return

        self.start_state(user_id, "add_code")
        self.bot.send_message(user_id, "Введите название кода (проекта).")

    def handle_add_code_name(self, message: telebot.types.Message):
        user_id = message.from_user.id
        data = self.get_state_data(user_id)
        data["name"] = message.text

        markup = types.InlineKeyboardMarkup()
        for cat in CATEGORIES.keys():
            markup.add(types.InlineKeyboardButton(cat, callback_data=f"add_code_cat|{cat}"))
        self.bot.send_message(user_id, "Выберите категорию:", reply_markup=markup)

    def callback_add_code_category(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        data = self.get_state_data(user_id)
        cat = call.data.split("|")[1]
        data["category"] = cat

        markup = types.InlineKeyboardMarkup()
        for subcat in CATEGORIES[cat]:
            markup.add(types.InlineKeyboardButton(subcat, callback_data=f"add_code_subcat|{subcat}"))

        try:
            self.bot.edit_message_text(
                f"Вы выбрали категорию {cat}. Теперь выберите подкатегорию:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        except Exception as e:
            logging.error(f"Error editing message for category selection: {str(e)}")

        self.bot.answer_callback_query(call.id)

    def callback_add_code_subcategory(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        data = self.get_state_data(user_id)
        subcat = call.data.split("|")[1]
        data["subcategory"] = subcat

        text = (
            f"Название: {data['name']}\n"
            f"Категория: {data['category']}\n"
            f"Подкатегория: {subcat}\n\n"
            "Теперь отправьте описание кода."
        )
        self.bot.edit_message_text(
            text, 
            call.message.chat.id,
            call.message.message_id
        )
        self.bot.answer_callback_query(call.id)

    def handle_add_code_description(self, message: telebot.types.Message):
        user_id = message.from_user.id
        data = self.get_state_data(user_id)
        data["description"] = message.text
        self.bot.send_message(user_id, "Отправьте фото (превью) этого кода.")

    def handle_add_code_photo(self, message: telebot.types.Message):
        user_id = message.from_user.id
        data = self.get_state_data(user_id)

        if not message.photo:
            self.bot.send_message(user_id, "Нужно прислать фото.")
            return

        photo = message.photo[-1]
        file_id = photo.file_id
        file_info = self.bot.get_file(file_id)
        downloaded = self.bot.download_file(file_info.file_path)

        photo_path = os.path.join(PHOTOS_FOLDER, f"{user_id}_{file_id}.jpg")
        with open(photo_path, "wb") as f:
            f.write(downloaded)

        data["photo_path"] = photo_path
        self.bot.send_message(user_id, "Введите цену (число).")

    def handle_add_code_price(self, message: telebot.types.Message):
        user_id = message.from_user.id
        data = self.get_state_data(user_id)
        try:
            price = float(message.text.replace(",", "."))
        except ValueError:
            self.bot.send_message(user_id, "Некорректная цена. Введите число.")
            return

        data["price"] = price
        self.bot.send_message(user_id, "Загрузите ZIP или другой файл с кодом.")

    def handle_add_code_file(self, message: telebot.types.Message):
        user_id = message.from_user.id
        data = self.get_state_data(user_id)

        if not message.document:
            self.bot.send_message(user_id, "Нужно отправить документ (ZIP).")
            return

        doc = message.document
        file_id = doc.file_id
        file_info = self.bot.get_file(file_id)
        downloaded = self.bot.download_file(file_info.file_path)

        file_path = os.path.join(FILES_FOLDER, f"{user_id}_{doc.file_name}")
        with open(file_path, "wb") as f:
            f.write(downloaded)

        data["file_path"] = file_path

        # Добавляем код в БД и получаем code_id
        code_id = self.db.execute("""
            INSERT INTO codes (name, category, subcategory, description, price, photo_path, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["name"],
            data["category"],
            data["subcategory"],
            data["description"],
            data["price"],
            data["photo_path"],
            data["file_path"]
        ), commit=True)

        if not code_id:
            logging.error(f"Failed to insert code for user {user_id}.")
            self.bot.send_message(user_id, "Произошла ошибка при добавлении кода.")
            self.clear_state(user_id)
            return

        self.db.add_log(user_id, "ADD_CODE", f"code_id={code_id}, {data['name']} ({data['category']} -> {data['subcategory']})")

        self.bot.send_message(user_id, "Код успешно добавлен!")
        self.clear_state(user_id)
        kb = self.get_main_menu(user_id)
        self.bot.send_message(user_id, "Что дальше?", reply_markup=kb)

    ########################################################################
    #              ПОИСК КОДОВ: «Общий поиск» и «с фильтрами»               #
    ########################################################################

    def handle_search_codes_start(self, message: telebot.types.Message):
        """
        Предлагаем пользователю: 
        1) Общий поиск (все товары) 
        2) Поиск с фильтрами (категория → подкатегория → цена).
        """
        user_id = message.from_user.id
        self.start_state(user_id, "search_codes")

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Общий поиск (без фильтров)", callback_data="search_all"))
        markup.add(types.InlineKeyboardButton("Поиск с фильтрами", callback_data="search_filters_start"))
        self.bot.send_message(user_id, "Выберите способ поиска:", reply_markup=markup)

    def callback_search_category(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        cat = call.data.split("|")[1]

        # Проверяем, что пользователь находится в правильном состоянии
        if self.get_state_action(user_id) != "search_codes":
            self.bot.answer_callback_query(call.id, "Пожалуйста, начните поиск сначала.", show_alert=True)
            return

        # Сохраняем выбранную категорию
        self.user_states[user_id]["data"]["search_cat"] = cat

        # Предлагаем подкатегории
        markup = types.InlineKeyboardMarkup()
        for subcat in CATEGORIES[cat]:
            markup.add(types.InlineKeyboardButton(subcat, callback_data=f"search_subcat|{subcat}"))
        markup.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data="search_confirm_subcat"))
        self.bot.edit_message_text(
            text=f"Вы выбрали категорию: {cat}\nТеперь выберите подкатегорию:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        self.bot.answer_callback_query(call.id)

    def callback_search_subcategory(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        subcat = call.data.split("|")[1]

        # Проверяем, что пользователь находится в правильном состоянии и выбрал категорию
        if self.get_state_action(user_id) != "search_codes" or "search_cat" not in self.user_states[user_id]["data"]:
            self.bot.answer_callback_query(call.id, "Пожалуйста, начните поиск сначала.", show_alert=True)
            return

        # Сохраняем выбранную подкатегорию
        self.user_states[user_id]["data"]["search_subcat"] = subcat
        self.bot.answer_callback_query(call.id, f"Подкатегория: {subcat}", show_alert=True)

    def callback_search_confirm_subcat(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        data = self.user_states[user_id]["data"]
        cat = data.get("search_cat", "не выбрана")
        subcat = data.get("search_subcat", "не выбрана")

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📉 Цена: ниже → выше", callback_data="search_price|asc"))
        markup.add(types.InlineKeyboardButton("📈 Цена: выше → ниже", callback_data="search_price|desc"))
        self.bot.edit_message_text(
            text=f"Выбрана категория: {cat}\nПодкатегория: {subcat}\n\nВыберите порядок сортировки по цене:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        self.bot.answer_callback_query(call.id)

    def callback_search_price_filter(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        order = call.data.split("|")[1]
        self.user_states[user_id]["data"]["search_price_order"] = order

        cat = self.user_states[user_id]["data"].get("search_cat", "не выбрана")
        subcat = self.user_states[user_id]["data"].get("search_subcat", "не выбрана")
        text = f"Категория: {cat}\nПодкатегория: {subcat}\nСортировка: {PRICE_FILTERS[order]}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Начать поиск", callback_data="search_start"))
        self.bot.edit_message_text(
            text=text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        self.bot.answer_callback_query(call.id)

    def callback_search_reset(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        self.user_states[user_id]["data"].pop("search_cat", None)
        self.user_states[user_id]["data"].pop("search_subcat", None)
        self.user_states[user_id]["data"].pop("search_price_order", None)
        self.bot.edit_message_text(
            "Фильтры сброшены. Выберите категорию:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        self.bot.answer_callback_query(call.id)

    def callback_search_start(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        data = self.user_states[user_id]["data"]
        cat = data.get("search_cat", None)
        subcat = data.get("search_subcat", None)
        price_order = data.get("search_price_order", None)

        # Строим запрос
        sql = "SELECT code_id, name, category, subcategory, description, price, photo_path FROM codes WHERE is_sold=0"
        params = []
        if cat:
            sql += " AND category=?"
            params.append(cat)
        if subcat:
            sql += " AND subcategory=?"
            params.append(subcat)
        if price_order == "asc":
            sql += " ORDER BY price ASC"
        elif price_order == "desc":
            sql += " ORDER BY price DESC"

        results = self.db.execute(sql, params, fetchall=True)
        self.user_states[user_id]["search_results"] = results
        self.user_states[user_id]["search_idx"] = 0
        if not results:
            self.bot.edit_message_text(
                "Ничего не найдено по фильтрам.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        else:
            self.show_search_result(user_id, call.message.message_id)

        self.bot.answer_callback_query(call.id)

    def show_search_result(self, user_id, msg_id):
        results = self.user_states[user_id].get("search_results", [])
        idx = self.user_states[user_id].get("search_idx", 0)

        if idx < 0:
            idx = 0
        if idx >= len(results):
            idx = len(results) - 1
        self.user_states[user_id]["search_idx"] = idx

        if not results:
            self.bot.send_message(user_id, "Ничего не найдено.")
            return

        code_id, name, cat, subcat, desc, price, photo_path = results[idx]
        caption = (
            f"<b>{name}</b>\n"
            f"Категория: {cat}\n"
            f"Подкатегория: {subcat}\n"
            f"Описание: {desc}\n"
            f"Цена: {price} руб."
        )

        markup = types.InlineKeyboardMarkup()
        b_prev = types.InlineKeyboardButton("← Назад", callback_data="search_prev")
        b_noop = types.InlineKeyboardButton(f"{idx+1}/{len(results)}", callback_data="search_noop")
        b_next = types.InlineKeyboardButton("Вперёд →", callback_data="search_next")
        b_buy = types.InlineKeyboardButton("Купить", callback_data=f"user_buy|{code_id}")
        b_fav = types.InlineKeyboardButton("★", callback_data=f"add_fav|{code_id}")
        markup.row(b_prev, b_noop, b_next)
        markup.row(b_buy, b_fav)

        if photo_path and os.path.exists(photo_path):
            try:
                with open(photo_path, "rb") as f:
                    photo = f.read()
                self.bot.edit_message_media(
                    media=types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML"),
                    chat_id=user_id,
                    message_id=msg_id,
                    reply_markup=markup
                )
            except Exception as e:
                logging.error(f"Error editing media: {str(e)}")
                try:
                    with open(photo_path, "rb") as f:
                        self.bot.send_photo(
                            user_id,
                            f,
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=markup
                        )
                except Exception as ex:
                    logging.error(f"Error sending photo fallback: {str(ex)}")
        else:
            try:
                self.bot.edit_message_text(
                    caption,
                    chat_id=user_id,
                    message_id=msg_id,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except Exception as e:
                logging.error(f"Error editing message without photo: {str(e)}")
                self.bot.send_message(user_id, caption, parse_mode="HTML", reply_markup=markup)

    def callback_search_nav(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        if call.data == "search_prev":
            self.user_states[user_id]["search_idx"] -= 1
        else:  # search_next
            self.user_states[user_id]["search_idx"] += 1

        # Проверяем границы
        idx = self.user_states[user_id]["search_idx"]
        total = len(self.user_states[user_id].get("search_results", []))
        if idx < 0:
            self.user_states[user_id]["search_idx"] = 0
        elif idx >= total:
            self.user_states[user_id]["search_idx"] = total - 1

        try:
            self.show_search_result(user_id, call.message.message_id)
        except Exception as e:
            logging.error(f"Error showing search result: {str(e)}")
            self.bot.answer_callback_query(call.id, "Произошла ошибка при отображении результата.", show_alert=True)

        self.bot.answer_callback_query(call.id)

    def callback_search_noop(self, call: telebot.types.CallbackQuery):
        self.bot.answer_callback_query(call.id, "Страница.")

    ########################################################################
    #                     ИЗБРАННОЕ (добавить / удалить)                    #
    ########################################################################

    def handle_favorites(self, message: telebot.types.Message):
        user_id = message.from_user.id
        rows = self.db.execute("""
            SELECT f.id, c.code_id, c.name, c.price
            FROM favorites f
            JOIN codes c ON f.code_id = c.code_id
            WHERE f.user_id=?
        """, (user_id,), fetchall=True)

        if not rows:
            self.bot.send_message(user_id, "У вас нет избранных кодов.")
            return

        text = "Ваши избранные:\n\n"
        markup = types.InlineKeyboardMarkup()
        for (fav_id, code_id, name, price) in rows:
            text += f"ID: {code_id}, {name}, {price} руб.\n"
            markup.add(types.InlineKeyboardButton(f"Убрать «{name}»", callback_data=f"remove_fav|{code_id}"))

        self.bot.send_message(user_id, text, reply_markup=markup)

    def callback_add_fav(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        code_id = call.data.split("|")[1]
        row = self.db.execute("""
            SELECT id FROM favorites WHERE user_id=? AND code_id=?
        """, (user_id, code_id), fetchone=True)
        if row:
            self.bot.answer_callback_query(call.id, "Уже в избранном.")
        else:
            self.db.execute(
                "INSERT INTO favorites (user_id, code_id) VALUES (?, ?)",
                (user_id, code_id),
                commit=True
            )
            self.bot.answer_callback_query(call.id, "Добавлено в избранные!")
            self.db.add_log(user_id, "ADD_FAV", f"code_id={code_id}")

    def callback_remove_fav(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        code_id = call.data.split("|")[1]
        self.db.execute(
            "DELETE FROM favorites WHERE user_id=? AND code_id=?",
            (user_id, code_id),
            commit=True
        )
        self.bot.answer_callback_query(call.id, "Убрано из избранного.")
        self.db.add_log(user_id, "REMOVE_FAV", f"code_id={code_id}")

    ########################################################################
    #                            ПОКУПКА КОДА                               #
    ########################################################################

    def callback_user_buy(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        code_id = call.data.split("|")[1]
        logging.info(f"User {user_id} is attempting to buy code {code_id}.")

        # Проверяем, продан ли код
        row = self.db.execute("SELECT is_sold FROM codes WHERE code_id=?", (code_id,), fetchone=True)
        if not row:
            logging.warning(f"Code {code_id} not found.")
            self.bot.answer_callback_query(call.id, "Код не найден.", show_alert=True)
            return
        if row[0] == 1:
            logging.info(f"Code {code_id} is already sold.")
            self.bot.answer_callback_query(call.id, "Этот код уже продан.", show_alert=True)
            return

        # Проверяем, есть ли уже запись о покупке
        purchase_row = self.db.execute("""
            SELECT purchase_id, is_paid FROM purchases
            WHERE user_id=? AND code_id=?
        """, (user_id, code_id), fetchone=True)

        if not purchase_row:
            created_at = time.strftime("%Y-%m-%d %H:%M:%S")
            purchase_id = self.db.execute("""
                INSERT INTO purchases (user_id, code_id, created_at) 
                VALUES (?, ?, ?)
            """, (user_id, code_id, created_at), commit=True)

            if not purchase_id:
                logging.error(f"Failed to create purchase for user {user_id}, code {code_id}.")
                self.bot.answer_callback_query(call.id, "Произошла ошибка при создании покупки.", show_alert=True)
                return
            logging.info(f"Created purchase {purchase_id} for user {user_id}, code {code_id}.")
        else:
            purchase_id, is_paid = purchase_row
            if is_paid == 1:
                logging.info(f"Purchase {purchase_id} already paid.")
                self.bot.answer_callback_query(call.id, "Покупка уже оплачена.", show_alert=True)
                return
            logging.info(f"Found existing purchase {purchase_id} for user {user_id}, code {code_id}.")

        # Устанавливаем состояние для ввода ФИО
        self.start_state(user_id, "enter_fio")
        self.get_state_data(user_id)["purchase_id"] = purchase_id
        self.bot.answer_callback_query(call.id, "Введите ФИО.")
        self.bot.send_message(user_id, "Введите ваши ФИО, чтобы админ смог проверить оплату.")

    def handle_user_fio_input(self, message: telebot.types.Message):
        user_id = message.from_user.id
        fio = message.text.strip()
        data = self.get_state_data(user_id)
        purchase_id = data.get("purchase_id")

        if not purchase_id:
            self.bot.send_message(user_id, "Произошла ошибка. Попробуйте снова.")
            self.clear_state(user_id)
            return

        self.db.execute(
            "UPDATE purchases SET fio=? WHERE purchase_id=?",
            (fio, purchase_id),
            commit=True
        )

        # Узнаём название и цену кода
        row = self.db.execute("""
            SELECT code_id FROM purchases WHERE purchase_id=?
        """, (purchase_id,), fetchone=True)
        if not row:
            code_name, code_price = "(неизвестно)", 0
        else:
            code_id = row[0]
            row_code = self.db.execute("""
                SELECT name, price FROM codes WHERE code_id=?
            """, (code_id,), fetchone=True)
            if row_code:
                code_name, code_price = row_code
            else:
                code_name, code_price = "(неизвестно)", 0

        text_user = (
            f"Ваши ФИО: <b>{fio}</b>\n"
            f"Покупка: <b>{code_name}</b>\n"
            f"Цена: <b>{code_price} руб.</b>\n\n"
            "Переведите эту сумму на реквизиты:\n"
            f"<b>{PAYMENT_CARD_DETAILS}</b>\n\n"
            "Затем нажмите «Подтвердить оплату».\n"
            "Админ проверит поступление и вышлет вам файл."
        )

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 Подтвердить оплату", callback_data=f"user_confirm_pay|{purchase_id}"))

        self.bot.send_message(
            user_id,
            text_user,
            parse_mode="HTML",
            reply_markup=kb
        )
        self.clear_state(user_id)

    def callback_user_confirm_pay(self, call: telebot.types.CallbackQuery):
        user_id = call.from_user.id
        purchase_id = call.data.split("|")[1]

        self.db.execute(
            "UPDATE purchases SET is_waiting_admin_approval=1 WHERE purchase_id=?",
            (purchase_id,),
            commit=True
        )

        row = self.db.execute("""
            SELECT p.user_id, p.code_id, p.fio, c.name, c.price
            FROM purchases p
            JOIN codes c ON p.code_id = c.code_id
            WHERE p.purchase_id=?
        """, (purchase_id,), fetchone=True)
        if not row:
            self.bot.answer_callback_query(call.id, "Покупка не найдена.", show_alert=True)
            return

        buyer_id, code_id, fio, code_name, code_price = row

        try:
            self.bot.edit_message_text(
                "Заявка на подтверждение оплаты отправлена администратору. Ожидайте.",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception as e:
            logging.error(f"Error editing payment confirmation message: {str(e)}")

        text_admin = (
            f"Пользователь <b>{buyer_id}</b> (ФИО: {fio})\n"
            f"Покупает: {code_name} за {code_price} руб.\n\n"
            "Подтвердить оплату?"
        )
        kb_admin = types.InlineKeyboardMarkup()
        kb_admin.add(
            types.InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"admin_approve_pay|{purchase_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_pay|{purchase_id}")
        )
        self.bot.send_message(MAIN_ADMIN_ID, text_admin, parse_mode="HTML", reply_markup=kb_admin)
        self.bot.answer_callback_query(call.id)

    def callback_admin_approve_pay(self, call: telebot.types.CallbackQuery):
        admin_id = call.from_user.id
        if admin_id != MAIN_ADMIN_ID:
            self.bot.answer_callback_query(call.id, "Недостаточно прав.", show_alert=True)
            return

        purchase_id = call.data.split("|")[1]
        row = self.db.execute("""
            SELECT user_id, code_id, fio, is_paid 
            FROM purchases 
            WHERE purchase_id=?
        """, (purchase_id,), fetchone=True)
        if not row:
            self.bot.answer_callback_query(call.id, "Покупка не найдена.", show_alert=True)
            return

        user_id, code_id, fio, is_paid = row
        if is_paid == 1:
            self.bot.answer_callback_query(call.id, "Уже оплачено.", show_alert=True)
            return

        # Подтверждаем
        self.db.execute("""
            UPDATE purchases 
            SET is_paid=1, is_waiting_admin_approval=0
            WHERE purchase_id=?
        """, (purchase_id,), commit=True)
        self.db.execute("""
            UPDATE codes SET is_sold=1 WHERE code_id=?
        """, (code_id,), commit=True)

        try:
            self.bot.edit_message_text(
                f"Оплата подтверждена. Пользователю ({user_id}) отправлен файл.",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception as e:
            logging.error(f"Error editing payment approval message: {str(e)}")

        row_code = self.db.execute("SELECT file_path FROM codes WHERE code_id=?", (code_id,), fetchone=True)
        file_path = row_code[0] if row_code else None

        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    self.bot.send_document(user_id, f)
                self.bot.send_message(user_id, "Админ подтвердил оплату. Вот ваш файл:")
            except Exception as e:
                logging.error(f"Error sending file to user {user_id}: {str(e)}")
                self.bot.send_message(
                    user_id,
                    "Админ подтвердил оплату, но не удалось отправить файл. Обратитесь в поддержку."
                )
        else:
            self.bot.send_message(
                user_id,
                "Админ подтвердил оплату, но архив не найден. Обратитесь в поддержку."
            )

        self.db.add_log(user_id, "PURCHASE_APPROVED", f"code_id={code_id}")
        self.bot.answer_callback_query(call.id, "Оплата подтверждена.")

    def callback_admin_reject_pay(self, call: telebot.types.CallbackQuery):
        admin_id = call.from_user.id
        if admin_id != MAIN_ADMIN_ID:
            self.bot.answer_callback_query(call.id, "Недостаточно прав.", show_alert=True)
            return

        purchase_id = call.data.split("|")[1]
        row = self.db.execute("""
            SELECT user_id, code_id, fio 
            FROM purchases
            WHERE purchase_id=?
        """, (purchase_id,), fetchone=True)
        if not row:
            self.bot.answer_callback_query(call.id, "Покупка не найдена.", show_alert=True)
            return

        user_id, code_id, fio = row

        self.db.execute("""
            UPDATE purchases
            SET is_waiting_admin_approval=0
            WHERE purchase_id=?
        """, (purchase_id,), commit=True)

        try:
            self.bot.edit_message_text(
                f"Оплата отклонена. Покупка #{purchase_id}, пользователь {user_id}, ФИО: {fio}.",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception as e:
            logging.error(f"Error editing payment rejection message: {str(e)}")

        self.bot.send_message(
            user_id,
            "Администратор отклонил оплату.\n\n"
            "Возможно, вы не оплатили или оплатили неверную сумму.\n"
            "Обратитесь в поддержку или повторите оплату заново."
        )
        self.db.add_log(user_id, "PURCHASE_REJECTED", f"code_id={code_id}")
        self.bot.answer_callback_query(call.id, "Оплата отклонена.")

##############################################################################
#                       ЗАПУСК БОТА (polling)                                #
##############################################################################

db_manager = DBManager("kupikod.db")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
logic = BotLogic(db_manager, bot)

@bot.message_handler(commands=["start"])
def cmd_start(message: telebot.types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    db_manager.ensure_user(user_id, username)

    kb = logic.get_main_menu(user_id)
    text = (
        f"Добро пожаловать, <b>{username}</b>!\n"
        "Это бот «Купикод», где вы можете покупать и продавать готовые коды.\n"
        "Воспользуйтесь меню ниже."
    )
    bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)

@bot.message_handler(content_types=["text"])
def on_text(message: telebot.types.Message):
    user_id = message.from_user.id
    text = message.text
    state = logic.get_state_action(user_id)

    # Если главный админ в режиме notify_update
    if state == "notify_update" and user_id == MAIN_ADMIN_ID:
        logic.handle_broadcast_text(message)
        return

    # Логика FSM
    if state == "add_code":
        data = logic.get_state_data(user_id)
        if "name" not in data:
            logic.handle_add_code_name(message)
            return
        if "subcategory" in data and "description" not in data:
            logic.handle_add_code_description(message)
            return
        if "photo_path" in data and "price" not in data:
            logic.handle_add_code_price(message)
            return

    if state == "admin_approve_user":
        logic.handle_admin_approve_user_input(message)
        return

    if state == "enter_fio":
        logic.handle_user_fio_input(message)
        return

    # Иначе — кнопка главного меню
    logic.handle_main_menu_message(message)

@bot.message_handler(content_types=["photo"])
def on_photo(message: telebot.types.Message):
    user_id = message.from_user.id
    state = logic.get_state_action(user_id)
    data = logic.get_state_data(user_id)

    if state == "add_code" and data.get("description") and "photo_path" not in data:
        logic.handle_add_code_photo(message)
    else:
        bot.send_message(user_id, "Фото не к месту. Используйте меню.")

@bot.message_handler(content_types=["document"])
def on_document(message: telebot.types.Message):
    user_id = message.from_user.id
    state = logic.get_state_action(user_id)
    data = logic.get_state_data(user_id)

    if state == "add_code" and "price" in data and "file_path" not in data:
        logic.handle_add_code_file(message)
    else:
        bot.send_message(user_id, "Документ не к месту. Используйте меню.")

@bot.callback_query_handler(func=lambda call: True)
def on_callback_query(call: telebot.types.CallbackQuery):
    data = call.data
    user_id = call.from_user.id

    # apply_admin
    if data == "apply_admin":
        logic.callback_apply_admin(call)

    # admin menu
    elif data == "admin_sales":
        logic.callback_admin_menu_sales(call)
    elif data == "admin_approve_user":
        logic.start_state(call.from_user.id, "admin_approve_user")
        bot.answer_callback_query(call.id, "Введите ID пользователя, чтобы сделать его младшим админом.", show_alert=True)
    elif data == "admin_paid_purchases":
        logic.callback_admin_paid_purchases(call)
    elif data == "admin_paid_prev":
        logic.callback_admin_paid_prev(call)
    elif data == "admin_paid_next":
        logic.callback_admin_paid_next(call)
    elif data == "admin_paid_noop":
        logic.callback_admin_paid_noop(call)

    # Оповестить об обновлении
    elif data == "notify_update":
        if user_id != MAIN_ADMIN_ID:
            bot.answer_callback_query(call.id, "Нет доступа (только для главного админа).", show_alert=True)
            return
        logic.start_broadcast_mode(user_id)
        bot.answer_callback_query(call.id)

    # ADD_CODE
    elif data.startswith("add_code_cat|"):
        logic.callback_add_code_category(call)
    elif data.startswith("add_code_subcat|"):
        logic.callback_add_code_subcategory(call)

    # SEARCH
    elif data == "search_all":
        # Общий поиск: показываем все товары без фильтра
        results = db_manager.execute(
            "SELECT code_id, name, category, subcategory, description, price, photo_path FROM codes WHERE is_sold=0",
            fetchall=True
        )
        if not results:
            bot.answer_callback_query(call.id, "Ничего не найдено.", show_alert=True)
            return
        # Сохраним в user_states
        logic.user_states[user_id]["search_results"] = results
        logic.user_states[user_id]["search_idx"] = 0
        # Отобразим первый результат
        logic.show_search_result(user_id, call.message.message_id)
        bot.answer_callback_query(call.id)

    elif data == "search_filters_start":
        # Пользователь хочет поиск с фильтрами
        # Попросим выбрать категорию
        markup = types.InlineKeyboardMarkup()
        for cat in CATEGORIES.keys():
            markup.add(types.InlineKeyboardButton(cat, callback_data=f"search_cat|{cat}"))
        markup.add(types.InlineKeyboardButton("Сбросить всё", callback_data="search_reset"))
        bot.edit_message_text(
            "Выберите категорию:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)

    elif data.startswith("search_cat|"):
        logic.callback_search_category(call)
    elif data.startswith("search_subcat|"):
        logic.callback_search_subcategory(call)
    elif data == "search_confirm_subcat":
        logic.callback_search_confirm_subcat(call)
    elif data.startswith("search_price|"):
        logic.callback_search_price_filter(call)
    elif data == "search_reset":
        logic.callback_search_reset(call)
    elif data == "search_start":
        logic.callback_search_start(call)
    elif data in ["search_prev", "search_next"]:
        logic.callback_search_nav(call)
    elif data == "search_noop":
        logic.callback_search_noop(call)

    # FAVORITES
    elif data.startswith("remove_fav|"):
        logic.callback_remove_fav(call)
    elif data.startswith("add_fav|"):
        logic.callback_add_fav(call)

    # BUY
    elif data.startswith("user_buy|"):
        logic.callback_user_buy(call)
    elif data.startswith("user_confirm_pay|"):
        logic.callback_user_confirm_pay(call)

    # ADMIN approve/reject payment
    elif data.startswith("admin_approve_pay|"):
        logic.callback_admin_approve_pay(call)
    elif data.startswith("admin_reject_pay|"):
        logic.callback_admin_reject_pay(call)

    else:
        bot.answer_callback_query(call.id, "Неизвестное действие.")

if __name__ == "__main__":
    print("Bot is running...")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        logging.error(f"Bot crashed with error: {str(e)}")
        traceback.print_exc()
