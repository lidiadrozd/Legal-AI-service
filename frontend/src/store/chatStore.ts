import { create } from 'zustand';
import { capitalizeFirstLetter } from '@/utils/capitalizeFirst';
import type { Chat, Message, FeedbackRating } from '@/types/chat.types';

interface ChatState {
  chats: Chat[];
  activeChat: Chat | null;
  messages: Message[];
  isStreaming: boolean;
  streamingContent: string;
  streamingMessageId: string | null;
}

interface ChatActions {
  setChats: (chats: Chat[]) => void;
  addChat: (chat: Chat) => void;
  removeChat: (chatId: string) => void;
  setActiveChat: (chat: Chat | null) => void;
  updateChatTitle: (chatId: string, title: string) => void;
  setMessages: (messages: Message[]) => void;
  appendMessage: (message: Message) => void;
  startStreaming: () => void;
  appendStreamChunk: (chunk: string) => void;
  finishStreaming: (messageId: string) => void;
  setMessageFeedback: (messageId: string, rating: FeedbackRating) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState & ChatActions>((set, get) => ({
  chats: [],
  activeChat: null,
  messages: [],
  isStreaming: false,
  streamingContent: '',
  streamingMessageId: null,

  setChats: (chats) => set({ chats }),

  addChat: (chat) => set((s) => ({ chats: [chat, ...s.chats] })),

  removeChat: (chatId) =>
    set((s) => ({
      chats: s.chats.filter((c) => c.id !== chatId),
      activeChat: s.activeChat?.id === chatId ? null : s.activeChat,
    })),

  setActiveChat: (chat) => set({ activeChat: chat }),

  updateChatTitle: (chatId, title) =>
    set((s) => {
      const t = capitalizeFirstLetter(title);
      return {
        chats: s.chats.map((c) => (c.id === chatId ? { ...c, title: t } : c)),
        activeChat: s.activeChat?.id === chatId ? { ...s.activeChat, title: t } : s.activeChat,
      };
    }),

  setMessages: (messages) => set({ messages }),

  appendMessage: (message) =>
    set((s) => ({
      messages: [...s.messages, message],
    })),

  startStreaming: () =>
    set({ isStreaming: true, streamingContent: '', streamingMessageId: null }),

  appendStreamChunk: (chunk) =>
    set((s) => ({ streamingContent: s.streamingContent + chunk })),

  finishStreaming: (messageId) => {
    const { streamingContent, messages } = get();
    const text = (streamingContent || '').trim();
    if (!text) {
      set({ isStreaming: false, streamingContent: '', streamingMessageId: null });
      return;
    }

    const chatId = get().activeChat?.id || '';
    let emptyAssistantIdx = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && !(messages[i].content || '').trim()) {
        emptyAssistantIdx = i;
        break;
      }
    }

    const resolvedId =
      emptyAssistantIdx >= 0
        ? String(messages[emptyAssistantIdx].id)
        : messageId || crypto.randomUUID();

    const assistantMessage: Message = {
      id: resolvedId,
      chat_id: chatId,
      role: 'assistant',
      content: streamingContent,
      created_at:
        emptyAssistantIdx >= 0 ? messages[emptyAssistantIdx].created_at : new Date().toISOString(),
    };

    const newMessages =
      emptyAssistantIdx >= 0
        ? [
            ...messages.slice(0, emptyAssistantIdx),
            assistantMessage,
            ...messages.slice(emptyAssistantIdx + 1),
          ]
        : [...messages, assistantMessage];

    set({
      isStreaming: false,
      streamingContent: '',
      streamingMessageId: null,
      messages: newMessages,
    });
  },

  setMessageFeedback: (messageId, rating) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === messageId ? { ...m, feedback: rating } : m
      ),
    })),

  clearMessages: () => set({ messages: [], streamingContent: '' }),
}));
