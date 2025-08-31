// controllers/adminController.js
const jwt = require('jsonwebtoken');
const adminService = require('../services/adminService');
const requestService = require('../services/requestService');

/**
 * Функция входа администратора.
 * Проверяет, что в теле запроса переданы email и password.
 * Затем получает данные администратора из БД через adminService.
 * Если учетные данные верны, генерирует JWT-токен и отправляет его клиенту.
 */
exports.adminLogin = async (req, res, next) => {
  try {
    const { email, password } = req.body;
    // Проверка обязательных полей
    if (!email || !password) {
      return res.status(400).json({ message: 'Email и пароль обязательны' });
    }
    // Получаем администратора по email из базы данных
    const admin = await adminService.getAdminByEmail(email);
    // Если администратор не найден или пароль не совпадает – возвращаем ошибку
    if (!admin || admin.password !== password) {
      return res.status(401).json({ message: 'Неверные учетные данные' });
    }
    // Генерация JWT-токена с полезной нагрузкой (email и id администратора)
    const token = jwt.sign(
      { email: admin.email, id: admin.id },
      process.env.ADMIN_JWT_SECRET,
      { expiresIn: '1h' }
    );
    // Отправляем ответ с токеном
    res.status(200).json({ message: 'Успешный вход', token });
  } catch (error) {
    next(error);
  }
};

/**
 * Функция для получения списка заявок.
 * Вызывается защищённым маршрутом (через middleware adminAuth).
 * Получает данные из базы через requestService и возвращает их клиенту.
 */
exports.getRequests = async (req, res, next) => {
  try {
    const requests = await requestService.getRequests();
    res.status(200).json({ requests });
  } catch (error) {
    next(error);
  }
};
