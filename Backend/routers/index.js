const express = require('express');
const router = express.Router();

const adminRoutes = require('./adminRoutes');
const userRoutes = require('./userRoutes');
const requestRoutes = require('./requestRoutes');
const chatRoutes = require('./chat.routes'); // путь поправлен: убери "routes/", ты уже в этой папке

// Роуты
router.use('/admin', adminRoutes);        // /api/admin/*
router.use('/users', userRoutes);         // /api/users/*
router.use('/requests', requestRoutes);   // /api/requests/*
router.use('/chat', chatRoutes);          // /api/chat/*

module.exports = router;
