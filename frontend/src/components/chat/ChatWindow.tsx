import { useEffect, useRef } from 'react';
import styled from 'styled-components';
import { useChatStore } from '@/store/chatStore';
import { MessageBubble } from './MessageBubble';
import { StreamingMessage } from './StreamingMessage';

const Wrap = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 24px 0 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

const Empty = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  gap: 12px;
  padding: 40px 24px;
  text-align: center;
`;

const EmptyTitle = styled.div`
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--color-text-secondary);
`;

const EmptyHint = styled.div`
  font-size: var(--font-size-sm);
  max-width: 320px;
  line-height: 1.6;
`;

const SuggestionGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 8px;
  max-width: 500px;
  width: 100%;

  @media (max-width: 480px) {
    grid-template-columns: 1fr;
  }
`;

const SuggestionCard = styled.button`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  text-align: left;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.4;
  transition: border-color var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-text);
    background: var(--color-primary-muted);
  }
`;

const SUGGESTIONS = [
  'Как уволить сотрудника по закону?',
  'Что делать, если залили соседи?',
  'Как составить договор аренды?',
  'Права потребителя при возврате товара',
];

interface ChatWindowProps {
  onSuggestionClick?: (text: string) => void;
}

export function ChatWindow({ onSuggestionClick }: ChatWindowProps) {
  const { messages, isStreaming, streamingContent } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  if (messages.length === 0 && !isStreaming) {
    return (
      <Wrap>
        <Empty>
          <EmptyTitle>Задайте юридический вопрос</EmptyTitle>
          <EmptyHint>
            Я помогу с вопросами трудового, гражданского, жилищного и других отраслей права.
          </EmptyHint>
          <SuggestionGrid>
            {SUGGESTIONS.map((s) => (
              <SuggestionCard key={s} onClick={() => onSuggestionClick?.(s)}>
                {s}
              </SuggestionCard>
            ))}
          </SuggestionGrid>
        </Empty>
      </Wrap>
    );
  }

  return (
    <Wrap>
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isStreaming && <StreamingMessage content={streamingContent} />}
      <div ref={bottomRef} />
    </Wrap>
  );
}
