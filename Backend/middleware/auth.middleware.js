const jwt = require('jsonwebtoken');

// Проверка наличия токена и его валидности
exports.authenticate = (req, res, next) => {
  const authHeader = req.headers.authorization;
  if (!authHeader) return res.status(401).json({ error: 'Нет токена' });

  const token = authHeader.split(' ')[1];
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    req.user = decoded; // содержит id, email, role
    next();
  } catch (err) {
    return res.status(403).json({ error: 'Неверный токен' });
  }
};

// Только для админов
exports.isAdmin = (req, res, next) => {
  if (req.user?.role !== 'admin') {
    return res.status(403).json({ error: 'Доступ только для администраторов' });
  }
  next();
};

// Только для обычных пользователей
exports.isUser = (req, res, next) => {
  if (req.user?.role !== 'user') {
    return res.status(403).json({ error: 'Доступ только для пользователей' });
  }
  next();
};
