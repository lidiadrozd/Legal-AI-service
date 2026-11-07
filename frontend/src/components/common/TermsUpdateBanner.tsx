import { useState, useEffect } from 'react';
import styled from 'styled-components';
import { Link } from 'react-router-dom';
import { Info } from 'lucide-react';

const BannerWrap = styled.div<{ $visible: boolean }>`
  display: ${({ $visible }) => ($visible ? 'flex' : 'none')};
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 32px);
  max-width: 500px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-primary);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  border-radius: var(--radius-lg);
  padding: 16px;
  z-index: 9999;
  align-items: center;
  gap: 16px;
  animation: slideUp 0.5s ease-out;

  @keyframes slideUp {
    from { transform: translate(-50%, 100px); opacity: 0; }
    to { transform: translate(-50%, 0); opacity: 1; }
  }

  @media (max-width: 480px) {
    flex-direction: column;
    text-align: center;
    bottom: 12px;
  }
`;

const Text = styled.p`
  flex: 1;
  font-size: 14px;
  color: var(--color-text);
  line-height: 1.5;
  margin: 0;
  
  a {
    color: var(--color-primary);
    text-decoration: underline;
    &:hover { opacity: 0.8; }
  }
`;

const Btn = styled.button`
  padding: 10px 20px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: transform 0.1s;
  &:hover { background: var(--color-primary-hover); transform: scale(1.02); }
  &:active { transform: scale(0.98); }
`;

export function TermsUpdateBanner() {
  const [visible, setVisible] = useState(false);
  // Используем ключ с версией, чтобы баннер показался всем заново после обновления
  const STORAGE_KEY = 'legal_terms_accepted_v2'; 

  useEffect(() => {
    const isAccepted = localStorage.getItem(STORAGE_KEY);
    if (!isAccepted) {
      // Показываем через небольшую паузу для красоты
      const timer = setTimeout(() => setVisible(true), 1500);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setVisible(false);
  };

  return (
    <BannerWrap $visible={visible}>
      <Info size={24} color="var(--color-primary)" style={{ flexShrink: 0 }} />
      <Text>
        Мы обновили <strong>Пользовательское соглашение</strong> и правила обработки данных. 
        Ознакомьтесь с изменениями <Link to="/privacy">здесь</Link>.
      </Text>
      <Btn onClick={handleAccept}>Принять</Btn>
    </BannerWrap>
  );
}