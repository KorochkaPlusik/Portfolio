// src/pages/Dangerous.js
import React, { useState } from 'react';
import './Dangerous.css';

const bodyTypes = [
  { name: 'Фургон', cssClass: 'body-photo-furgon' },
  { name: 'Тент', cssClass: 'body-photo-tent' },
  { name: 'Рефрижератор', cssClass: 'body-photo-refrigerator' },
  { name: 'Контейнеровоз', cssClass: 'body-photo-container' },
  { name: 'Шаланда', cssClass: 'body-photo-shalanda' },
];

const Dangerous = () => {
  const [formData, setFormData] = useState({ name: '', phone: '' });
  const [responseMsg, setResponseMsg] = useState('');
  const [activeIndex, setActiveIndex] = useState(null);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
       const response = await fetch('/api/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...formData, tab: 'dangerous' }),
      });

      const data = await response.json();
      if (response.ok) {
        setResponseMsg(data.message || 'Заявка отправлена!');
        setFormData({ name: '', phone: '' });
      } else {
        setResponseMsg(data.message || 'Ошибка при отправке');
      }
    } catch (err) {
      console.error(err);
      setResponseMsg('Ошибка подключения к серверу');
    }
  };

  const togglePhoto = (index) => {
    setActiveIndex(index === activeIndex ? null : index);
  };

  return (
    <div className="dangerous-container">
      {/* Заголовок */}
      <header className="dangerous-header">
        <div className="header-overlay">
          <h1>Еврофуры</h1>
        </div>
      </header>

      {/* Заявка */}
      <section className="dangerous-request">
        <div className="container">
          <h2>Оставьте заявку на перевозку опасных грузов</h2>
          <p>Наш менеджер свяжется с вами для уточнения деталей</p>
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
          <p className="disclaimer">Нажимая на кнопку, вы соглашаетесь на обработку персональных данных</p>
        </div>
      </section>

      {/* Параметры грузов */}
      <section className="dangerous-benefits">
        <div className="container">
          <h2>Какой груз берем?</h2>
          <div className="benefit-grid">
            <div className="benefit-item"><h3>Максимальный вес</h3><p>20 тонн</p></div>
            <div className="benefit-item"><h3>Габариты</h3><p>13,6 × 2,5 × 2,7 м</p></div>
            <div className="benefit-item"><h3>Полезный объём</h3><p>92 м³</p></div>
            <div className="benefit-item"><h3>Вместительность</h3><p>33 европаллеты</p></div>
          </div>
        </div>
      </section>

      {/* Галерея */}
      <section className="work-gallery">
        <div className="container">
          <h2>Наши работы</h2>
          <div className="gallery-grid">
            <div className="gallery-item galery-photo-1"><p>Упаковка химических веществ</p></div>
            <div className="gallery-item galery-photo-2"><p>Транспортировка опасных грузов</p></div>
            <div className="gallery-item galery-photo-3"><p>Погрузка на охраняемом складе</p></div>
          </div>
        </div>
      </section>

      {/* Тип кузова */}
      <section className="dangerous-info">
        <div className="container">
          <div className="type-body">
            <h3>Тип кузова:</h3>
            <ul>
              {bodyTypes.map((type, index) => (
                <li
                  key={index}
                  onClick={() => togglePhoto(index)}
                  className={activeIndex === index ? 'active' : ''}
                >
                  {type.name}
                </li>
              ))}
            </ul>
            {activeIndex !== null && (
              <div className={`body-photo ${bodyTypes[activeIndex].cssClass}`} />
            )}
          </div>
        </div>
      </section>

      {/* Особенности */}
      <section className="dangerous-details">
        <div className="container">
          <h2>Особенности перевозки опасных грузов</h2>
          <div className="details-grid">
            <div className="detail-item"><h3>Меры безопасности</h3><p>Контроль и аварийные протоколы на каждом этапе.</p></div>
            <div className="detail-item"><h3>Контроль качества</h3><p>Проверки, обучение и документация.</p></div>
            <div className="detail-item"><h3>Спецтранспорт</h3><p>Оборудованные средства для опасных грузов.</p></div>
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

export default Dangerous;
