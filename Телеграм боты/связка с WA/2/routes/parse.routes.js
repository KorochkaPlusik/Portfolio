// routes/parse.routes.js
const express = require('express');
const router  = express.Router();
const { fetch } = require('../controllers/parse.controllers');

router.get('/:account_id/messages', fetch);

module.exports = router;
