require('dotenv').config();
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const morgan = require('morgan');
const http = require('http');
const { Server } = require('socket.io');

const routes       = require('./routers/index');
const errorHandler = require('./middleware/errorHandler');
const db           = require('./config/db');

const app    = express();
const server = http.createServer(app);
const io     = new Server(server, { cors: { origin: '*' } });

const PORT = process.env.PORT || 5000;

// ─── Middleware ───────────────────────────────────────
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(
  process.env.NODE_ENV === 'development'
    ? morgan('dev')
    : morgan('combined')
);

// ─── API Routes ───────────────────────────────────────
app.use('/api', routes);

// ─── Error Handling ──────────────────────────────────
// Любые ошибки внутри /api попадут сюда и вернут JSON
app.use(errorHandler);

// ─── WebSocket (Socket.IO) ───────────────────────────
io.on('connection', (socket) => {
  console.log('🟢 Новый пользователь в чате:', socket.id);

  socket.on('join', (userId) => {
    socket.join(userId);
  });

  socket.on('chat message', ({ from, to, text }) => {
    if (!from || !to || !text) return;
    db.run(
      `INSERT INTO chat_messages (from_user, to_user, message) VALUES (?, ?, ?)`,
      [from, to, text],
      (err) => {
        if (err) console.error('❌ Ошибка записи чата в БД:', err.message);
      }
    );
    io.to(to).emit('chat message', { from, to, text });
    io.to(from).emit('chat message', { from, to, text });
  });

  socket.on('disconnect', () => {
    console.log('🔴 Пользователь отключился:', socket.id);
  });
});

// ─── Запуск сервера ───────────────────────────────────
server.listen(PORT, () => {
  console.log(`🚀 Сервер запущен на порту ${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  server.close(() => console.log('🛑 Сервер завершил работу'));
});
