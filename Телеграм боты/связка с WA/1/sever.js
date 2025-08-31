// server.js — основной сервер Express для WhatsApp API
const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const whatsappRoutes = require('./routes/whatsappRoutes');
const whatsapp = require('./whatsappManager');

const app = express();
const PORT = 5000;

app.use(cors());
app.use(bodyParser.json());

// Подключаем роуты WhatsApp API
app.use('/', whatsappRoutes);

// Глобальный обработчик ошибок
app.use((err, req, res, next) => {
  console.error('Server error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

// Функция для запуска WhatsApp сессии
function startWhatsappSession() {
  whatsapp.startSession((reason) => {
    console.log(`Session blocked: ${reason}`);
    sendTelegramAlert(`⚠️ WhatsApp сессия прервана: ${reason}`);
    
    // Перезапуск через 30 секунд после блокировки
    setTimeout(startWhatsappSession, 30000);
  });
}

app.listen(PORT, () => {
  console.log(`Server started on port ${PORT}`);
  startWhatsappSession();
});