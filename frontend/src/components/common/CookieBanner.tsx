import { useState } from 'react';
import styled from 'styled-components';
import { Link } from 'react-router-dom';

const COOKIE_KEY = 'ai_lawyer_cookie_consent';

const Banner = styled.div`
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 2000;
  padding: 16px 24px;
  background: var(--color-surface-card);
  border-top: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  flex-wrap: wrap;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.25);
`;

const Text = styled.p`
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  max-width: 720px;
  line-height: 1.5;
`;

const Btn = styled.button`
  padding: 10px 20px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  &:hover { background: var(--color-primary-hover); }
`;

export function CookieBanner() {
  const [visible, setVisible] = useState(() => !localStorage.getItem(COOKIE_KEY));

  if (!visible) return null;

  const accept = () => {
    localStorage.setItem(COOKIE_KEY, '1');
    setVisible(false);
  };

  return (
    <Banner role="dialog" aria-label="Уведомление об использовании cookie">
      <Text>
        Мы используем cookie для работы сайта и улучшения сервиса. Продолжая пользоваться сайтом, вы
        соглашаетесь с{' '}
        <Link to="/privacy">политикой конфиденциальности</Link>.
      </Text>
      <Btn type="button" onClick={accept} aria-label="Принять использование cookie">
        Принять
      </Btn>
    </Banner>
  );
}
