const db = require('../config/db');

exports.register = (req, res) => {
  const { name, email, password } = req.body;

  // Проверка на пустые поля
  if (!name || !email || !password) {
    return res.status(400).json({ error: 'Имя, email и пароль обязательны' });
  }

  // Проверка, существует ли уже пользователь с таким email
  db.get(`SELECT * FROM users WHERE email = ?`, [email], (err, existingUser) => {
    if (err) {
      console.error('Ошибка при проверке email:', err.message);
      return res.status(500).json({ error: 'Ошибка сервера при проверке email' });
    }

    if (existingUser) {
      return res.status(409).json({ error: 'Пользователь с таким email уже зарегистрирован' });
    }

    // Регистрация нового пользователя
    db.run(
      `INSERT INTO users (name, email, password) VALUES (?, ?, ?)`,
      [name, email, password],
      function(err) {
        if (err) {
          console.error('Ошибка при создании пользователя:', err.message);
          return res.status(500).json({ error: 'Ошибка сервера при регистрации' });
        }

        res.status(201).json({ message: 'Регистрация успешна', userId: this.lastID });
      }
    );
  });
};
