const express = require('express');
const router = express.Router();
const chatController = require('../controllers/chat.controller');

router.get('/:email', chatController.getMessages);   // Получить все сообщения по email
router.post('/', chatController.sendMessage);        // Отправить сообщение

module.exports = router;
