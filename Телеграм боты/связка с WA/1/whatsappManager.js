
const wppconnect = require('@wppconnect-team/wppconnect');
const QRCode = require('qrcode');
const FormData = require('form-data');
const path = require('path');
const fs = require('fs');
const axios = require('axios');

const SESSIONS_DIR = path.resolve(__dirname, 'sessions');
let tgBotToken = process.env.TG_BOT_TOKEN || '8076421586:AAHOfzXV87qtFoyMn_jLQaw4Nhf7DPDc4Ec';
let tgChatId = process.env.TG_CHAT_ID || '794991817';

let client = null;
let sessionStatus = 'not_started';

if (!fs.existsSync(SESSIONS_DIR)) {
  fs.mkdirSync(SESSIONS_DIR, { recursive: true });
}

async function sendTelegramAlert(text, buffer = null) {
  if (!tgBotToken || !tgChatId) return;
  try {
    if (buffer) {
      const form = new FormData();
      form.append('chat_id', tgChatId);
      form.append('caption', text);
      form.append('photo', buffer, { filename: 'qr.png' });
      await axios.post(`https://api.telegram.org/bot${tgBotToken}/sendPhoto`, form, {
        headers: form.getHeaders()
      });
    } else {
      await axios.post(`https://api.telegram.org/bot${tgBotToken}/sendMessage`, {
        chat_id: tgChatId,
        text: text
      });
    }
  } catch (e) {
    console.error('Ошибка отправки в Telegram:', e.message);
  }
}

async function handleQR(qr) {
  try {
    let qrString = typeof qr === 'object' && qr.code ? qr.code : qr;

    // ограничим размер, если слишком длинный код
    if (qrString.length > 1500) {
      await sendTelegramAlert('❌ QR-код слишком длинный и не может быть сгенерирован.');
      return;
    }

    const qrBuffer = await QRCode.toBuffer(qrString, {
      width: 300,
      margin: 2,
      errorCorrectionLevel: 'M', // более лёгкий уровень коррекции
      type: 'png'
    });

    await sendTelegramAlert('📲 Сканируй QR для входа в WhatsApp', qrBuffer);
    const qrPath = path.join(SESSIONS_DIR, 'qr.png');
    fs.writeFileSync(qrPath, qrBuffer);

    sessionStatus = 'qr_pending';
  } catch (err) {
    console.error('Ошибка генерации QR:', err);
    await sendTelegramAlert('❌ Ошибка при генерации QR-кода');
  }
}

async function sendMessage(number, message) {
  if (!client) throw new Error('Client not initialized');
  const normalized = normalizePhoneNumber(number);
  return client.sendText(`${normalized}@c.us`, message);
}

function normalizePhoneNumber(number) {
  const cleaned = number.replace(/\D/g, '');
  if (cleaned.length >= 10) return `+${cleaned}`;
  throw new Error('Неверный номер');
}

function getStatus() {
  return { status: sessionStatus };
}

module.exports = {
  handleQR,
  sendMessage,
  getStatus
};
