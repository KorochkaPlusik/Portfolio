// server/controllers/whatsapp.controller.js
const fs          = require('fs');
const fsPromises  = fs.promises;
const path        = require('path');
const {
  getClient,
  isClientReady,
} = require('../whatsappManager');

// ───────────────────────────────────────────────────────────
// Простая очередь на аккаунт (чтобы не долбить WA одновременно)
// ───────────────────────────────────────────────────────────
const QUEUES   = new Map();   // accountId → [ { fn, resolve, reject } ]
const LOCKS    = new Map();   // accountId → boolean
const DELAY_MS = 1000;        // ms между задачами в очереди

function enqueue(accountId, fn) {
  if (!QUEUES.has(accountId)) QUEUES.set(accountId, []);
  const queue = QUEUES.get(accountId);
  return new Promise((resolve, reject) => {
    queue.push({ fn, resolve, reject });
    processQueue(accountId);
  });
}

async function processQueue(accountId) {
  if (LOCKS.get(accountId)) return;
  const queue = QUEUES.get(accountId) || [];
  if (!queue.length) return;

  const task = queue.shift();
  LOCKS.set(accountId, true);
  try {
    const result = await task.fn();
    task.resolve(result);
  } catch (err) {
    task.reject(err);
  } finally {
    LOCKS.set(accountId, false);
    setTimeout(() => processQueue(accountId), DELAY_MS);
  }
}

async function waitReady(accountId, timeout = 30000, interval = 500) {
  const start = Date.now();
  while (!isClientReady(accountId) && Date.now() - start < timeout) {
    await new Promise(r => setTimeout(r, interval));
  }
  return isClientReady(accountId);
}

function normId(req) {
  return (req.params.account_id || req.query.account_id || '').trim() || 'default';
}

// ───────────────────────────────────────────────────────────
// Лёгкий кэш групп (TTL 60с) + дедупликация запроса в полёте
// ───────────────────────────────────────────────────────────
const GROUPS_CACHE  = new Map(); // accountId -> { at:number, data:Array, inflight:Promise|null }
const GROUPS_TTL_MS = 60 * 1000;

async function fetchGroupsFromWA(accountId) {
  const client = await getClient(accountId);
  const chats  = await client.listChats({ onlyGroups: true }).catch(() => []);
  return (chats || []).map(c => ({
    id:   (c.id?._serialized || c.id || '').toString().split('@')[0],
    name: (c.name || c.formattedTitle || 'Группа без имени').trim(),
  }));
}

async function getGroupsCached(accountId, { forceRefresh = false } = {}) {
  const entry = GROUPS_CACHE.get(accountId);
  const now   = Date.now();

  // свежий кэш
  if (!forceRefresh && entry && now - entry.at < GROUPS_TTL_MS) {
    return { data: entry.data, at: entry.at, fromCache: true };
  }

  // уже идёт обновление — дождёмся
  if (entry?.inflight) {
    await entry.inflight.catch(() => {});
    const fresh = GROUPS_CACHE.get(accountId);
    return { data: fresh?.data || [], at: fresh?.at || now, fromCache: false };
  }

  // запускаем загрузку (одна на аккаунт)
  const inflight = fetchGroupsFromWA(accountId)
    .then(data => {
      GROUPS_CACHE.set(accountId, { at: Date.now(), data, inflight: null });
      return data;
    })
    .catch(err => {
      if (entry) entry.inflight = null;
      throw err;
    });

  if (entry) {
    entry.inflight = inflight;
    // отдаём старые данные мгновенно, обновляемся в фоне
    return { data: entry.data, at: entry.at, fromCache: true };
  } else {
    GROUPS_CACHE.set(accountId, { at: 0, data: [], inflight });
    // первый запрос — дождёмся
    const data = await inflight;
    const fresh = GROUPS_CACHE.get(accountId);
    return { data: fresh?.data || data, at: fresh?.at || Date.now(), fromCache: false };
  }
}

function parseIntOr(def, v) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : def;
}

