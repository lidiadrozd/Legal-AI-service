import { useRef, useCallback } from 'react';
import { useChatStore } from '@/store/chatStore';
import { useUIStore } from '@/store/uiStore';
import { chatApi } from '@/api/chat';
import type { ChatGeneratedDocument, SendMessageRequest } from '@/types/chat.types';

/**
 * Хук управления SSE-стримингом ответа LLM через fetch + ReadableStream.
 */
export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);
  const addToast = useUIStore((s) => s.addToast);
  const { startStreaming, appendStreamChunk, finishStreaming, isStreaming } = useChatStore();

  const stream = useCallback(
    async (
      request: SendMessageRequest,
      opts?: {
        onTitle?: (title: string) => void;
        onGeneratedDocument?: (doc: ChatGeneratedDocument) => void;
      }
    ) => {
      if (isStreaming) return;

      abortRef.current = new AbortController();
      startStreaming();

      await chatApi.sendStream(
        request,
        (chunk) => appendStreamChunk(chunk),
        (msgId) => finishStreaming(msgId),
        (err) => {
          finishStreaming('');
          addToast({ message: err, type: 'error' });
        },
        abortRef.current.signal,
        opts?.onTitle,
        opts?.onGeneratedDocument
      );
    },
    [isStreaming, startStreaming, appendStreamChunk, finishStreaming, addToast]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    finishStreaming('');
  }, [finishStreaming]);

  return { stream, cancel, isStreaming };
}
