import apiClient from './client';
import { getRestApiBaseUrl } from '@/config/apiEnv';
import { getAccessToken } from '@/utils/tokenStorage';
import type { Chat, Message, CreateChatResponse, SendMessageRequest } from '@/types/chat.types';

const STREAM_BASE_URL = getRestApiBaseUrl();

export const chatApi = {
  createChat: async (): Promise<CreateChatResponse> => {
    const response = await apiClient.post<{ id: number; title: string | null }>('/chat/new');
    return {
      chat_id: String(response.data.id),
      title: response.data.title ?? 'Новый чат',
    };
  },

  getChats: async (): Promise<Chat[]> => {
    const response = await apiClient.get<
      Array<{
        id: number;
        user_id: number | null;
        title: string | null;
        message_count?: number;
        created_at: string;
        last_message_at?: string | null;
      }>
    >('/chat/list');

    return response.data.map((chat) => ({
      id: String(chat.id),
      user_id: chat.user_id ? String(chat.user_id) : '',
      title: chat.title ?? 'Новый чат',
      message_count: chat.message_count ?? 0,
      created_at: chat.created_at,
      updated_at: chat.last_message_at ?? chat.created_at,
    }));
  },

  getChatHistory: async (chatId: string): Promise<Message[]> => {
    const response = await apiClient.get<
      Array<{
        id: number;
        chat_id: number;
        role: 'user' | 'assistant';
        content: string;
        created_at: string;
      }>
    >(`/chat/${chatId}/history`);

    return response.data.map((message) => ({
      id: String(message.id),
      chat_id: String(message.chat_id),
      role: message.role,
      content: message.content,
      created_at: message.created_at,
    }));
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
      response = await fetch(`${STREAM_BASE_URL}/chat/${request.chat_id}/send_stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content: request.content }),
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
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';

        for (const event of events) {
          const dataLines = event
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart());
          if (dataLines.length === 0) continue;

          const payload = dataLines.join('\n');
          if (payload === '[DONE]') {
            onDone(messageId);
            return;
          }

          try {
            const parsed = JSON.parse(payload);
            if (parsed.message_id) messageId = parsed.message_id;
            if (typeof parsed.content === 'string') onChunk(parsed.content);
          } catch {
            // Совместимость со старым plain-text форматом
            onChunk(payload);
          }
        }
      }

      // Обрабатываем хвост, если сервер закрыл соединение без финального \n\n
      if (buffer.trim()) {
        const line = buffer
          .split('\n')
          .find((entry) => entry.startsWith('data:'));
        if (line) {
          const payload = line.slice(5).trimStart();
          if (payload && payload !== '[DONE]') {
            try {
              const parsed = JSON.parse(payload);
              if (typeof parsed.content === 'string') onChunk(parsed.content);
            } catch {
              onChunk(payload);
            }
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


