import { useRef, useCallback } from 'react';
import { useChatStore } from '@/store/chatStore';
import { useUIStore } from '@/store/uiStore';
import { chatApi } from '@/api/chat';
import type { SendMessageRequest } from '@/types/chat.types';

/**
 * Хук управления SSE-стримингом ответа LLM через fetch + ReadableStream.
 */
export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);
  const addToast = useUIStore((s) => s.addToast);
  const { startStreaming, appendStreamChunk, finishStreaming, isStreaming } = useChatStore();

  const stream = useCallback(
    async (request: SendMessageRequest) => {
      if (useChatStore.getState().isStreaming) return;

      abortRef.current = new AbortController();
      startStreaming();

      await chatApi.sendStream(
        request,
        (chunk) => {
          if (useChatStore.getState().activeChat?.id === request.chat_id) appendStreamChunk(chunk);
        },
        (msgId) => {
          if (useChatStore.getState().activeChat?.id === request.chat_id) finishStreaming(msgId);
        },
        (err) => {
          if (useChatStore.getState().activeChat?.id === request.chat_id) finishStreaming('');
          addToast({ message: err, type: 'error' });
        },
        abortRef.current.signal
      );
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
