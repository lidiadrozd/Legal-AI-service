import apiClient from './client';
import { getAccessToken } from '@/utils/tokenStorage';
import type { Chat, Message, CreateChatResponse, SendMessageRequest } from '@/types/chat.types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export const chatApi = {
  createChat: async (): Promise<CreateChatResponse> => {
    const response = await apiClient.post<CreateChatResponse>('/chat/new');
    return response.data;
  },

  getChats: async (): Promise<Chat[]> => {
    const response = await apiClient.get<Chat[]>('/chat/list');
    return response.data;
  },

  getChatHistory: async (chatId: string): Promise<Message[]> => {
    const response = await apiClient.get<Message[]>(`/chat/${chatId}/history`);
    return response.data;
  },

  deleteChat: async (chatId: string): Promise<void> => {
    await apiClient.delete(`/chat/${chatId}`);
  },

  /**
   * Отправить сообщение со стримингом ответа (fetch + ReadableStream).
   * Каждый чанк вызывает onChunk, по завершению — onDone.
   */
  sendStream: async (
    request: SendMessageRequest,
    onChunk: (chunk: string) => void,
    onDone: (messageId: string) => void,
    onError: (err: string) => void,
    signal?: AbortSignal
  ): Promise<void> => {
    const token = getAccessToken();

    let response: Response;
    try {
      response = await fetch(`${BASE_URL}/chat/send_stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(request),
        signal,
      });
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      onError('Ошибка подключения к серверу');
      return;
    }

    if (!response.ok) {
      onError(`Ошибка сервера: ${response.status}`);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      onError('Стриминг не поддерживается');
      return;
    }

    const decoder = new TextDecoder();
    let messageId = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const raw = decoder.decode(value, { stream: true });
        // Формат SSE: "data: {...}\n\n"
        const lines = raw.split('\n').filter((l) => l.startsWith('data:'));
        for (const line of lines) {
          const json = line.replace('data:', '').trim();
          if (json === '[DONE]') {
            onDone(messageId);
            return;
          }
          try {
            const parsed = JSON.parse(json);
            if (parsed.message_id) messageId = parsed.message_id;
            if (parsed.content) onChunk(parsed.content);
          } catch {
            // plain text chunk
            onChunk(json);
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      onError('Ошибка при получении ответа');
    } finally {
      reader.releaseLock();
      onDone(messageId);
    }
  },
};
