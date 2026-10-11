import { useState, useRef, useEffect } from 'react';
import styled from 'styled-components';
import { Bell } from 'lucide-react';
import { useNotificationStore } from '@/store/notificationStore';
import type { Notification } from '@/store/notificationStore';

const Wrap = styled.div`
  position: relative;
`;

const BellBtn = styled.button`
  position: relative;
  background: none;
  border: none;
  color: var(--color-text-secondary);
  padding: 6px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color var(--transition-fast), background var(--transition-fast);
  &:hover { color: var(--color-text); background: var(--color-surface-hover); }
`;

const Badge = styled.span`
  position: absolute;
  top: 2px;
  right: 2px;
  background: var(--color-error);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 999px;
  min-width: 16px;
  text-align: center;
`;

const Panel = styled.div<{ $open: boolean }>`
  display: ${({ $open }) => ($open ? 'flex' : 'none')};
  flex-direction: column;
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-elevated);
  
  /* Адаптивная ширина */
  width: 320px;
  max-width: calc(100vw - 32px); /* Чтобы не вылезало за края экрана на мобилках */
  
  max-height: 420px;
  z-index: 100;
  overflow: hidden;

  @media (max-width: 480px) {
    position: fixed;
    right: 16px;
    left: 16px; /* Растягиваем почти на всю ширину на очень мелких экранах */
    width: auto;
  }
`;

const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
`;

const PanelTitle = styled.span`
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
`;

const MarkReadBtn = styled.button`
  background: none;
  border: none;
  font-size: 11px;
  color: var(--color-primary);
  font-weight: 500;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  &:hover { background: var(--color-surface-hover); }
`;

const List = styled.div`
  overflow-y: auto;
  flex: 1;
  /* Тонкий скроллбар для красоты */
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 10px; }
`;

const Item = styled.div<{ $unread: boolean }>`
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
  background: ${({ $unread }) => ($unread ? 'rgba(var(--color-primary-rgb), 0.05)' : 'transparent')};
  transition: background 0.2s ease;
  &:last-child { border-bottom: none; }
  &:hover { background: var(--color-surface-hover); }
`;

const ItemIcon = styled.div`
  font-size: 18px;
  flex-shrink: 0;
  line-height: 1.4;
`;

const ItemBody = styled.div`
  flex: 1;
  min-width: 0;
`;

const ItemTitle = styled.div`
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ItemText = styled.div`
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 2px;
  display: -webkit-box;
  -webkit-line-clamp: 3; /* Больше текста для мобилок */
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
`;

const ItemTime = styled.div`
  font-size: 10px;
  color: var(--color-text-tertiary);
  margin-top: 6px;
`;

const Empty = styled.div`
  padding: 40px 14px;
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
`;

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function NotificationItem({ n }: { n: Notification }) {
  return (
    <Item $unread={!n.read}>
      <ItemIcon>{n.icon || '🔔'}</ItemIcon>
      <ItemBody>
        <ItemTitle>{n.title}</ItemTitle>
        <ItemText>{n.body}</ItemText>
        <ItemTime>{formatTime(n.createdAt)}</ItemTime>
      </ItemBody>
    </Item>
  );
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const { notifications, unreadCount, markAllRead } = useNotificationStore();

  // Закрытие по клику вне панели
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (open && wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleMarkRead = () => {
    void markAllRead();
  };

  return (
    <Wrap ref={wrapRef}>
      <BellBtn onClick={() => setOpen((v) => !v)} title="Уведомления">
        <Bell size={18} />
        {unreadCount > 0 && <Badge>{unreadCount > 99 ? '99+' : unreadCount}</Badge>}
      </BellBtn>
      <Panel $open={open}>
        <PanelHeader>
          <PanelTitle>Уведомления</PanelTitle>
          {unreadCount > 0 && (
            <MarkReadBtn onClick={handleMarkRead}>Прочитать все</MarkReadBtn>
          )}
        </PanelHeader>
        <List>
          {notifications.length === 0 ? (
            <Empty>Нет уведомлений</Empty>
          ) : (
            notifications.map((n) => <NotificationItem key={n.id} n={n} />)
          )}
        </List>
      </Panel>
    </Wrap>
  );
}