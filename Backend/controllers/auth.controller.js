const db = require('../config/db');
const jwt = require('jsonwebtoken');

exports.login = (req, res) => {
  const { email, password } = req.body;

  // 1. Проверка админа
  db.get(`SELECT * FROM admins WHERE email = ?`, [email], (err, admin) => {
    if (err) return res.status(500).json({ error: 'Ошибка при проверке администратора' });

    if (admin && admin.password === password) {
      const token = jwt.sign(
        { id: admin.id, email: admin.email, role: 'admin' },
        process.env.JWT_SECRET,
        { expiresIn: '7d' }
      );

      return res.json({
        token,
        role: 'admin',
        name: admin.name || 'Admin',
        email: admin.email    // 🔥 добавлено
      });
    }

    // 2. Проверка обычного пользователя
    db.get(`SELECT * FROM users WHERE email = ?`, [email], (err, user) => {
      if (err) return res.status(500).json({ error: 'Ошибка при проверке пользователя' });

      if (!user || user.password !== password) {
        return res.status(401).json({ error: 'Неверный email или пароль' });
      }

      const token = jwt.sign(
        { id: user.id, email: user.email, role: 'user' },
        process.env.JWT_SECRET,
        { expiresIn: '7d' }
      );

      return res.json({
        token,
        role: 'user',
        name: user.name,
        email: user.email     // 🔥 добавлено
      });
    });
  });
};

exports.logout = (req, res) => {
  res.json({ message: 'Выход выполнен' });
};
