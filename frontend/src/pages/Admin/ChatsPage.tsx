import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import styled from 'styled-components';
import { adminApi } from '@/api/admin';
import { ChatLogViewer } from '@/components/admin/ChatLogViewer';
import { formatDateTime } from '@/utils/formatDate';
import type { AdminChat } from '@/types/admin.types';
import type { Message } from '@/types/chat.types';

const Page = styled.div`
  padding: 32px;
  max-width: 1200px;
  height: 100%;
  overflow-y: auto;
`;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 24px;
`;

const Layout = styled.div`
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  align-items: flex-start;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

const ChatList = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
`;

const ChatListHeader = styled.div`
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
`;

const ChatItem = styled.div<{ $active: boolean }>`
  padding: 14px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--color-border-subtle);
  background: ${({ $active }) => ($active ? 'var(--color-primary-muted)' : 'transparent')};
  border-left: 3px solid ${({ $active }) => ($active ? 'var(--color-primary)' : 'transparent')};
  transition: all var(--transition-fast);
  &:hover { background: var(--color-surface); }
  &:last-child { border-bottom: none; }
`;

const ChatItemTitle = styled.div`
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ChatItemMeta = styled.div`
  font-size: 12px;
  color: var(--color-text-tertiary);
`;

const Skeleton = styled.div`
  height: 60px;
  background: var(--color-surface);
  margin: 1px 0;
  animation: skeleton-pulse 1.4s ease-in-out infinite;
  @keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
`;

const EmptyMsg = styled.div`
  padding: 32px;
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
`;

export default function ChatsPage() {
  const [searchParams] = useSearchParams();
  const userId = searchParams.get('userId') ?? undefined;
  const [selectedChat, setSelectedChat] = useState<AdminChat | null>(null);

  const { data: chats, isLoading } = useQuery({
    queryKey: ['admin-chats', userId],
    queryFn: () => (userId ? adminApi.getUserChats(userId) : adminApi.getAllChats()),
  });

  const { data: selectedMessages = [] } = useQuery<Message[]>({
    queryKey: ['admin-chat-messages', selectedChat?.id],
    queryFn: () => adminApi.getChatMessages(selectedChat!.id),
    enabled: !!selectedChat,
  });

  return (
    <Page>
      <Title>Чаты{userId ? ' пользователя' : ''}</Title>
      <Layout>
        <ChatList>
          <ChatListHeader>
            {isLoading ? '...' : `${chats?.length ?? 0} чатов`}
          </ChatListHeader>
          {isLoading
            ? Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} />)
            : !chats?.length
              ? <EmptyMsg>Чатов не найдено</EmptyMsg>
              : chats.map((chat) => (
                  <ChatItem
                    key={chat.id}
                    $active={selectedChat?.id === chat.id}
                    onClick={() => setSelectedChat(chat)}
                  >
                    <ChatItemTitle>{chat.title || 'Без заголовка'}</ChatItemTitle>
                    <ChatItemMeta>
                      {chat.user_email} · {formatDateTime(chat.created_at)}
                    </ChatItemMeta>
                  </ChatItem>
                ))}
        </ChatList>

        {selectedChat ? (
          <ChatLogViewer chat={selectedChat} messages={selectedMessages} />
        ) : (
          <EmptyMsg style={{ flex: 1 }}>Выберите чат для просмотра</EmptyMsg>
        )}
      </Layout>
    </Page>
  );
}
