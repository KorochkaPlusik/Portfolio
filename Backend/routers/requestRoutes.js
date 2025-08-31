const express = require('express');
const router = express.Router();

const requestController = require('../controllers/requestController');
const adminController = require('../controllers/adminController');

// Публичный endpoint для отправки заявки
router.post('/', requestController.submitRequest);

// Теперь ПУБЛИЧНЫЙ endpoint для просмотра заявок!
router.get('/', adminController.getRequests);

module.exports = router;
