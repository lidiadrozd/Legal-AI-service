import { useState, useRef } from 'react';
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
  width: 320px;
  max-height: 420px;
  z-index: 50;
  overflow: hidden;
`;

const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
`;

const PanelTitle = styled.span`
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
`;

const MarkReadBtn = styled.button`
  background: none;
  border: none;
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  &:hover { color: var(--color-text); background: var(--color-surface-hover); }
`;

const List = styled.div`
  overflow-y: auto;
  flex: 1;
`;

const Item = styled.div<{ $unread: boolean }>`
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
  background: ${({ $unread }) => ($unread ? 'var(--color-primary-muted)' : 'transparent')};
  &:last-child { border-bottom: none; }
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
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const ItemTime = styled.div`
  font-size: 10px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
`;

const Empty = styled.div`
  padding: 32px 14px;
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
      <ItemIcon>{n.icon}</ItemIcon>
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

  const handleMarkRead = () => {
    markAllRead();
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
