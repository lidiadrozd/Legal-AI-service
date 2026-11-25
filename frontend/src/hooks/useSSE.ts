import { useRef, useCallback, useEffect } from 'react';
import { useChatStore } from '@/store/chatStore';
import { useUIStore } from '@/store/uiStore';
import { chatApi } from '@/api/chat';
import type { Message, SendMessageRequest } from '@/types/chat.types';

/**
 * Хук управления SSE-стримингом ответа LLM через fetch + ReadableStream.
 */
export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);
  const onlineRecoveryRef = useRef<(() => void) | null>(null);
  const addToast = useUIStore((s) => s.addToast);
  const { startStreaming, appendStreamChunk, finishStreaming, isStreaming } = useChatStore();

  useEffect(() => () => {
    if (onlineRecoveryRef.current) window.removeEventListener('online', onlineRecoveryRef.current);
  }, []);

  const stream = useCallback(
    async (request: SendMessageRequest, onRecovered?: (chatId: string) => void | Promise<void>) => {
      if (useChatStore.getState().isStreaming) return;

      abortRef.current = new AbortController();
      startStreaming();
      let streamError: string | null = null;

      await chatApi.sendStream(
        request,
        (chunk) => {
          if (useChatStore.getState().activeChat?.id === request.chat_id) appendStreamChunk(chunk);
        },
        (msgId) => {
          if (useChatStore.getState().activeChat?.id === request.chat_id) finishStreaming(msgId);
        },
        (err) => {
          streamError = err;
          if (useChatStore.getState().activeChat?.id === request.chat_id) finishStreaming('');
        },
        abortRef.current.signal
      );

      if (streamError) {
        const recover = async (delays = [0, 1200, 3000]): Promise<void> => {
          let lastHistory: Message[] | null = null;
          let responseSaved = false;
          for (const delay of delays) {
            if (delay) await new Promise((resolve) => window.setTimeout(resolve, delay));
            try {
              lastHistory = await chatApi.getChatHistory(request.chat_id);
            } catch {
              lastHistory = null;
              continue;
            }
            const lastUser = lastHistory.map((message) => message.role).lastIndexOf('user');
            responseSaved = lastHistory.slice(lastUser + 1)
              .some((message) => message.role === 'assistant' && message.content.trim().length > 0);
            if (responseSaved) break;
          }

          if (lastHistory) {
            const visibleHistory = lastHistory.filter(
              (message) => message.role !== 'assistant' || message.content.trim().length > 0,
            );
            const currentState = useChatStore.getState();
            const isActive = currentState.activeChat?.id === request.chat_id && !currentState.isStreaming;
            if (isActive) {
              useChatStore.getState().setMessages(visibleHistory);
              await onRecovered?.(request.chat_id);
            }
            if (onlineRecoveryRef.current) {
              window.removeEventListener('online', onlineRecoveryRef.current);
              onlineRecoveryRef.current = null;
            }
            addToast({
              message: responseSaved
                ? 'Связь прервалась, но сохранённая история чата восстановлена.'
                : 'Ответ пользователя сохранён. Если следующий вопрос не появился, напишите «повтори».',
              type: responseSaved ? 'info' : 'error',
            });
            return;
          }

          addToast({
            message: `${streamError}. После восстановления сети история чата обновится автоматически.`,
            type: 'error',
          });
          if (onlineRecoveryRef.current) window.removeEventListener('online', onlineRecoveryRef.current);
          const retry = () => { void recover([0, 1200, 3000]); };
          onlineRecoveryRef.current = retry;
          window.addEventListener('online', retry, { once: true });
        };
        void recover();
      }
      // Refresh subjects after server-side classification or clarification.
      const chats = await chatApi.getChats().catch(() => null);
      if (chats) useChatStore.getState().setChats(chats);
    },
    [isStreaming, startStreaming, appendStreamChunk, finishStreaming, addToast]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    finishStreaming('');
  }, [finishStreaming]);

  return { stream, cancel, isStreaming };
}
