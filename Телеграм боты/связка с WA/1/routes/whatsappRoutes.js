// whatsappRoutes.js — роуты для WhatsApp API
const express = require('express');
const router = express.Router();
const whatsappController = require('../controllers/whatsappController');

// POST /send — отправить сообщения по номерам
router.post('/send', whatsappController.sendMessages);

// POST /change-account — сменить аккаунт WhatsApp
router.post('/change-account', whatsappController.changeAccount);

// GET /status — получить статус сессии WhatsApp
router.get('/status', whatsappController.getStatus);

// POST /register-tg-webhook — установить токен и chat_id Telegram
router.post('/register-tg-webhook', whatsappController.registerTgWebhook);

// POST /change-proxy — сменить SOCKS5-прокси
router.post('/change-proxy', whatsappController.changeProxy);

// POST /clear-session — очистить сессию WhatsApp
router.post('/clear-session', whatsappController.clearSession);

// POST /stop-broadcast — остановить текущую рассылку
router.post('/stop-broadcast', whatsappController.stopBroadcast);

// GET /session-status — получить детальный статус сессии
router.get('/session-status', whatsappController.getSessionStatus);

module.exports = router
router.post('/broadcast', whatsappController.broadcast);
