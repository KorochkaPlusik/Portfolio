import React, { useState, useEffect } from 'react';
import io from 'socket.io-client';
import './ContactWidget.css';

// Подключаемся к тому же домену, что и фронт.
// Nginx проксирует запросы на /socket.io/ к нашему бэку.
const socket = io('/', {
  path: '/socket.io',
  transports: ['websocket', 'polling'],
});

const ContactWidget = () => {
  const email = localStorage.getItem('email') || `guest-${Math.random().toString(36).substring(2, 10)}`;
  const isAdmin = email === 'LogisticTransAM@gmail.com'; // <- укажи точный email админа
  const [userId, setUserId] = useState(email);
  const [allUsers, setAllUsers] = useState([]);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);

  useEffect(() => {
    socket.emit('join', userId);

    if (isAdmin) {
      socket.emit('get users');
      socket.on('user list', (users) => {
        setAllUsers(users.filter(u => u !== email));
      });
    }

    socket.emit('load messages', { userId });
    socket.on('chat history', (history) => setMessages(history));

    socket.on('chat message', (msg) => {
      const isRelevant = (msg.to === userId || msg.from === userId || isAdmin);
      if (isRelevant && (!isAdmin || msg.from === userId || msg.to === userId)) {
        setMessages(prev => [...prev, msg]);
      }
    });

    return () => {
      socket.off('chat message');
      socket.off('chat history');
      socket.off('user list');
    };
  }, [userId, isAdmin, email]);

  const sendMessage = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    const msg = isAdmin
      ? { from: email, to: userId, text }
      : { from: userId, to: 'LogisticTransAM@gmail.com', text };

    socket.emit('chat message', msg);
    setMessages(prev => [...prev, msg]);
    setText('');
  };

  const handleSelectUser = (selectedUser) => {
    setMessages([]);
    setUserId(selectedUser);
    socket.emit('join', selectedUser);
    socket.emit('load messages', { userId: selectedUser });
  };

  return (
    <div className="contact-widget">
      <div className="contact-buttons">
        {!isAdmin && (
          <a href="tel:+79296998653" className="contact-icon" title="Позвонить">
            📞
          </a>
        )}
        <div className="contact-icon" title="Чат с админом" onClick={() => setOpen(!open)}>
          💬
        </div>
      </div>

      {open && (
        <div className="chat-box">
          <div className="chat-header">
            {isAdmin ? 'Чаты пользователей' : 'Чат с админом'}
          </div>

          {isAdmin && (
            <div className="chat-users">
              {allUsers.map(u => (
                <div
                  key={u}
                  className={`chat-user ${u === userId ? 'active' : ''}`}
                  onClick={() => handleSelectUser(u)}
                >
                  {u}
                </div>
              ))}
            </div>
          )}

          <div className="chat-messages">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`chat-message ${msg.from === email ? 'from-me' : 'from-admin'}`}
              >
                {msg.text}
              </div>
            ))}
          </div>

          <form onSubmit={sendMessage} className="chat-form">
            <input
              type="text"
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Напишите сообщение..."
            />
            <button type="submit">➤</button>
          </form>
        </div>
      )}
    </div>
  );
};

export default ContactWidget;
