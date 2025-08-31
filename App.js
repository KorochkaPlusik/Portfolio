import { Routes, Route, Navigate } from 'react-router-dom';
import Home from './pages/Home';
import AdminLogin from './pages/AdminLogin';
import Requests from './pages/Requests';
import Dangerous from './pages/Dangerous';
import Header from './components/Header';
import Containers from './pages/Containers';
import Refrigerated from './pages/Refrigerated';
import Oversized from './pages/Oversized';
import Nebortovye from './pages/Nebortovye';
import Tentovye from './pages/Tentovye';
import About from './pages/About';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ContactWidget from './pages/ContactWidget';
import ScrollTruck from './ScrollTruck';
import ScrollToTopButton from './pages/ScrollToTopButton';
import './App.css';

function App() {
  const adminEmail = "LogisticTransAM@gmail.com"; // или свой
  const isAdmin = localStorage.getItem('email') === adminEmail;

  return (
    <>
      <Header />
      <div className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/admin" element={<AdminLogin />} />
          <Route
            path="/admin/requests"
            element={
              isAdmin ? <Requests /> : <Navigate to="/" replace />
            }
          />
          <Route path="/dangerous" element={<Dangerous />} />
          <Route path="/containers" element={<Containers />} />
          <Route path="/oversized" element={<Oversized />} />
          <Route path="/refrigerated" element={<Refrigerated />} />
          <Route path="/tentovye" element={<Tentovye />} />
          <Route path="/nebortovye" element={<Nebortovye />} />
          <Route path="/about" element={<About />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </div>
      <ContactWidget />
      <ScrollTruck />
      <ScrollToTopButton />
    </>
  );
}

export default App;
