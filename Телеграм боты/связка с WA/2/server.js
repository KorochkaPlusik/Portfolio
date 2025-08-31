// server.js
const express = require('express');
const cors    = require('cors');
const path    = require('path');

const whatsappRoutes = require('./routes/whatsapp.routes');
const parseRoutes    = require('./routes/parse.routes');
const systemRoutes   = require('./routes/system.routes');

const app = express();

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// API-маршруты
app.use('/api/whatsapp', whatsappRoutes);
app.use('/api/parse',    parseRoutes);
app.use('/api/system',   systemRoutes);

// Централизованный обработчик ошибок
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(err.status || 500).json({ status: 'error', error: err.message });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`🚀 Server listening on http://localhost:${PORT}`);
});
