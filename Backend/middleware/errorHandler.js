// middlewares/errorHandler.js
const errorHandler = (err, req, res, next) => {
    // Если заголовки уже отправлены, передаем ошибку дальше
    if (res.headersSent) {
      return next(err);
    }
  
    // Логирование ошибки
    console.error('Ошибка:', err);
  
    // Определяем HTTP-статус
    const statusCode = err.status || 500;
    res.status(statusCode);
  
    // Формирование ответа
    res.json({
      message: err.message || 'Внутренняя ошибка сервера',
      ...(process.env.NODE_ENV === 'development' && { stack: err.stack })
    });
  };
  
  module.exports = errorHandler;
  