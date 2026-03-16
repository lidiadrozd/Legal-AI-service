import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '@/store/chatStore';
import { useUIStore } from '@/store/uiStore';
import { chatApi } from '@/api/chat';
import type { SendMessageRequest } from '@/types/chat.types';

export function useChat() {
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);
  const {
    setChats,
    addChat,
    setActiveChat,
    setMessages,
    appendMessage,
    startStreaming,
    appendStreamChunk,
    finishStreaming,
    activeChat,
  } = useChatStore();

  const loadChats = useCallback(async () => {
    const chats = await chatApi.getChats();
    setChats(chats);
  }, [setChats]);

  const openChat = useCallback(
    async (chatId: string) => {
      const messages = await chatApi.getChatHistory(chatId);
      setMessages(messages);
    },
    [setMessages]
  );

  const createChat = useCallback(async () => {
    const result = await chatApi.createChat();
    addChat({ id: result.chat_id, title: result.title, user_id: '', message_count: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
    setActiveChat({ id: result.chat_id, title: result.title, user_id: '', message_count: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
    navigate(`/chat/${result.chat_id}`);
  }, [addChat, setActiveChat, navigate]);

  const sendMessage = useCallback(
    async (content: string, attachmentIds?: string[], signal?: AbortSignal) => {
      if (!activeChat) return;

      const userMessage = {
        id: crypto.randomUUID(),
        chat_id: activeChat.id,
        role: 'user' as const,
        content,
        created_at: new Date().toISOString(),
      };
      appendMessage(userMessage);

      const request: SendMessageRequest = {
        chat_id: activeChat.id,
        content,
        attachment_ids: attachmentIds,
      };

      startStreaming();

      await chatApi.sendStream(
        request,
        (chunk) => appendStreamChunk(chunk),
        (msgId) => finishStreaming(msgId),
        (err) => {
          finishStreaming('');
          addToast({ message: err, type: 'error' });
        },
        signal
      );
    },
    [activeChat, appendMessage, startStreaming, appendStreamChunk, finishStreaming, addToast]
  );

  return { loadChats, openChat, createChat, sendMessage };
}
