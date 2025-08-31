// whatsappController.js — обработчики API для WhatsApp
const whatsapp = require('../whatsappManager');
const fs = require('fs');
const LIMIT_PER_DAY = 200;
const LIMIT_FILE = 'send_limit.json';

let isBroadcasting = false;
let shouldStopBroadcast = false;

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

function getLimitData() {
  try {
    return JSON.parse(fs.readFileSync(LIMIT_FILE, 'utf8'));
  } catch {
    return {};
  }
}

function saveLimitData(data) {
  fs.writeFileSync(LIMIT_FILE, JSON.stringify(data));
}

function getSentToday() {
  const data = getLimitData();
  const today = getToday();
  return data[today] || 0;
}

function addSentToday(count) {
  const data = getLimitData();
  const today = getToday();
  data[today] = (data[today] || 0) + count;
  saveLimitData(data);
}

// Отправка сообщений по списку номеров
exports.sendMessages = async (req, res) => {
  const { numbers, message } = req.body;
  if (!Array.isArray(numbers) || !message) {
    return res.status(400).json({ error: 'Invalid params: numbers (array) and message (string) required.' });
  }
  
  // Нормализация номеров
  const normalizedNumbers = [];
  const invalidNumbers = [];
  
  numbers.forEach(number => {
    try {
      normalizedNumbers.push(whatsapp.normalizePhoneNumber(number));
    } catch (e) {
      invalidNumbers.push({ number, error: e.message });
    }
  });
  
  // Лимит отправок
  const sentToday = getSentToday();
  const allowed = Math.max(0, LIMIT_PER_DAY - sentToday);
  const numbersToSend = normalizedNumbers.slice(0, allowed);
  
  if (numbersToSend.length === 0) {
    return res.status(429).json({ 
      error: `Достигнут лимит ${LIMIT_PER_DAY} отправок на сегодня`,
      invalidNumbers
    });
  }
  
  try {
    const results = [];
    isBroadcasting = true;
    shouldStopBroadcast = false;
    
    for (let i = 0; i < numbersToSend.length; i++) {
      if (shouldStopBroadcast) {
        results.push({ 
          number: numbersToSend[i], 
          status: 'stopped', 
          error: 'Рассылка остановлена пользователем' 
        });
        continue;
      }
      
      try {
        await whatsapp.sendMessage(numbersToSend[i], message);
        results.push({ number: numbersToSend[i], status: 'sent' });
      } catch (e) {
        results.push({ 
          number: numbersToSend[i], 
          status: 'error', 
          error: e.message 
        });
      }
      
      // Случайная задержка 45-120 секунд
      if (i < numbersToSend.length - 1) {
        const delay = 45000 + Math.floor(Math.random() * 75000);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    
    isBroadcasting = false;
    addSentToday(results.filter(r => r.status === 'sent').length);
    
    // Добавляем невалидные номера в результаты
    invalidNumbers.forEach(item => {
      results.push({ number: item.number, status: 'invalid', error: item.error });
    });
    
    // Добавляем номера, не попавшие в рассылку из-за лимита
    if (normalizedNumbers.length > allowed) {
      for (let i = allowed; i < normalizedNumbers.length; i++) {
        results.push({ 
          number: normalizedNumbers[i], 
          status: 'skipped', 
          error: 'Лимит на сегодня исчерпан' 
        });
      }
    }
    
    res.json({ results });
  } catch (e) {
    isBroadcasting = false;
    res.status(500).json({ error: 'Internal error: ' + e.message });
  }
};

// Остановить рассылку
exports.stopBroadcast = (req, res) => {
  if (!isBroadcasting) {
    return res.json({ status: 'not_broadcasting' });
  }
  shouldStopBroadcast = true;
  res.json({ status: 'stopping' });
};

// Смена аккаунта WhatsApp
exports.changeAccount = (req, res) => {
  try {
    whatsapp.changeAccount();
    res.json({ status: 'restarted' });
  } catch (e) {
    res.status(500).json({ error: 'Failed to change account: ' + e.message });
  }
};

// Получить статус сессии WhatsApp
exports.getStatus = (req, res) => {
  try {
    res.json(whatsapp.getStatus());
  } catch (e) {
    res.status(500).json({ error: 'Failed to get status: ' + e.message });
  }
};

// Установить токен и chat_id Telegram
exports.registerTgWebhook = (req, res) => {
  const { token, chat_id } = req.body;
  if (!token || !chat_id) {
    return res.status(400).json({ error: 'Invalid params: token and chat_id required.' });
  }
  try {
    whatsapp.setTelegramConfig(token, chat_id);
    res.json({ status: 'ok' });
  } catch (e) {
    res.status(500).json({ error: 'Failed to set Telegram config: ' + e.message });
  }
};

// Сменить прокси
exports.changeProxy = async (req, res) => {
  try {
    // URL внешнего API для получения прокси
    const apiUrl = process.env.PROXY_API_URL || 'http://localhost:8080/get-proxy';
    const resp = await fetch(apiUrl);
    if (!resp.ok) throw new Error('Ошибка получения прокси: ' + resp.statusText);
    
    const proxyConfig = await resp.json();
    if (!proxyConfig.proxy_ip || !proxyConfig.proxy_port) {
      return res.status(500).json({ error: 'Некорректный ответ от API прокси' });
    }
    
    whatsapp.changeProxy(proxyConfig);
    res.json({ status: 'ok', proxy: proxyConfig });
  } catch (e) {
    res.status(500).json({ error: 'Ошибка смены прокси: ' + e.message });
  }
};
// Получить детальный статус сессии
exports.getSessionStatus = (req, res) => {
  try {
    const status = whatsapp.getStatus();
    res.json({
      authenticated: status.authenticated,
      ready: status.ready,
      blocked: status.blocked
    });
  } catch (e) {
    res.status(500).json({ error: 'Failed to get session status: ' + e.message });
  }
};
// Очистить сессию WhatsApp
exports.clearSession = (req, res) => {
  try {
    whatsapp.clearSession();
    res.json({ status: 'ok' });
  } catch (e) {
    res.status(500).json({ error: 'Ошибка очистки сессии: ' + e.message });
  }
};


exports.broadcast = async (req, res) => {
  const { numbers, message } = req.body;

  if (!Array.isArray(numbers) || typeof message !== 'string') {
    return res.status(400).json({ error: 'Invalid input' });
  }

  const { sendMessage } = require('../whatsappManager');
  const results = [];

  for (const number of numbers) {
    try {
      await sendMessage(number, message);
      results.push({ number, status: 'sent' });
    } catch (err) {
      results.push({ number, status: 'failed', error: err.message });
    }
  }

  res.json({ results });
};
