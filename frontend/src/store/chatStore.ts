import { create } from 'zustand';
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
    if (!streamingContent) {
      set({ isStreaming: false, streamingContent: '', streamingMessageId: null });
      return;
    }
    const assistantMessage: Message = {
      id: messageId || crypto.randomUUID(),
      chat_id: get().activeChat?.id || '',
      role: 'assistant',
      content: streamingContent,
      created_at: new Date().toISOString(),
    };
    set({
      isStreaming: false,
      streamingContent: '',
      streamingMessageId: null,
      messages: [...messages, assistantMessage],
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
