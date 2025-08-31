# --- Инструкция по Google Sheets ---
# Для работы с Google Sheets:
# 1. Перейдите на https://console.cloud.google.com/
# 2. Создайте проект, включите API Google Sheets и Google Drive.
# 3. Создайте сервисный аккаунт, скачайте credentials.json.
# 4. Добавьте email сервисного аккаунта в доступ к вашей таблице (как редактор).
# 5. Поместите credentials.json рядом с этим файлом.

import telebot
from telebot import types
import requests
import os
import io
import csv
import openpyxl
import re
from datetime import datetime
import sqlite3

API_TOKEN = os.getenv('TG_BOT_TOKEN') or '8076421586:AAHOfzXV87qtFoyMn_jLQaw4Nhf7DPDc4Ec'
SERVER_URL = 'http://localhost:5000'

bot = telebot.TeleBot(API_TOKEN)

DB_PATH = 'botik_data.sqlite3'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        numbers TEXT,
        failed_numbers TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        date TEXT,
        total INTEGER,
        sent INTEGER,
        failed INTEGER,
        text TEXT
    )''')
    conn.commit()
    conn.close()

def save_numbers(chat_id, numbers):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO users (chat_id, numbers, failed_numbers) VALUES (?, ?, COALESCE((SELECT failed_numbers FROM users WHERE chat_id=?), ?))',
              (chat_id, ','.join(numbers), chat_id, ''))
    conn.commit()
    conn.close()

def get_numbers(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT numbers FROM users WHERE chat_id=?', (chat_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0].split(',')
    return []

def save_failed_numbers(chat_id, failed_numbers):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET failed_numbers=? WHERE chat_id=?', (','.join(failed_numbers), chat_id))
    conn.commit()
    conn.close()

def get_failed_numbers(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT failed_numbers FROM users WHERE chat_id=?', (chat_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0].split(',')
    return []

def add_history(chat_id, date, total, sent, failed, text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO history (chat_id, date, total, sent, failed, text) VALUES (?, ?, ?, ?, ?, ?)',
              (chat_id, date, total, sent, failed, text))
    conn.commit()
    conn.close()

def get_history(chat_id, limit=5):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT date, total, sent, failed, text FROM history WHERE chat_id=? ORDER BY id DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_history_full(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT date, total, sent, failed, text FROM history WHERE chat_id=? ORDER BY id', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- Google Sheets ---
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GSHEETS_AVAILABLE = True
except ImportError:
    GSHEETS_AVAILABLE = False

# Главное меню
@bot.message_handler(commands=['start'])
def start_message(message):
    # Проверяем статус сессии WhatsApp
    try:
        resp = requests.get(f'{SERVER_URL}/session-status')
        if resp.ok:
            status = resp.json()
            if status.get('authenticated'):
                msg_status = '✅ WhatsApp уже авторизован!'
            else:
                msg_status = '⚠️ Требуется авторизация в WhatsApp. QR-код будет отправлен в течение минуты...'
        else:
            msg_status = '❌ Не удалось проверить статус сессии'
    except Exception as e:
        msg_status = f'❌ Ошибка при проверке статуса: {e}'
    
    # Создаем меню
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('Загрузить Google Таблицу', callback_data='upload_sheet'),
        types.InlineKeyboardButton('Загрузить файл (Excel/CSV)', callback_data='upload_file'),
        types.InlineKeyboardButton('Начать рассылку', callback_data='start_sending'),
        types.InlineKeyboardButton('Статус WhatsApp', callback_data='status'),
        types.InlineKeyboardButton('Сменить аккаунт WhatsApp', callback_data='change_account'),
        types.InlineKeyboardButton('Повторить по неотправленным', callback_data='retry_failed'),
        types.InlineKeyboardButton('История рассылок', callback_data='history'),
        types.InlineKeyboardButton('Сбросить историю и неотправленные', callback_data='reset_history_failed'),
        types.InlineKeyboardButton('Экспорт истории (CSV)', callback_data='export_history_csv'),
        types.InlineKeyboardButton('❌ Остановить рассылку', callback_data='stop_broadcast'),
        types.InlineKeyboardButton('🌐 Сменить прокси', callback_data='change_proxy'),
        types.InlineKeyboardButton('🧹 Очистить сессию', callback_data='clear_session'),
        types.InlineKeyboardButton('🔄 Проверить статус WhatsApp', callback_data='check_auth_status'),
        types.InlineKeyboardButton('⚙ Настройки', callback_data='settings')
    ]
    
    # Добавляем кнопки в меню (по 2 в ряд)
    for i in range(0, len(buttons), 2):
        if i+1 < len(buttons):
            markup.add(buttons[i], buttons[i+1])
        else:
            markup.add(buttons[i])
    
    # Отправляем сообщение со статусом и меню
    bot.send_message(message.chat.id, f"{msg_status}\n\nДобро пожаловать! Выберите действие:", reply_markup=markup)


# Обработка нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    if call.data == 'upload_sheet':
        bot.send_message(call.message.chat.id, 'Пришлите ссылку на Google Таблицу с номерами.')
        bot.register_next_step_handler(call.message, process_sheet_link)
    
    elif call.data == 'upload_file':
        bot.send_message(call.message.chat.id, 'Пришлите файл с номерами (Excel .xlsx или CSV).')
        bot.register_next_step_handler(call.message, process_file_upload)
    
    elif call.data == 'start_sending':
        bot.send_message(call.message.chat.id, 'Введите текст сообщения для рассылки:')
        bot.register_next_step_handler(call.message, process_message_text)
    
    elif call.data == 'status':
        try:
            resp = requests.get(f'{SERVER_URL}/session-status')
            if resp.ok:
                status = resp.json()
                if status.get('ready'):
                    msg = f"✅ WhatsApp готов к работе!"
                elif status.get('blocked'):
                    msg = "❌ Ваш аккаунт WhatsApp заблокирован!"
                else:
                    msg = "⚠️ WhatsApp не готов. Требуется авторизация."
            else:
                msg = '❌ Ошибка получения статуса сервера.'
        except Exception as e:
            msg = f'❌ Ошибка: {e}'
        
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg)
    
    elif call.data == 'change_account':
        try:
            resp = requests.post(f'{SERVER_URL}/change-account')
            if resp.ok:
                bot.send_message(call.message.chat.id, '🔄 Смена аккаунта инициирована. QR-код будет отправлен в течение минуты...')
            else:
                bot.send_message(call.message.chat.id, f'❌ Ошибка сервера: {resp.text}')
        except Exception as e:
            bot.send_message(call.message.chat.id, f'❌ Ошибка: {e}')
    
    elif call.data == 'retry_failed':
        failed_numbers = get_failed_numbers(call.message.chat.id)
        if not failed_numbers:
            bot.send_message(call.message.chat.id, 'ℹ️ Нет неотправленных номеров для повторной рассылки.')
        else:
            bot.send_message(call.message.chat.id, f'✉️ Введите текст сообщения для повторной рассылки по {len(failed_numbers)} неотправленным номерам:')
            bot.register_next_step_handler(call.message, lambda m: process_retry_failed(m, failed_numbers))
    
    elif call.data == 'history':
        history = get_history(call.message.chat.id)
        if not history:
            bot.send_message(call.message.chat.id, 'ℹ️ История рассылок пуста.')
        else:
            msg = '📊 Последние рассылки:\n'
            for i, h in enumerate(history, 1):
                msg += f"{i}) {h[0]} | Всего: {h[1]} | Отправлено: {h[2]} | Не отправлено: {h[3]}\nТекст: {h[4][:40]}...\n"
            bot.send_message(call.message.chat.id, msg)
    
    elif call.data == 'reset_history_failed':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM history WHERE chat_id=?', (call.message.chat.id,))
        c.execute('UPDATE users SET failed_numbers=NULL WHERE chat_id=?', (call.message.chat.id,))
        conn.commit()
        conn.close()
        bot.send_message(call.message.chat.id, '♻️ История рассылок и неотправленные номера сброшены.')
    
    elif call.data == 'export_history_csv':
        history = get_history_full(call.message.chat.id)
        if not history:
            bot.send_message(call.message.chat.id, 'ℹ️ История рассылок пуста.')
        else:
            try:
                output = io.BytesIO()
                writer = csv.writer(io.TextIOWrapper(output, encoding='utf-8'))
                writer.writerow(['Дата', 'Всего', 'Отправлено', 'Не отправлено', 'Текст'])
                for h in history:
                    writer.writerow([h[0], h[1], h[2], h[3], h[4]])
                
                output.seek(0)
                bot.send_document(
                    call.message.chat.id,
                    ('history.csv', output.getvalue())
                )
            except Exception as e:
                bot.send_message(call.message.chat.id, f'❌ Ошибка при экспорте: {e}')
    
    elif call.data == 'stop_broadcast':
        try:
            resp = requests.post(f'{SERVER_URL}/stop-broadcast')
            if resp.ok:
                status = resp.json().get('status')
                if status == 'stopping':
                    bot.send_message(call.message.chat.id, '⏹️ Рассылка будет остановлена в ближайшее время.')
                elif status == 'not_broadcasting':
                    bot.send_message(call.message.chat.id, 'ℹ️ Сейчас нет активной рассылки.')
                else:
                    bot.send_message(call.message.chat.id, f'ℹ️ Статус: {status}')
            else:
                bot.send_message(call.message.chat.id, f'❌ Ошибка сервера: {resp.text}')
        except Exception as e:
            bot.send_message(call.message.chat.id, f'❌ Ошибка: {e}')
    
    elif call.data == 'change_proxy':
        try:
            resp = requests.post(f'{SERVER_URL}/change-proxy')
            if resp.ok:
                data = resp.json()
                if data.get('status') == 'ok':
                    proxy = data.get('proxy', {})
                    msg = f"🌐 Прокси успешно сменён!\nIP: {proxy.get('proxy_ip')}:{proxy.get('proxy_port')}"
                else:
                    msg = f"ℹ️ Ответ сервера: {data}"
            else:
                msg = f"❌ Ошибка сервера: {resp.text}"
            bot.send_message(call.message.chat.id, msg)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Ошибка: {e}")
    
    elif call.data == 'clear_session':
        try:
            resp = requests.post(f'{SERVER_URL}/clear-session')
            if resp.ok:
                bot.send_message(call.message.chat.id, '🧹 Сессия очищена. QR-код для авторизации будет отправлен в течение минуты...')
            else:
                bot.send_message(call.message.chat.id, f'❌ Ошибка сервера: {resp.text}')
        except Exception as e:
            bot.send_message(call.message.chat.id, f'❌ Ошибка: {e}')
    
    elif call.data == 'settings':
        bot.send_message(call.message.chat.id, 
            '⚙️ Настройки:\n'
            '- Лимит отправок: 200 в сутки\n'
            '- Задержка между сообщениями: 45-120 сек\n'
            '- Прокси: можно сменить через меню\n'
            '- Для расширенных настроек используйте команду /start'
        )

# Загрузка Google Sheets
def process_sheet_link(message):
    link = message.text.strip()
    if not GSHEETS_AVAILABLE:
        bot.send_message(message.chat.id, 'Для работы с Google Sheets установите библиотеки gspread и oauth2client!')
        return
    # Парсим ID таблицы
    match = re.search(r'/d/([\w-]+)', link)
    if not match:
        bot.send_message(message.chat.id, 'Не удалось определить ID таблицы. Проверьте ссылку!')
        return
    sheet_id = match.group(1)
    try:
        scope = 'https://spreadsheets.google.com/feeds https://www.googleapis.com/auth/drive'
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scopes=scope)
        client = gspread.authorize(creds)  # type: ignore
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.get_worksheet(0)
        numbers = []
        for row in worksheet.get_all_values():
            for cell in row:
                num = ''.join(filter(str.isdigit, cell))
                if len(num) >= 10:
                    numbers.append(num)
        if numbers:
            save_numbers(message.chat.id, numbers)
            bot.send_message(message.chat.id, f'Номера успешно загружены из Google Таблицы! Всего номеров: {len(numbers)}')
        else:
            bot.send_message(message.chat.id, 'Не удалось найти номера в таблице.')
    except Exception as e:
        bot.send_message(message.chat.id, f'Ошибка при работе с Google Sheets: {e}')

# Загрузка файла с номерами
def process_file_upload(message):
    if not message.document:
        bot.send_message(message.chat.id, 'Пожалуйста, отправьте файл (Excel .xlsx или CSV).')
        return
    file_info = bot.get_file(message.document.file_id)
    if not file_info.file_path:
        bot.send_message(message.chat.id, 'Ошибка: не удалось получить путь к файлу.')
        return
    downloaded_file = bot.download_file(file_info.file_path)
    numbers = []
    if message.document.file_name.endswith('.csv'):
        f = io.StringIO(downloaded_file.decode('utf-8'))
        reader = csv.reader(f)
        for row in reader:
            for cell in row:
                num = ''.join(filter(str.isdigit, cell))
                if len(num) >= 10:
                    numbers.append(num)
    elif message.document.file_name.endswith('.xlsx'):
        f = io.BytesIO(downloaded_file)
        wb = openpyxl.load_workbook(f)
        ws = wb.active
        if ws:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell:
                        num = ''.join(filter(str.isdigit, str(cell)))
                        if len(num) >= 10:
                            numbers.append(num)
    else:
        bot.send_message(message.chat.id, 'Формат файла не поддерживается. Используйте .xlsx или .csv')
        return
    if numbers:
        save_numbers(message.chat.id, numbers)
        bot.send_message(message.chat.id, f'Номера успешно загружены! Всего номеров: {len(numbers)}')
    else:
        bot.send_message(message.chat.id, 'Не удалось найти номера в файле.')

# Ввод текста сообщения и запуск рассылки
def process_message_text(message):
    text = message.text.strip()
    numbers = get_numbers(message.chat.id)
    if not numbers:
        bot.send_message(message.chat.id, 'Сначала загрузите Google Таблицу или файл с номерами!')
        return
    # Показываем подтверждение перед рассылкой
    preview = text[:60] + ('...' if len(text) > 60 else '')
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✅ Подтвердить рассылку', callback_data=f'confirm_send'))
    markup.add(types.InlineKeyboardButton('❌ Отмена', callback_data=f'cancel_send'))
    bot.send_message(
        message.chat.id,
        f'Вы собираетесь отправить сообщение {len(numbers)} номерам.\n\nТекст сообщения:\n"{preview}"\n\nПодтвердите рассылку:',
        reply_markup=markup
    )
    # Сохраняем текст сообщения во временное хранилище
    save_numbers(message.chat.id, numbers)  # на всякий случай
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS temp_send (chat_id INTEGER PRIMARY KEY, text TEXT)')
    c.execute('INSERT OR REPLACE INTO temp_send (chat_id, text) VALUES (?, ?)', (message.chat.id, text))
    conn.commit()
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data in ['confirm_send', 'cancel_send'])
def confirm_send_callback(call):
    bot.answer_callback_query(call.id)  # <-- обязательно!
    if call.data == 'cancel_send':
        bot.send_message(call.message.chat.id, 'Рассылка отменена.')
        # Очищаем временное сообщение
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM temp_send WHERE chat_id=?', (call.message.chat.id,))
        conn.commit()
        conn.close()
        return
    # confirm_send
    # Получаем текст сообщения из temp_send
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT text FROM temp_send WHERE chat_id=?', (call.message.chat.id,))
    row = c.fetchone()
    conn.close()
    if not row:
        bot.send_message(call.message.chat.id, 'Ошибка: не найден текст сообщения для рассылки.')
        return
    text = row[0]
    numbers = get_numbers(call.message.chat.id)
    resp = requests.post(f'{SERVER_URL}/send', json={'numbers': numbers, 'message': text})
    if resp.ok:
        results = resp.json().get('results', [])
        sent = sum(1 for r in results if r['status'] == 'sent')
        failed = [r['number'] for r in results if r['status'] != 'sent']
        save_failed_numbers(call.message.chat.id, failed)
        add_history(call.message.chat.id, datetime.now().strftime('%Y-%m-%d %H:%M'), len(numbers), sent, len(failed), text)
        msg = f'Отправлено: {sent}\nНе отправлено: {len(failed)}'
        if failed:
            msg += '\nНе отправленные номера: ' + ', '.join(failed)
        bot.send_message(call.message.chat.id, msg)
    else:
        bot.send_message(call.message.chat.id, 'Ошибка при рассылке!')
    # Очищаем временное сообщение
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM temp_send WHERE chat_id=?', (call.message.chat.id,))
    conn.commit()
    conn.close()

def process_retry_failed(message, failed_numbers):
    text = message.text.strip()
    if not failed_numbers:
        bot.send_message(message.chat.id, 'Нет неотправленных номеров для повторной рассылки.')
        return
    resp = requests.post(f'{SERVER_URL}/send', json={'numbers': failed_numbers, 'message': text})
    if resp.ok:
        results = resp.json().get('results', [])
        sent = sum(1 for r in results if r['status'] == 'sent')
        failed = [r['number'] for r in results if r['status'] != 'sent']
        save_failed_numbers(message.chat.id, failed)
        add_history(message.chat.id, datetime.now().strftime('%Y-%m-%d %H:%M'), len(failed_numbers), sent, len(failed), text)
        msg = f'Повторная рассылка завершена. Отправлено: {sent}\nНе отправлено: {len(failed)}'
        if failed:
            msg += '\nНе отправленные номера: ' + ', '.join(failed)
        bot.send_message(message.chat.id, msg)
    else:
        bot.send_message(message.chat.id, 'Ошибка при повторной рассылке!')
@bot.callback_query_handler(func=lambda call: call.data == 'check_auth_status')
def check_auth_status(call):
    try:
        resp = requests.get(f'{SERVER_URL}/session-status')
        if resp.ok:
            status = resp.json()
            if status.get('authenticated'):
                msg = '✅ WhatsApp авторизован и готов к работе!'
            elif status.get('blocked'):
                msg = '❌ Ваш аккаунт WhatsApp заблокирован!'
            else:
                msg = '⚠️ Требуется авторизация. QR-код будет отправлен в течение минуты...'
        else:
            msg = '❌ Не удалось проверить статус сессии'
    except Exception as e:
        msg = f'❌ Ошибка при проверке статуса: {e}'
    
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, msg)
# Webhook для оповещений от сервера (локально через polling)
from flask import Flask, request as flask_request
import threading

app = Flask(__name__)

@app.route('/notify', methods=['POST'])
def notify():
    data = flask_request.json
    chat_id = data.get('chat_id') if data else None
    reason = data.get('reason') if data else None
    if chat_id and reason:
        text = 'Внимание! Ваш аккаунт WhatsApp заблокирован или отключён.'
        bot.send_message(chat_id, text)
    return 'ok'

def run_flask():
    app.run(port=7000)

if __name__ == '__main__':
    init_db()
    # Регистрируем webhook на сервере
    import time
    def register_webhook():
        time.sleep(2)
        
        requests.post(f'{SERVER_URL}/register-tg-webhook', json={
            'url': 'http://localhost:7000/notify',
            'chat_id': 794991817  # <-- Заменить на свой chat_id
        })
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=register_webhook, daemon=True).start()
    bot.polling(none_stop=True)


@bot.message_handler(commands=['send'])
def handle_send(message):
    chat_id = message.chat.id
    text = message.text.replace('/send', '').strip()
    if not text:
        bot.reply_to(message, "❗️Введите текст сообщения после команды /send.")
        return

    numbers = get_numbers(chat_id)
    if not numbers:
        bot.reply_to(message, "❗️Сначала загрузите номера.")
        return

    bot.reply_to(message, f"📤 Отправляю {len(numbers)} номеров...")

    try:
        response = requests.post(f"{SERVER_URL}/api/whatsapp/broadcast", json={
            "numbers": numbers,
            "message": text
        })

        if response.status_code == 200:
            bot.send_message(chat_id, "✅ Сообщения отправлены.")
        else:
            bot.send_message(chat_id, f"❌ Ошибка сервера: {response.text}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка при обращении к серверу: {str(e)}")
