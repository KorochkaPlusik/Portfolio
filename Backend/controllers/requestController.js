// controllers/requestController.js
const requestService = require('../services/requestService');

exports.submitRequest = async (req, res, next) => {
  try {
    const { name, phone } = req.body;
    if (!name || !phone) {
      return res.status(400).json({ message: 'Имя и номер телефона обязательны' });
    }
    const newRequest = await requestService.createRequest({ name, phone });
    res.status(201).json({ message: 'Заявка успешно отправлена', request: newRequest });
  } catch (error) {
    next(error);
  }
};
