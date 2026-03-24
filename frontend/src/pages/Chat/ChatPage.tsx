import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import styled from 'styled-components';
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

  return (
    <Wrapper>
      <WindowWrap>
        <ChatWindow onSuggestionClick={handleSuggestion} />
      </WindowWrap>
      <MessageInput onSend={handleSend} onStopStreaming={cancel} />
    </Wrapper>
  );
}
