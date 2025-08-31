// whatsappManager.js

process.removeAllListeners('unhandledRejection');
process.on('unhandledRejection', reason => {
  const msg = reason?.message || String(reason);
  if (msg.includes('Protocol error: Connection closed')) {
    console.warn('[WA Manager] Suppressed Protocol error:', msg);
    return;
  }
  console.error('Unhandled Rejection in WA Manager:', reason);
});

const { create } = require('@wppconnect-team/wppconnect');
const puppeteer  = require('puppeteer');
const fs         = require('fs');
const path       = require('path');
const fetch      = require('node-fetch');
const FormData   = require('form-data');
const QRCode     = require('qrcode');
const sharp = require('sharp');

const fsPromises = fs.promises;

const BOT_TOKEN = '7648352866:AAHbns666v8TYvYLwFHLXrrtpJghwWkIeo4';
const CHAT_ID   = '7522950558';
const RETRY_DELAY  = 2000;
const MAX_RETRIES  = 2;

const SESSIONS_DIR = path.resolve(__dirname, 'sessions');
const PUBLIC_DIR   = path.resolve(__dirname, 'public');

fs.mkdirSync(SESSIONS_DIR, { recursive: true });
fs.mkdirSync(PUBLIC_DIR,   { recursive: true });

// ─────────── helpers & state ───────────
function sessionDirOf(accountId, sub = '') {
  return path.join(SESSIONS_DIR, accountId, sub);
}

const clients         = new Map(); // accountId -> client
const clientStatus    = new Map(); // 'initializing' | 'ready' | 'down'
const keepAliveTimers = new Map(); // accountId -> interval
const backoffInfo     = new Map(); // accountId -> { tries, timer }

