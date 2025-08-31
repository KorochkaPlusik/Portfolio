// services/requestService.js
const db = require('../config/db');

exports.createRequest = async ({ name, phone }) => {
  return new Promise((resolve, reject) => {
    const query = `INSERT INTO requests (name, phone) VALUES (?, ?)`;
    db.run(query, [name, phone], function(err) {
      if (err) {
        console.error('Ошибка при вставке заявки:', err.message);
        return reject(err);
      }
      resolve({ id: this.lastID, name, phone });
    });
  });
};

exports.getRequests = async () => {
  return new Promise((resolve, reject) => {
    const query = `SELECT * FROM requests ORDER BY created_at DESC`;
    db.all(query, [], (err, rows) => {
      if (err) {
        console.error('Ошибка при получении заявок:', err.message);
        return reject(err);
      }
      resolve(rows);
    });
  });
};
