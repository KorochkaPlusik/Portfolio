// src/pages/Containers.js
import React, { useState } from 'react';
import './Containers.css';

const Containers = () => {
  const [formData, setFormData] = useState({ name: '', phone: '' });
  const [responseMsg, setResponseMsg] = useState('');

  const handleChange = e =>
    setFormData(prev => ({ ...prev, [e.target.name]: e.target.value }));

  const handleSubmit = async e => {
    e.preventDefault();
    try {
      const res = await fetch('/api/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...formData, tab: 'containers' }),
      });
      const data = await res.json();
      if (res.ok) {
        setResponseMsg(data.message || 'Заявка успешно отправлена!');
        setFormData({ name: '', phone: '' });
      } else {
        setResponseMsg(data.message || 'Ошибка при отправке');
      }
    } catch {
      setResponseMsg('Ошибка подключения к серверу');
    }
  };

  return (
    <div className="containers-page">
      {/* Шапка */}
      <header className="containers-header">
        <div className="header-overlay">
          <h1>Грузы до 5 тонн</h1>
          <p></p>
        </div>
      </header>
      {/* Форма заявки */}
      <section className="containers-request">
        <div className="container">
          <h2>Оставьте заявку на перевозку</h2>
          <p>Наш менеджер свяжется для уточнения деталей</p>
          <form className="request-form" onSubmit={handleSubmit}>
            <input
              type="text"
              name="name"
              placeholder="Ваше имя"
              value={formData.name}
              onChange={handleChange}
              required
            />
            <input
              type="tel"
              name="phone"
              placeholder="Ваш телефон"
              value={formData.phone}
              onChange={handleChange}
              required
            />
            <button type="submit">Отправить заявку</button>
          </form>
          {responseMsg && <p className="response-message">{responseMsg}</p>}
          <p className="disclaimer">
            Нажимая «Отправить», вы соглашаетесь на обработку персональных данных
          </p>
        </div>
      </section>
      {/* Информация */}
      <section className="containers-info">
        <div className="container">
          {/* Основные характеристики груза */}
          <div className="cargo-info">
            <h2>Какой груз берем?</h2>
            <p>
              Максимальный вес груза — 5 тонн{'\n'}
              Габариты — 5,8 × 7,3{'\n'}
              Полезный объем — 45 м³{'\n'}
              Вместительность — 12–18 европалет
            </p>
          </div>

          {/* Тип кузова */}
          <div className="type-body">
            <h3>Тип кузова:</h3>
            <ul>
              <li>Фургон</li>
              <li>Тент</li>
              <li>Рефрижератор</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Преимущества */}
      <section className="containers-benefits">
        <div className="container">
          <h2>Преимущества нашей компании</h2>
          <div className="benefits-grid">
            <div className="benefit-item">
              <h3>Гибкая логистика</h3>
              <p>Маршруты под ваши задачи и сроки.</p>
            </div>
            <div className="benefit-item">
              <h3>Современный транспорт</h3>
              <p>Сертифицированные контейнеровозы.</p>
            </div>
            <div className="benefit-item">
              <h3>Страхование</h3>
              <p>Полная защита груза на всем пути.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Галерея */}
      <section className="containers-gallery">
        <div className="container">
          <h2>Наши работы</h2>
          <div className="gallery-grid">
            <div className="gallery-item gallery-photo-1">
              <p>Перевозка морских контейнеров</p>
            </div>
            <div className="gallery-item gallery-photo-2">
              <p>Современные контейнеровозы</p>
            </div>
            <div className="gallery-item gallery-photo-3">
              <p>Надёжная погрузка и крепление</p>
            </div>
          </div>
        </div>
      </section>
            <section className="contacts-section">
        <div className="container contacts-container">
          <div className="contacts-info">
            <div className="contact-item address">
              <span>Калужская область, Боровский район, п. Ворсино</span>
            </div>
            <div className="contact-item email">
              <span>amlogistic40@mail.ru</span>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
};

export default Containers;
