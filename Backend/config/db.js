const sqlite3 = require('sqlite3').verbose();
require('dotenv').config();

// Подключение к базе данных
const db = new sqlite3.Database('./database.sqlite', (err) => {
  if (err) {
    console.error('❌ Ошибка подключения к SQLite:', err.message);
    process.exit(1);
  }
  console.log('✅ Подключение к SQLite установлено');
});

db.serialize(() => {
  // ─────────────── Таблица заявок ───────────────
  db.run(`
    CREATE TABLE IF NOT EXISTS requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `, (err) => {
    if (err) console.error('❌ Ошибка создания таблицы requests:', err.message);
    else console.log('✅ Таблица requests готова');
  });
db.run(`
  CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    to_user TEXT NOT NULL,
    from_user TEXT NOT NULL,
    message TEXT NOT NULL,
    sender TEXT CHECK(sender IN ('user', 'admin')) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`, (err) => {
  if (err) console.error('❌ Ошибка создания таблицы chats:', err.message);
  else console.log('✅ Таблица chats готова');
});
  // ─────────────── Таблица пользователей ───────────────
  db.run(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE,
      password TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `, (err) => {
    if (err) console.error('❌ Ошибка создания таблицы users:', err.message);
    else console.log('✅ Таблица users готова');
  });

  // ─────────────── Таблица администраторов ───────────────
  db.run(`
    CREATE TABLE IF NOT EXISTS admins (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT DEFAULT 'Admin',
      email TEXT NOT NULL UNIQUE,
      password TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `, (err) => {
    if (err) {
      console.error('❌ Ошибка создания таблицы admins:', err.message);
      return;
    }

    console.log('✅ Таблица admins готова');

    // Проверка и автосоздание админа из .env
    const { ADMIN_EMAIL, ADMIN_PASSWORD } = process.env;
    if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
      console.warn('⚠️  Не указаны ADMIN_EMAIL или ADMIN_PASSWORD в .env — пропуск автосоздания');
      return;
    }

    db.get(`SELECT * FROM admins WHERE email = ?`, [ADMIN_EMAIL], (err, row) => {
      if (err) {
        console.error('❌ Ошибка при проверке администратора:', err.message);
      } else if (!row) {
        db.run(
          `INSERT INTO admins (email, password) VALUES (?, ?)`,
          [ADMIN_EMAIL, ADMIN_PASSWORD],
          function(err) {
            if (err) {
              console.error('❌ Ошибка при создании администратора:', err.message);
            } else {
              console.log(`✅ Администратор создан: ${ADMIN_EMAIL}`);
            }
          }
        );
      } else {
        console.log(`ℹ️ Администратор с email ${ADMIN_EMAIL} уже существует`);
      }
    });
  });
});

module.exports = db;
