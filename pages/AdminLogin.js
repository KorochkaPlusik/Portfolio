import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

function AdminLogin() {
  const [credentials, setCredentials] = useState({ email: '', password: '' });
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

  const handleChange = e => {
    setCredentials({ ...credentials, [e.target.name]: e.target.value });
  };

  const handleSubmit = async e => {
    e.preventDefault();
    try {
      const response = await fetch('http://localhost:5000/api/admin/login', {
         method: 'POST',
         headers: {
           'Content-Type': 'application/json'
         },
         body: JSON.stringify(credentials)
      });
      const data = await response.json();
      if(response.ok) {
         localStorage.setItem('adminToken', data.token);
         setMessage(data.message);
         navigate('/admin/requests');
      } else {
         setMessage(data.message || 'Ошибка авторизации');
      }
    } catch (error) {
      console.error(error);
      setMessage('Ошибка авторизации');
    }
  };

  return (
    <div>
      <h1>Администратор. Вход</h1>
      <form onSubmit={handleSubmit}>
         <div>
            <label htmlFor="email">Email:</label>
            <input
              type="email"
              name="email"
              id="email"
              value={credentials.email}
              onChange={handleChange}
              required
            />
         </div>
         <div>
            <label htmlFor="password">Пароль:</label>
            <input
              type="password"
              name="password"
              id="password"
              value={credentials.password}
              onChange={handleChange}
              required
            />
         </div>
         <button type="submit">Войти</button>
      </form>
      {message && <p>{message}</p>}
    </div>
  );
}

export default AdminLogin;
