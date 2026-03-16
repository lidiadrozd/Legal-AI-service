import styled from 'styled-components';
import { formatDateTime } from '@/utils/formatDate';
import type { Message } from '@/types/chat.types';
import type { AdminChat } from '@/types/admin.types';

const Wrap = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const ChatHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
`;

const ChatMeta = styled.div`
  flex: 1;
`;

const ChatTitle = styled.div`
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
`;

const ChatInfo = styled.div`
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
`;

const MessageList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const MsgItem = styled.div<{ $isUser: boolean }>`
  display: flex;
  flex-direction: ${({ $isUser }) => ($isUser ? 'row-reverse' : 'row')};
  gap: 8px;
`;

const MsgBubble = styled.div<{ $isUser: boolean }>`
  max-width: 70%;
  padding: 10px 14px;
  border-radius: ${({ $isUser }) => ($isUser ? '14px 14px 4px 14px' : '4px 14px 14px 14px')};
  background: ${({ $isUser }) => ($isUser ? 'var(--color-primary-muted)' : 'var(--color-surface-card)')};
  border: 1px solid ${({ $isUser }) => ($isUser ? 'var(--color-primary)' : 'var(--color-border)')};
  font-size: var(--font-size-sm);
  color: var(--color-text);
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
`;

const MsgTime = styled.div`
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
  padding: 0 4px;
`;

const EmptyMsg = styled.div`
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  padding: 32px;
`;

interface Props {
  chat: AdminChat;
  messages: Message[];
}

export function ChatLogViewer({ chat, messages }: Props) {
  return (
    <Wrap>
      <ChatHeader>
        <ChatMeta>
          <ChatTitle>{chat.title}</ChatTitle>
          <ChatInfo>
            {chat.user_email} · {chat.message_count} сообщений · {formatDateTime(chat.created_at)}
          </ChatInfo>
        </ChatMeta>
      </ChatHeader>
      <MessageList>
        {messages.length === 0 && (
          <EmptyMsg>Сообщений нет</EmptyMsg>
        )}
        {messages.map((msg) => (
          <div key={msg.id}>
            <MsgItem $isUser={msg.role === 'user'}>
              <MsgBubble $isUser={msg.role === 'user'}>
                {msg.content}
              </MsgBubble>
            </MsgItem>
            <MsgTime style={{ textAlign: msg.role === 'user' ? 'right' : 'left' }}>
              {msg.role === 'user' ? 'Пользователь' : 'ИИ-ассистент'} · {formatDateTime(msg.created_at)}
            </MsgTime>
          </div>
        ))}
      </MessageList>
    </Wrap>
  );
}
