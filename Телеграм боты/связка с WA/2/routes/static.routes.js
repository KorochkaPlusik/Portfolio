// routes/static.routes.js
const express = require('express');
const path = require('path');
const router = express.Router();

// GET /
router.get('/', (_req, res) => {
  res.sendFile(path.join(__dirname, '..', 'public', 'index.html'));
});

// GET /favicon.ico
router.get('/favicon.ico', (_req, res) => {
  // if you have public/favicon.ico, express.static will serve it first
  // otherwise, return no content to avoid 404
  res.status(204).end();
});

// GET /robots.txt
router.get('/robots.txt', (_req, res) => {
  res.type('text/plain').send(`User-agent: *\nDisallow:`);
});

// GET /sitemap.xml
router.get('/sitemap.xml', (_req, res) => {
  res.sendFile(path.join(__dirname, '..', 'public', 'sitemap.xml'));
});

// GET /security.txt
router.get('/security.txt', (_req, res) => {
  res.sendFile(path.join(__dirname, '..', 'public', 'security.txt'));
});

module.exports = router;
