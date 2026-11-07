import styled from 'styled-components';
import { Menu, LogOut, User, Shield, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { useAuth } from '@/hooks/useAuth';
import { useUIStore } from '@/store/uiStore';
import { useState, useRef } from 'react';
import { NotificationBell } from '@/components/common/NotificationBell';

const Bar = styled.header`
  height: var(--header-height);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  padding: 0 12px; /* Уменьшил отступы для мобилок */
  gap: 8px; /* Уменьшил зазор между кнопками */
  background: var(--color-surface);
  flex-shrink: 0;

  @media (min-width: 768px) {
    padding: 0 20px;
    gap: 12px;
  }
`;

const BurgerBtn = styled.button`
  background: none;
  border: none;
  color: var(--color-text-secondary);
  padding: 6px;
  border-radius: var(--radius-sm);
  display: none;
  @media (max-width: 768px) { display: flex; }
  &:hover { color: var(--color-text); background: var(--color-surface-hover); }
`;

const Title = styled.div`
  flex: 1;
  font-size: 14px; /* Меньше на мобилках */
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis; /* Обрезает текст многоточием, если не влезает */

  @media (min-width: 480px) {
    font-size: var(--font-size-md);
  }
`;

const UserMenu = styled.div`
  position: relative;
`;

const UserBtn = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  padding: 4px 8px; /* Компактнее на мобилках */
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  transition: border-color var(--transition-fast), color var(--transition-fast);
  &:hover { border-color: var(--color-border-hover); color: var(--color-text); }

  @media (min-width: 768px) {
    padding: 6px 12px 6px 8px;
    gap: 8px;
  }
`;

const Dropdown = styled.div<{ $open: boolean }>`
  display: ${({ $open }) => ($open ? 'block' : 'none')};
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 8px;
  width: 300px;
  max-width: calc(100vw - 24px);
  box-shadow: var(--shadow-elevated);
  z-index: 50;
`;

const DropdownItem = styled.button`
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  text-align: left;
  line-height: 1.5;
  text-decoration: none;
  & svg { flex-shrink: 0; }
  &:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
  transition: background var(--transition-fast), color var(--transition-fast);
  &:hover { background: var(--color-surface-hover); color: var(--color-text); }
  &.danger:hover { color: var(--color-error); }
`;

const UserName = styled.span`
  max-width: 60px; /* Очень узко на мобилках */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  @media (min-width: 480px) {
    max-width: 140px;
  }
  
  @media (max-width: 360px) {
    display: none; /* Скрываем имя на совсем маленьких экранах */
  }
`;

export function Header() {
  const { user } = useAuthStore();
  const { logout } = useAuth();
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleLogout = async () => {
    setOpen(false);
    await logout();
  };

  return (
    <Bar>
      <BurgerBtn onClick={toggleSidebar}>
        <Menu size={20} />
      </BurgerBtn>
      <Title>Юридический ИИ-ассистент</Title>
      <NotificationBell />
      <UserMenu ref={menuRef}>
        <UserBtn
          aria-label="Меню аккаунта"
          aria-expanded={open}
          aria-controls="account-dropdown"
          onClick={() => setOpen((v) => !v)}
        >
          <User size={16} />
          <UserName>{user?.full_name ?? user?.email ?? 'Пользователь'}</UserName>
        </UserBtn>
        <Dropdown id="account-dropdown" $open={open}>
          <DropdownItem as="div" style={{ paddingBottom: '4px', opacity: 0.5, fontSize: '11px', overflowWrap: 'anywhere' }}>
            {user?.email}
          </DropdownItem>
          <div style={{ height: 1, background: 'var(--color-border)', margin: '4px 0' }} />
          <DropdownItem as={Link} to="/privacy" target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
            <Shield size={16} />
            <span>Политика конфиденциальности и обработка персональных данных</span>
          </DropdownItem>
          <DropdownItem as={Link} to="/terms" target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
            <FileText size={16} />
            <span>Пользовательское соглашение</span>
          </DropdownItem>
          <div style={{ height: 1, background: 'var(--color-border)', margin: '4px 0' }} />
          <DropdownItem className="danger" onClick={handleLogout}>
            <LogOut size={14} />
            Выйти
          </DropdownItem>
        </Dropdown>
      </UserMenu>
    </Bar>
  );
}