// ───────────────────────────────────────────────────────────
// GET /api/whatsapp/:account_id/groups  (?page, ?page_size, ?refresh=true)
// Быстро отдаёт 1000+ групп: лёгкий WA-вызов + TTL-кэш + пагинация
// ───────────────────────────────────────────────────────────
exports.getGroups = async (req, res) => {
  try {
    const accountId    = normId(req);
    if (!accountId) {
      return res.status(400).json({ status: 'error', error: 'account_id required' });
    }

    const page         = parseIntOr(1, req.query.page);
    const pageSize     = Math.min(500, parseIntOr(200, req.query.page_size)); // до 500 за раз
    const forceRefresh = String(req.query.refresh || '').toLowerCase() === 'true';

    await getClient(accountId).catch(() => {});
    if (!await waitReady(accountId)) {
      return res.status(202).json({
        status:  'pending',
        message: `WA client "${accountId}" not ready. Scan QR at /api/whatsapp/${accountId}/new_account_qr`
      });
    }

    const { data, at, fromCache } = await getGroupsCached(accountId, { forceRefresh });
    const total = data.length;
    const start = (page - 1) * pageSize;
    const slice = data.slice(start, start + pageSize);

    res.json({
      status: 'success',
      account_id: accountId,
      total,
      page,
      page_size: pageSize,
      from_cache: fromCache,
      refreshed_at: at,
      groups: slice
    });
  } catch (err) {
    console.error('getGroups error:', err);
    res.status(500).json({ status: 'error', error: err.message });
  }
};

// ───────────────────────────────────────────────────────────
// POST /api/whatsapp/:account_id/send  (form-data: photo? + message)
// ───────────────────────────────────────────────────────────
exports.sendMessage = async (req, res) => {
  let tmpPath = null;
  try {
    const accountId = normId(req);
    const chatId    = String(req.body.chat_id || '').trim();
    const message   = String(req.body.message || '').trim();

    if (!accountId || !chatId || !message) {
      return res.status(400).json({
        status: 'error',
        error:  'account_id, chat_id and message required'
      });
    }

    const jid = chatId.includes('@') ? chatId : `${chatId}@g.us`;
    if (req.file?.path) {
      tmpPath = req.file.path;
    }

    const result = await enqueue(accountId, async () => {
      if (!await waitReady(accountId)) {
        throw new Error(`WA client "${accountId}" not ready`);
      }
      const client = await getClient(accountId);

      if (tmpPath) {
        await client.sendFile(jid, tmpPath, path.basename(tmpPath), message);
      } else {
        await client.sendText(jid, message);
      }
      return { messageId: `${jid}_${Date.now()}` };
    });

    res.json({
      status:     'success',
      account_id: accountId,
      messageId:  result.messageId
    });
  } catch (err) {
    console.error('sendMessage error:', err);
    res.status(500).json({ status: 'error', error: err.message });
  } finally {
    if (tmpPath) {
      fsPromises.unlink(tmpPath).catch(() => {});
    }
  }
};

// ───────────────────────────────────────────────────────────
// GET /api/whatsapp/:account_id/new_account_qr
// НЕ ЖДЁМ QR — сразу 200/202, сам QR появится отдельно
// ───────────────────────────────────────────────────────────
exports.newAccountQr = async (req, res) => {
  const accountId = normId(req);
  if (!accountId) {
    return res.status(400).json({ status: 'error', error: 'account_id required' });
  }

  try {
    // Поднимаем/инициализируем клиента (catchQR сам сохранит PNG в /public)
    getClient(accountId).catch(e =>
      console.error(`[${accountId}] getClient error:`, e?.message || e)
    );

    if (isClientReady(accountId)) {
      return res.json({ status: 'ready', message: 'Client already authenticated' });
    }

    // Мгновенный ответ — фронт пусть опрашивает /qr_image
    return res.status(202).json({
      status:  'pending',
      message: 'QR generation started; poll /api/whatsapp/:account_id/qr_image'
    });
  } catch (err) {
    console.error('newAccountQr error:', err);
    return res.status(500).json({ status: 'error', error: err.message });
  }
};

// ───────────────────────────────────────────────────────────
// GET /api/whatsapp/:account_id/qr_image
// Быстрая выдача PNG или 404 pending
// ───────────────────────────────────────────────────────────
exports.getQrImage = async (req, res) => {
  try {
    const accountId = normId(req);
    if (!accountId) {
      return res.status(400).json({ status: 'error', error: 'account_id required' });
    }

    const pngPath = path.resolve(__dirname, '..', 'public', `qr_${accountId}.png`);
    if (!fs.existsSync(pngPath)) {
      return res.status(404).json({ status: 'pending', message: 'QR not ready' });
    }

    res.setHeader('Content-Type', 'image/png');
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).sendFile(pngPath);
  } catch (err) {
    console.error('getQrImage error:', err);
    return res.status(500).json({ status: 'error', error: err.message });
  }
};