// ─────────── telegram ───────────
async function sendToTelegram(text, buf = null) {
  const url = `https://api.telegram.org/bot${BOT_TOKEN}`;
  if (buf) {
    const form = new FormData();
    form.append('chat_id', CHAT_ID);
    form.append('caption', text);
    form.append('photo', buf, { filename: 'qr.png' });
    await fetch(`${url}/sendPhoto`, { method: 'POST', body: form });
  } else {
    await fetch(`${url}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: CHAT_ID, text })
    });
  }
}

// ─────────── QR: НЕ ТРОГАЕМ (как просил) ───────────
async function handleQR(input, accountId) {
  try {
    const { base64Qr, asciiQr, urlCode } =
      typeof input === 'object' ? input : { base64Qr: input };

    let qrValue = null;
    if (typeof urlCode === 'string' && urlCode.trim()) {
      qrValue = urlCode.trim();
    } else if (typeof asciiQr === 'string' && asciiQr.trim()) {
      qrValue = asciiQr.trim();
    }

    let finalBuf;

    if (qrValue) {
      // Рендерим чисто чёрно-белый QR
      const raw = await QRCode.toBuffer(qrValue, {
        type: 'png',
        errorCorrectionLevel: 'H',
        width: 900,              // крупный QR
        margin: 2,               // базовая «тихая зона»
        color: { dark: '#000000', light: '#FFFFFF' }
      });

      // Белая подложка + тонкая чёрная рамка, как на скрине
      finalBuf = await sharp(raw)
        .extend({ top: 60, bottom: 60, left: 60, right: 60, background: '#FFFFFF' }) // белые поля
        .extend({ top: 6, bottom: 6, left: 6, right: 6, background: '#000000' })     // чёрная рамка
        .png()
        .toBuffer();
    } else if (typeof base64Qr === 'string' && base64Qr.startsWith('data:image')) {
      // Фоллбэк, если вдруг не пришёл urlCode/ascii: превращаем присланное изображение в ч/б
      const base64 = base64Qr.replace(/^data:image\/\w+;base64,/, '');
      const buf    = Buffer.from(base64, 'base64');

      const bw = await sharp(buf)
        .resize({ width: 900, height: 900, fit: 'contain', background: '#FFFFFF' })
        .greyscale()
        .threshold(200)    // бинаризуем, чтобы был чистый чёрно-белый
        .png({ palette: true })
        .toBuffer();

      finalBuf = await sharp(bw)
        .extend({ top: 60, bottom: 60, left: 60, right: 60, background: '#FFFFFF' })
        .extend({ top: 6, bottom: 6, left: 6, right: 6, background: '#000000' })
        .png()
        .toBuffer();
    } else {
      throw new Error('Нет данных QR (urlCode/base64/ascii)');
    }

    const qrPath = path.join(PUBLIC_DIR, `qr_${accountId}.png`);
    await fsPromises.writeFile(qrPath, finalBuf);
    await sendToTelegram('📱 Отсканируйте этот QR-код', finalBuf);
  } catch (err) {
    console.error(`[${accountId}] ❌ Ошибка обработки QR:`, err);
    await sendToTelegram(`❌ Ошибка обработки QR для аккаунта ${accountId}: ${err.message}`);
  }
}


// ─────────── client factory ───────────
async function _createClient(accountId) {
  let lastError;

  fs.mkdirSync(sessionDirOf(accountId, 'tokens'),    { recursive: true });
  fs.mkdirSync(sessionDirOf(accountId, 'user-data'), { recursive: true });

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const client = await create({
        session: accountId,
        headless: true,
        autoClose: 0,
        restartOnCrash: true,

        folderNameToken: sessionDirOf(accountId, 'tokens'),
        puppeteer,
        puppeteerOptions: {
          userDataDir: sessionDirOf(accountId, 'user-data'),
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--no-first-run',
            '--no-default-browser-check'
          ],
          timeout: 900000
        },

        // получаем и рендерим Ч/Б QR
        catchQR: (base64Qr, asciiQr, attemptNo, urlCode) =>
          handleQR({ base64Qr, asciiQr, urlCode }, accountId),

        // ВАЖНО: считаем готовым не только isLogged
        statusFind: async (status) => {
          const s = String(status || '').toLowerCase();
          if (['islogged', 'connected', 'inchat', 'qrreadsuccess'].includes(s)) {
            if (clientStatus.get(accountId) !== 'ready') {
              clientStatus.set(accountId, 'ready');
              console.log(`[${accountId}] ✅ Ready via statusFind: ${status}`);
              try { await sendToTelegram(`✅ Аккаунт ${accountId} готов`); } catch {}
            }
          }
        },

        logQR: false
      });

      // Подстраховка по state-машине
      if (typeof client.onStateChange === 'function') {
        client.onStateChange(async (state) => {
          const st = String(state || '').toUpperCase();
          console.log(`[${accountId}] state: ${st}`);

          // Эти состояния считаем «готов»
          if (['CONNECTED', 'SYNCING', 'OPENING', 'PAIRING', 'MAIN'].includes(st)) {
            clientStatus.set(accountId, 'ready');
          }

          switch (st) {
            case 'CONFLICT':
              if (client.useHere) { try { await client.useHere(); } catch {} }
              break;
            case 'UNPAIRED':
            case 'UNPAIRED_IDLE':
              await restartClient(accountId, { forceRelogin: true, backoff: false });
              break;
            case 'DISCONNECTED':
            case 'UNLAUNCHED':
              scheduleBackoffRestart(accountId);
              break;
            default:
              break;
          }
        });
      }

      // keep-alive
      setupKeepAlive(accountId, client);

      // Ещё одна страховка: если API отвечает — ставим ready
      try {
        if (client.getHostDevice) { await client.getHostDevice(); clientStatus.set(accountId, 'ready'); }
      } catch (_) {}

      clients.set(accountId, client);
      clearBackoff(accountId);
      return client;

    } catch (err) {
      lastError = err;
      console.warn(
        `[${accountId}] ❌ Ошибка при создании (attempt ${attempt}/${MAX_RETRIES}): ${err?.message || err}`
      );
      if (attempt < MAX_RETRIES) await new Promise(r => setTimeout(r, RETRY_DELAY));
    }
  }

  clientStatus.set(accountId, 'down');
  throw lastError;
}


// ─────────── keep-alive ───────────
function setupKeepAlive(accountId, client) {
  if (keepAliveTimers.has(accountId)) {
    clearInterval(keepAliveTimers.get(accountId));
  }
  const t = setInterval(async () => {
    try {
      if (client.getBatteryLevel) await client.getBatteryLevel();
      else if (client.getHostDevice) await client.getHostDevice();
    } catch (e) {
      console.warn(`[${accountId}] keepalive failed: ${e?.message}`);
      scheduleBackoffRestart(accountId);
    }
  }, 90_000);
  keepAliveTimers.set(accountId, t);
}

function clearKeepAlive(accountId) {
  if (keepAliveTimers.has(accountId)) {
    clearInterval(keepAliveTimers.get(accountId));
    keepAliveTimers.delete(accountId);
  }
}

// ─────────── backoff restart ───────────
function scheduleBackoffRestart(accountId) {
  const info = backoffInfo.get(accountId) || { tries: 0, timer: null };
  if (info.timer) return; // уже запланирован

  info.tries = Math.min(info.tries + 1, 10);
  const delayMs = Math.min(15000 * Math.pow(2, info.tries - 1), 10 * 60 * 1000); // 15s → … → 10m

  info.timer = setTimeout(async () => {
    info.timer = null;
    await restartClient(accountId, { forceRelogin: false, backoff: true });
  }, delayMs);

  backoffInfo.set(accountId, info);
  console.warn(`[${accountId}] Планирую рестарт через ${Math.round(delayMs/1000)}s (try ${info.tries})`);
}

function clearBackoff(accountId) {
  const info = backoffInfo.get(accountId);
  if (info?.timer) clearTimeout(info.timer);
  backoffInfo.delete(accountId);
}

// ─────────── public api ───────────
async function getClient(accountId = 'default') {
  if (clients.has(accountId) && clientStatus.get(accountId) === 'ready') {
    return clients.get(accountId);
  }

  // если уже идёт инициализация: ждём появления клиента в Map, не логина
  if (clientStatus.get(accountId) === 'initializing') {
    while (!clients.has(accountId) && clientStatus.get(accountId) === 'initializing') {
      await new Promise(r => setTimeout(r, 300));
    }
    return clients.get(accountId);
  }

  clientStatus.set(accountId, 'initializing');
  const client = await _createClient(accountId);
  // здесь НЕ ставим 'ready' — это делает statusFind('isLogged')
  return client;
}



async function restartClient(accountId = 'default', opts = {}) {
  const { forceRelogin = false, backoff = false } = opts;

  try {
    clearKeepAlive(accountId);

    if (clients.has(accountId)) {
      try { await clients.get(accountId).close(); } catch {}
      clients.delete(accountId);
    }
  } catch {}

  clientStatus.set(accountId, 'down');

  // чистим только токены при форс-релогине, профиль оставляем
  if (forceRelogin) {
    try {
      fs.rmSync(sessionDirOf(accountId, 'tokens'), { recursive: true, force: true });
    } catch {}
  }

  if (!backoff) {
    clearBackoff(accountId);
  }

  setTimeout(() => {
    getClient(accountId).catch(e => {
      console.error(`[${accountId}] Ошибка при рестарте:`, e);
      scheduleBackoffRestart(accountId);
    });
  }, 1500);
}

// ─────────── groups ───────────
// ─────────── groups ───────────
async function getGroupList(accountId = 'default') {
  const client = await getClient(accountId);

  const MAX_ATTEMPTS      = 8;      // до 8 попыток
  const ATTEMPT_DELAY_MS  = 10_000; // по 10 секунд ожидания
  const UNNAMED_THRESHOLD = 0.20;   // терпим до 20% "без имени"

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      let groups;

      // сначала пробуем getAllGroups (надёжнее)
      if (typeof client.getAllGroups === 'function') {
        groups = await client.getAllGroups();
      } else {
        // fallback: listChats
        groups = await client.listChats({ onlyGroups: true });
      }

      const result = (groups || []).map(c => ({
        id:   (c.id?._serialized || c.id || '').toString().split('@')[0],
        name: (c.name || c.formattedTitle || 'Группа без имени').trim(),
      }));

      const unnamedCount = result.filter(c => c.name === 'Группа без имени').length;
      const unnamedRatio = unnamedCount / (result.length || 1);

      console.log(
        `[${accountId}] Попытка ${attempt}: групп=${result.length}, без имени=${unnamedCount} (${(unnamedRatio*100).toFixed(1)}%)`
      );

      // если мало групп или много "без имени" → ждём и повторяем
      if (attempt < MAX_ATTEMPTS && (result.length < 5 || unnamedRatio > UNNAMED_THRESHOLD)) {
        await new Promise(r => setTimeout(r, ATTEMPT_DELAY_MS));
        continue;
      }

      return result;
    } catch (err) {
      console.error(`[${accountId}] Ошибка получения групп (попытка ${attempt}):`, err?.message || err);
      if (attempt === MAX_ATTEMPTS) return [];
      await new Promise(r => setTimeout(r, ATTEMPT_DELAY_MS));
    }
  }

  return [];
}

// ─────────── helpers ───────────
function isClientReady(accountId = 'default') {
  return clientStatus.get(accountId) === 'ready';
}

// ─────────── exports ───────────
module.exports = {
  getClient,
  isClientReady,
  restartClient,
  getGroupList
};
