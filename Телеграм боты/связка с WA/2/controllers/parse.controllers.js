// server/controllers/parse.controllers.js
const fs        = require('fs');
const fsPromises= fs.promises;
const path      = require('path');
const sharp     = require('sharp');
const ffmpeg    = require('fluent-ffmpeg');
const sqlite3   = require('sqlite3').verbose();

const { getClient, isClientReady } = require('../whatsappManager');

const STATE_FILE = path.resolve(__dirname, '..', 'parse_state.json');
const DB_FILE    = path.resolve(__dirname, '..', 'profiles_app.db');

// Ensure state file exists
let state = {};
try {
  state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
} catch {
  state = {};
}

// Wait until the WA client is ready or timeout
function waitForClientReady(id, timeout = 30000, interval = 500) {
  const start = Date.now();
  return new Promise(resolve => {
    const iv = setInterval(() => {
      if (isClientReady(id) || Date.now() - start > timeout) {
        clearInterval(iv);
        resolve(isClientReady(id));
      }
    }, interval);
  });
}

const NAME_AGE_RE = /(?:^|\s)([А-ЯЁA-Z][а-яёa-z]{1,14})[ ,]+(\d{2})(?=\D|$)/;
const MIN_AGE = 14, MAX_AGE = 60;

const db = new sqlite3.Database(DB_FILE);

exports.fetch = async (req, res, next) => {
  try {
    const { account_id } = req.params;
    if (!account_id) return res.status(400).json({ error: 'account_id required' });

    const client = await getClient(account_id);
    if (!(await waitForClientReady(account_id))) {
      return res.status(503).json({ error: 'WA client not ready. Please scan QR code.' });
    }

    const lastSeen = state[account_id] || 0;
    let   maxSeen  = lastSeen;
    const profiles = [];

    // Fetch all private chats
    const chats       = await client.getAllChats();
    const privateChats= chats.filter(c => !c.isGroup);

    for (const chat of privateChats) {
      // Load all messages and sort chronologically
      const jid  = chat.id._serialized;
      const msgs = await client.loadAndGetAllMessages(jid);
      msgs.sort((a, b) => a.timestamp - b.timestamp);

      for (const msg of msgs) {
        if (!msg.body || msg.timestamp <= lastSeen) continue;
        const match = msg.body.match(NAME_AGE_RE);
        if (!match) continue;

        const age = Number(match[2]);
        if (age < MIN_AGE || age > MAX_AGE) continue;

        const profile = {
          account_id,
          chat_id: jid,
          sender:  msg.from,
          content: msg.body,
          timestamp: msg.timestamp,
          name:    match[1].trim(),
          age,
          media:   []
        };

        // Process up to 10 media attachments after this message
        let savedCount = 0;
        for (const mmsg of msgs) {
          if (
            mmsg.timestamp <= lastSeen ||
            mmsg.timestamp < msg.timestamp ||
            savedCount >= 10 ||
            !mmsg.isMedia
          ) continue;

          try {
            const buffer = await client.decryptFile(mmsg);
            const [type, extRaw] = mmsg.mimetype.split('/');
            const ext = extRaw === 'jpeg' ? 'jpg' : extRaw;
            const outDir = path.resolve(
              __dirname, '..', 'public', 'profile_media',
              account_id, jid.replace(/@.+$/,'')
            );
            fs.mkdirSync(outDir, { recursive: true });

            const fileName = `${mmsg.id.id}_${savedCount}.${ext}`;
            const filePath = path.join(outDir, fileName);

            if (type === 'image') {
              const img = sharp(buffer);
              const meta = await img.metadata();
              await img
                .resize(Math.round(meta.width/2), Math.round(meta.height/2))
                .jpeg({ quality: 80 })
                .toFile(filePath);
            } else if (type === 'video') {
              const tmpPath = `${filePath}.tmp`;
              await fsPromises.writeFile(tmpPath, buffer);
              await new Promise((resolve, reject) => {
                ffmpeg(tmpPath)
                  .videoBitrate('50%')
                  .save(filePath)
                  .on('end', () => fs.unlinkSync(tmpPath) || resolve())
                  .on('error', reject);
              });
            } else {
              await fsPromises.writeFile(filePath, buffer);
            }

            profile.media.push(
              `/profile_media/${account_id}/${jid.replace(/@.+$/,'')}/${fileName}`
            );
            savedCount++;
          } catch (err) {
            console.warn(`[WARN] media processing failed: ${err.message}`);
          }
        }

        // Insert into SQLite
        db.run(
          `INSERT INTO profiles
            (account_id, chat_id, sender, content, timestamp, photo_path)
           VALUES (?, ?, ?, ?, ?, ?)`,
          [
            profile.account_id,
            profile.chat_id,
            profile.sender,
            profile.content,
            profile.timestamp,
            profile.media.join(',') || null
          ],
          err => { if (err) console.error('[DB ERROR]', err.message); }
        );

        profiles.push(profile);
        if (msg.timestamp > maxSeen) maxSeen = msg.timestamp;
      }
    }

    // Update and persist state
    if (maxSeen > lastSeen) {
      state[account_id] = maxSeen;
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2) + '\n');
    }

    res.json({ profiles });
  } catch (err) {
    console.error('[ERROR] parse.controllers.fetch:', err);
    next(err);
  }
};
