import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import logoImg from './logo.png';
import './Header.css';

function Header() {
  const navigate = useNavigate();
  const [isAuth, setIsAuth] = useState(!!localStorage.getItem('token'));
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const update = () => {
      const token = localStorage.getItem('token');
      const storedEmail = localStorage.getItem('email') || '';
      setIsAuth(!!token);
      setName(localStorage.getItem('name') || '');
      setEmail(storedEmail);

      // Сравниваем email с админским
      setIsAdmin(storedEmail === 'LogisticTransAM@gmail.com'); // ← Замените на свой email
    };

    update();
    const interval = setInterval(update, 500);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = () => {
    localStorage.clear();
    setIsAuth(false);
    setIsAdmin(false);
    navigate('/');
  };

  return (
    <header className="header">
      <div className="header-left">
        <Link to="/" className="logo-link">
          <img src={logoImg} alt="AM-Logistic" className="logo" />
        </Link>

        <nav>
          <ul className="nav-list">
            <li><Link className="nav-link" to="/">Главная</Link></li>
            <li className="dropdown">
              <span className="nav-link">Грузоперевозки</span>
              <ul className="dropdown-menu">
                <li><Link className="nav-link" to="/dangerous">Еврофуры</Link></li>
                <li><Link className="nav-link" to="/containers">Грузы до 5 тонн</Link></li>
                <li><Link className="nav-link" to="/refrigerated">Грузы до 1,5 тонн</Link></li>
                <li><Link className="nav-link" to="/oversized">Негабарит</Link></li>
                <li><Link className="nav-link" to="/tentovye">Контейнеровозы</Link></li>
              </ul>
            </li>
            <li><Link className="nav-link" to="/about">О нас</Link></li>

            {isAdmin && (
              <li><Link className="nav-link" to="/admin/requests">Заявки</Link></li>
            )}

            {!isAuth && (
              <>
                <li><Link className="nav-link" to="/login">Вход</Link></li>
                <li><Link className="nav-link" to="/register">Регистрация</Link></li>
              </>
            )}
          </ul>
        </nav>
      </div>

      {isAuth && (
        <div className="user-info-block">
          <span className="user-info">{name} ({email})</span>
          <span className="nav-link logout" onClick={handleLogout}>Выход</span>
        </div>
      )}
    </header>
  );
}

export default Header;
