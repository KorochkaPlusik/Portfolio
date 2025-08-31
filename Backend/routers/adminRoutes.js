const express = require('express');
const router = express.Router();
const authController = require('../controllers/auth.controller');
const registerController = require('../controllers/register.controller');
const { authenticate } = require('../middleware/auth.middleware');

// Вход
router.post('/login', authController.login);

// Регистрация (только если уже вошёл как админ)
router.post('/register', authenticate, registerController.register);

// Выход
router.post('/logout', authenticate, authController.logout);

module.exports = router;
