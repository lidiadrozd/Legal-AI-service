import { useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import styled from 'styled-components';
import { FileText } from 'lucide-react';
import { ChatWindow } from '@/components/chat/ChatWindow';
import { MessageInput } from '@/components/chat/MessageInput';
import { useChat } from '@/hooks/useChat';
import { useSSE } from '@/hooks/useSSE';
import { useChatStore } from '@/store/chatStore';
import { chatApi } from '@/api/chat';

const Wrapper = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const WindowWrap = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
`;

const DocsBar = styled(Link)`
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 24px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-surface-card);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  text-decoration: none;
  flex-shrink: 0;
  transition:
    border-color var(--transition-fast),
    color var(--transition-fast),
    background var(--transition-fast);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: var(--color-primary-muted);
  }
`;

const DocsBarTitle = styled.span`
  font-weight: 600;
  color: var(--color-text);
`;

const DocsBarHint = styled.span`
  color: var(--color-text-tertiary);
  font-size: 12px;
  font-weight: 400;
`;

export default function ChatPage() {
  const { chatId } = useParams<{ chatId?: string }>();
  const navigate = useNavigate();
  const { loadChats, openChat } = useChat();
  const { stream, cancel } = useSSE();
  const { activeChat } = useChatStore();

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  useEffect(() => {
    useChatStore.getState().resetStreaming();
    if (chatId) {
      openChat(chatId);
      const found = useChatStore.getState().chats.find((c) => c.id === chatId);
      if (found) useChatStore.getState().setActiveChat(found);
    } else {
      useChatStore.getState().setActiveChat(null);
      useChatStore.getState().clearMessages();
    }
  }, [chatId, openChat]);

  const handleSend = useCallback(
    async (content: string, fileId?: string) => {
      let chatIdToUse = activeChat?.id ?? chatId;

      if (!chatIdToUse) {
        const result = await chatApi.createChat();
        const newChat = {
          id: result.chat_id,
          title: result.title,
          user_id: '',
          message_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        useChatStore.getState().addChat(newChat);
        useChatStore.getState().setActiveChat(newChat);
        chatIdToUse = result.chat_id;
        navigate(`/chat/${chatIdToUse}`, { replace: true });
      }

      const userMsg = {
        id: `tmp-${Date.now()}`,
        chat_id: chatIdToUse,
        role: 'user' as const,
        content,
        created_at: new Date().toISOString(),
      };
      useChatStore.getState().appendMessage(userMsg);

      await stream({
        chat_id: chatIdToUse,
        content,
        attachment_ids: fileId ? [fileId] : undefined,
      });
    },
    [activeChat, chatId, navigate, stream],
  );

  const handleSuggestion = useCallback(
    (text: string) => handleSend(text),
    [handleSend],
  );

  const currentChatId = activeChat?.id ?? chatId ?? '';
  const documentsHref = currentChatId
    ? `/documents?chatId=${encodeURIComponent(currentChatId)}&openGenerate=1`
    : '/documents?openGenerate=1';

  return (
    <Wrapper>
      <WindowWrap>
        <ChatWindow onSuggestionClick={handleSuggestion} />
      </WindowWrap>
      <DocsBar to={documentsHref}>
        <FileText size={18} aria-hidden />
        <span>
          <DocsBarTitle>Документы Word / PDF / TXT</DocsBarTitle>
          {' — '}
          <DocsBarHint>
            {currentChatId
              ? 'откроется генерация с подстановкой из этого чата'
              : 'начните чат или откройте существующий — тогда подставится его контекст'}
          </DocsBarHint>
        </span>
      </DocsBar>
      <MessageInput onSend={handleSend} onStopStreaming={cancel} />
    </Wrapper>
  );
}
