// src/pages/Home.js
import React, { useState } from 'react';
import './Home.css';
import mapImage from '../pages/images/cart/cart.png'; // путь от текущего файла

const Home = () => {
  // Состояние для формы заявки
  const [formData, setFormData] = useState({ name: '', phone: '' });
  const [responseMsg, setResponseMsg] = useState('');

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch('/api/requests', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      const data = await response.json();

      if (response.ok) {
        setResponseMsg(data.message || 'Заявка успешно отправлена! Мы свяжемся с Вами в ближайшее время.');
        setFormData({ name: '', phone: '' });
      } else {
        setResponseMsg(data.message || 'Ошибка при отправке заявки');
      }
    } catch (error) {
      console.error('Ошибка:', error);
      setResponseMsg('Ошибка при отправке заявки');
    }
  };

  return (
    <div className="home-container">

      {/* Секция с формой заявки */}
      <section className="request-section">
        <div className="container">
          <h2>Нужна доставка? Оставьте заявку!</h2>
          <p>Оставьте заявку, и наш менеджер свяжется с Вами в ближайшее время</p>
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
            <button type="submit">ОТПРАВИТЬ ЗАЯВКУ</button>
          </form>
          {responseMsg && <p className="response-message">{responseMsg}</p>}
          <p className="disclaimer">
            Нажимая на кнопку, вы принимаете условия обработки персональных данных
          </p>
        </div>
      </section>
      {/* Большая информационная секция */}
      <section className="info-section">
        <div className="container">
          <h2>Подробная информация о наших услугах</h2>
          <p>
            Мы предоставляем полный комплекс логистических услуг, включая складское хранение  и страхование грузов. 
            Наш многолетний опыт и надёжные партнёры позволяют оптимизировать маршруты 
            и обеспечивать своевременную доставку в любую точку России и СНГ.
          </p>
          <p>
            Мы гарантирует индивидуальный подход к каждому клиенту, 
            высокий уровень сервиса и прозрачность всех процессов. 
            Мы ценим долгосрочные партнёрские отношения и всегда стремимся превзойти 
            ожидания наших заказчиков.
          </p>
          <ul>
            <li>Собственная сеть складов и перевалочных пунктов</li>
            <li>Гибкие тарифы и персональные предложения</li>
            <li>Страхование и полная ответственность за груз</li>
            <li>Оптимизация логистических процессов под нужды клиента</li>
          </ul>
        </div>
      </section>

      <section className="amlogistic-location">
        <div className="container">
          <div className="amlogistic-flex">
            <div className="amlogistic-left">
              <div className="amlogistic-logo-bg">
              </div>
              <div className="amlogistic-list">
                <h3>Выбрав нас, вы можете быть уверены в:</h3>
                <ul>
                  <li>оперативности</li>
                  <li>индивидуальном подходе</li>
                  <li>гибкости</li>
                  <li>профессионализме</li>
                  <li>качественном сервисе</li>
                </ul>
              </div>
            </div>
            <div className="amlogistic-right">
              <h3>
                AMLogistic — ваш надёжный логистический партнёр в Подмосковье
              </h3>
              <ul className="amlogistic-bullets">
                <li>
                  Водители аккредитованы на всех станция Москвы и Московской Области.
                </li>
                <li>
                  Участок оснащён современной инфраструктурой: твёрдое покрытие, удобные подъездные пути для любого типа транспорта.
                </li>
                <li>
                  Охрана объекта осуществляется круглосуточно, работает система видеонаблюдения и контроля доступа.
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      
      {/* КАРТА РОССИИ */}
      <section className="map-section">
        <div className="container">
          <img
            src={mapImage}
            alt="Работаем по всей России"
            className="map-image"
          />
        </div>
      </section>

    <section className="terminal-section">
      <div className="terminal-wrapper">
        <div className="terminal-content">
          <h2>КОНТЕЙНЕРНЫЙ ТЕРМИНАЛ</h2>
          <ul className="terminal-list">
            <li>Контейнерные перевозки</li>
            <li>Перевозка 20 футового контейнера</li>
            <li>Перевозка 40 футового контейнера</li>
            <li>Перевозка 45 футового контейнера</li>
            <li>Перевозка контейнера Омск</li>
            <li>Перевозка контейнера Ростов-на-Дону</li>
            <li>Перевозка контейнера Санкт-Петербург Москва</li>
            <li>Перевозка контейнеров в Архангельске</li>
            <li>Перевозка контейнеров Пермь</li>
          </ul>
        </div>
        <div className="terminal-image">
        </div>
      </div>
    </section>



{/* Секция преимуществ (услуг) */}
      <section id="services" className="services">
        <div className="container">
          <h2>Наши преимущества</h2>
          <div className="services-list">
            {/* Карточка 1 */}
            <div className="service-item service-1">
              <div className="service-content">
                <h3>Cобственный автопарк </h3>
              </div>
            </div>
            {/* Карточка 2 */}
            <div className="service-item service-2">
              <div className="service-content">
                <h3>Страхование грузов</h3>
                <p>
                </p>
              </div>
            </div>
            {/* Карточка 3 */}
            <div className="service-item service-3">
              <div className="service-content">
                <h3>Быстрая доставка</h3>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section className="contacts-section">
        <div className="contacts-bg-filter"></div>
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

export default Home;
