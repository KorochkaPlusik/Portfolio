// routes/whatsapp.routes.js
const express = require('express');
const multer  = require('multer');
const upload  = multer({ dest: 'uploads/' });

const {
  getGroups,
  sendMessage,
  newAccountQr,
  getQrImage,
} = require('../controllers/whatsapp.controller');

const router = express.Router();

// Варианты через query-параметры (account_id в query)
router.get('/groups',                      getGroups);
router.post('/send',        upload.single('photo'), sendMessage);
router.get('/new_account_qr',              newAccountQr);
router.get('/qr_image',                    getQrImage);

// То же самое, но с account_id в URL
router.get('/:account_id/groups',          getGroups);
router.post('/:account_id/send', upload.single('photo'), sendMessage);
router.get('/:account_id/new_account_qr',  newAccountQr);
router.get('/:account_id/qr_image',        getQrImage);

module.exports = router;
