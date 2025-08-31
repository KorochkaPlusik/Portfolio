// routes/system.routes.js
const express = require('express');
const router  = express.Router();

// Публичные методы менеджера (должны уже экспортироваться из ../whatsappManager)
const {
  isClientReady,
  restartClient,
  getClient,
  getGroupList
} = require('../whatsappManager');

/**
 * Вспомогалка: получаем список аккаунтов из body/query
 * - body.ids: ["19","20"]
 * - query.ids=19,20
 * - иначе — ['default']
 */
function parseIds(req) {
  if (Array.isArray(req.body?.ids) && req.body.ids.length > 0) {
    return req.body.ids.map(String);
  }
  if (typeof req.query?.ids === 'string' && req.query.ids.trim()) {
    return req.query.ids.split(',').map(s => s.trim()).filter(Boolean);
  }
  return ['default'];
}

/**
 * GET /system/health
 * Быстрый health-чек без запуска клиентов.
 * query.ids=19,20 (опционально)
 */
router.get('/health', async (req, res) => {
  const ids = parseIds(req);
  const data = ids.map(id => ({
    id,
    state: isClientReady(id) ? 'READY' : 'NOT_READY'
  }));
  res.json({ ok: true, accounts: data });
});

/**
 * GET /system/status
 * Более подробный статус: пытается мягко дернуть getClient()
 * (если клиент уже поднят — вернёт объект, если нет — просто покажет ready=false)
 * query.ids=19,20 (опц.)
 */
router.get('/status', async (req, res) => {
  const ids = parseIds(req);
  const out = [];

  for (const id of ids) {
    const ready = isClientReady(id);
    let info = { id, ready };
    if (ready) {
      try {
        const client = await getClient(id);
        // минимальные сведения, без тяжёлых вызовов:
        if (client?.getHostDevice) {
          try { info.host = await client.getHostDevice(); } catch {}
        }
      } catch (e) {
        info.error = String(e?.message || e);
      }
    }
    out.push(info);
  }

  res.json({ ok: true, accounts: out });
});

/**
 * POST /system/restart
 * Триггерит рестарт для набора аккаунтов.
 * body: { ids?: string[], forceRelogin?: boolean }
 *   - forceRelogin=true: удалит токены (user-data не трогает), запросит новый QR
 */
router.post('/restart', async (req, res) => {
  const ids = parseIds(req);
  const forceRelogin = !!req.body?.forceRelogin;

  // Отвечаем сразу, рестарт делаем асинхронно
  res.json({ ok: true, status: 'restarting', ids, forceRelogin });

  for (const id of ids) {
    try {
      await restartClient(id, { forceRelogin });
      console.log(`[SYSTEM] scheduled restart for "${id}" (forceRelogin=${forceRelogin})`);
    } catch (e) {
      console.error(`[SYSTEM] restart error for "${id}":`, e);
    }
  }
});

/**
 * GET /system/groups
 * Быстро получить список групп для аккаунта (без 10-мин ожидания).
 * query.id=<accountId> (по умолчанию 'default')
 */
router.get('/groups', async (req, res) => {
  const id = (req.query?.id || 'default').toString();

  try {
    const groups = await getGroupList(id);
    res.json({ ok: true, id, count: groups.length, groups });
  } catch (e) {
    res.status(500).json({ ok: false, id, error: String(e?.message || e) });
  }
});

module.exports = router;
