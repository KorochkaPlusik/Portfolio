// services/adminService.js
const db = require('../config/db');

exports.getAdminByEmail = async (email) => {
  return new Promise((resolve, reject) => {
    const query = `SELECT * FROM admins WHERE email = ?`;
    db.get(query, [email], (err, row) => {
      if (err) {
        return reject(err);
      }
      resolve(row);
    });
  });
};
