const db = require('../config/db');

// Получить все сообщения по email (и для админа, и для пользователя)
exports.getMessages = (req, res) => {
  const email = req.params.email;
  if (!email) return res.status(400).json({ error: 'Email обязателен' });

  db.all(
    `SELECT * FROM chats WHERE user_email = ? ORDER BY created_at ASC`,
    [email],
    (err, rows) => {
      if (err) return res.status(500).json({ error: err.message });
      res.json(rows);
    }
  );
};

// Отправка сообщения (через Postman или фронт)
exports.sendMessage = (req, res) => {
  const { user_email, message, sender } = req.body;
  if (!user_email || !message || !sender) {
    return res.status(400).json({ error: 'user_email, message и sender обязательны' });
  }

  const stmt = `INSERT INTO chats (user_email, message, sender) VALUES (?, ?, ?)`;
  db.run(stmt, [user_email, message, sender], function (err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ success: true, id: this.lastID });
  });
};
