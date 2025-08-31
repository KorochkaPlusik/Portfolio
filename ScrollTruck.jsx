import { useEffect, useState } from 'react';
import truckImage from './pages/images/log/m1.png';

const ScrollTruck = () => {
  const [scrollY, setScrollY] = useState(window.scrollY);
  const [lastY, setLastY] = useState(window.scrollY);
  const [rotation, setRotation] = useState(0);
  const [truckTop, setTruckTop] = useState(50);

  useEffect(() => {
    const handleScroll = () => {
      const currentY = window.scrollY;
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;

      if (currentY > lastY) {
        setRotation(0);
      } else if (currentY < lastY) {
        setRotation(180);
      }

      setScrollY(currentY);
      setLastY(currentY);

      // адаптивное положение (не до самого низа, учитывая нижнюю панель)
      const maxTruckY = window.innerHeight - 100; // отступ снизу
      const relativeY = (currentY / maxScroll) * maxTruckY;

      setTruckTop(Math.min(relativeY, maxTruckY));
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [lastY]);

  return (
    <img
      src={truckImage}
      alt="Scroll truck"
      className="scroll-truck"
      style={{
        position: 'fixed',
        right: '20px', // вместо left
        top: `${truckTop}px`,
        transform: `rotate(${rotation}deg)`,
        transition: 'top 0.2s ease, transform 0.3s ease',
        width: '80px',
        zIndex: 1000,
        pointerEvents: 'none',
      }}
    />
  );
};

export default ScrollTruck;
