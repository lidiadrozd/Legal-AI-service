import { Link, useNavigate, useParams } from 'react-router-dom';
import styled from 'styled-components';
import { MessageSquare, Plus, Trash2, LayoutDashboard, Users, MessageCircle, Star, BarChart3, FileText } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';
import { chatApi } from '@/api/chat';
import { formatRelative } from '@/utils/formatDate';
import { useUIStore } from '@/store/uiStore';

interface SidebarProps {
  isAdmin?: boolean;
}

const Wrap = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 12px;
  gap: 8px;
  overflow: hidden;
`;

const LogoRow = styled.div`
  padding: 4px 8px 16px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 4px;
`;

const LogoText = styled(Link)`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
  text-decoration: none;
  &:hover { text-decoration: none; }
  span { color: var(--color-primary); }
`;

const NewChatBtn = styled.button`
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  transition: background var(--transition-fast);
  &:hover { background: var(--color-primary-hover); }
`;

const SectionLabel = styled.div`
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  padding: 8px 8px 4px;
`;

const ChatList = styled.div`
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const ChatItem = styled.div<{ $active?: boolean }>`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  background: ${({ $active }) => ($active ? 'var(--color-primary-muted)' : 'transparent')};
  border: 1px solid ${({ $active }) => ($active ? 'var(--color-primary)' : 'transparent')};
  transition: background var(--transition-fast);
  &:hover {
    background: ${({ $active }) => ($active ? 'var(--color-primary-muted)' : 'var(--color-surface-hover)')};
  }
`;

const ChatItemText = styled.div`
  flex: 1;
  min-width: 0;
`;

const ChatTitle = styled.div`
  font-size: var(--font-size-sm);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ChatDate = styled.div`
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 1px;
`;

const DeleteBtn = styled.button`
  flex-shrink: 0;
  background: none;
  border: none;
  padding: 4px;
  color: var(--color-text-tertiary);
  border-radius: var(--radius-sm);
  opacity: 0;
  transition: opacity var(--transition-fast), color var(--transition-fast);
  ${ChatItem}:hover & { opacity: 1; }
  &:hover { color: var(--color-error); }
`;

const NavItem = styled(Link)<{ $active?: boolean }>`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  color: ${({ $active }) => ($active ? 'var(--color-text)' : 'var(--color-text-secondary)')};
  background: ${({ $active }) => ($active ? 'var(--color-surface-hover)' : 'transparent')};
  font-size: var(--font-size-sm);
  font-weight: ${({ $active }) => ($active ? '600' : '400')};
  text-decoration: none;
  transition: background var(--transition-fast), color var(--transition-fast);
  &:hover {
    background: var(--color-surface-hover);
    color: var(--color-text);
    text-decoration: none;
  }
`;

export function Sidebar({ isAdmin = false }: SidebarProps) {
  const { chatId } = useParams();
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);
  const { chats, removeChat, setActiveChat, clearMessages, addChat } = useChatStore();

  const handleNewChat = async () => {
    try {
      const result = await chatApi.createChat();
      const newChat = {
        id: result.chat_id,
        title: result.title,
        user_id: '',
        message_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      addChat(newChat);
      setActiveChat(newChat);
      clearMessages();
      navigate(`/chat/${result.chat_id}`);
    } catch {
      addToast({ message: 'Не удалось создать чат', type: 'error' });
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await chatApi.deleteChat(id);
      removeChat(id);
      if (chatId === id) navigate('/chat');
    } catch {
      addToast({ message: 'Не удалось удалить чат', type: 'error' });
    }
  };

  if (isAdmin) {
    const path = window.location.pathname;
    return (
      <Wrap>
        <LogoRow>
          <LogoText to="/admin">ИИ<span>-Юрист</span></LogoText>
        </LogoRow>
        <SectionLabel>Администрирование</SectionLabel>
        <NavItem to="/admin" $active={path === '/admin'}><LayoutDashboard size={16} />Дашборд</NavItem>
        <NavItem to="/admin/users" $active={path.startsWith('/admin/users')}><Users size={16} />Пользователи</NavItem>
        <NavItem to="/admin/chats" $active={path.startsWith('/admin/chats')}><MessageCircle size={16} />Логи чатов</NavItem>
        <NavItem to="/admin/feedback" $active={path.startsWith('/admin/feedback')}><Star size={16} />Обратная связь</NavItem>
        <NavItem to="/admin/stats" $active={path.startsWith('/admin/stats')}><BarChart3 size={16} />Статистика</NavItem>
        <NavItem to="/chat" style={{ marginTop: 'auto' }}><MessageSquare size={16} />Перейти к чату</NavItem>
      </Wrap>
    );
  }

  return (
    <Wrap>
      <LogoRow>
        <LogoText to="/chat">ИИ<span>-Юрист</span></LogoText>
      </LogoRow>
      <NewChatBtn onClick={handleNewChat}>
        <Plus size={16} />
        Новый чат
      </NewChatBtn>
      <SectionLabel>История чатов</SectionLabel>
      <ChatList>
        {chats.length === 0 && (
          <div style={{ padding: '12px 8px', color: 'var(--color-text-tertiary)', fontSize: '13px' }}>
            Нет чатов
          </div>
        )}
        {chats.map((chat) => (
          <ChatItem
            key={chat.id}
            $active={chat.id === chatId}
            onClick={() => navigate(`/chat/${chat.id}`)}
          >
            <MessageSquare size={14} style={{ flexShrink: 0, color: 'var(--color-text-secondary)' }} />
            <ChatItemText>
              <ChatTitle>{chat.title}</ChatTitle>
              <ChatDate>{formatRelative(chat.updated_at)}</ChatDate>
            </ChatItemText>
            <DeleteBtn onClick={(e) => handleDelete(e, chat.id)}>
              <Trash2 size={13} />
            </DeleteBtn>
          </ChatItem>
        ))}
      </ChatList>
      <NavItem to="/documents" $active={window.location.pathname.startsWith('/documents')}>
        <FileText size={16} />Мои документы
      </NavItem>
    </Wrap>
  );
}
