import { useLayoutEffect, useRef } from 'react';
import styled from 'styled-components';
import { useChatStore } from '@/store/chatStore';
import { MessageBubble } from './MessageBubble';
import { StreamingMessage } from './StreamingMessage';

const Wrap = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  padding: 24px 0 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  > * { flex-shrink: 0; }
`;

const Messages = styled.div`
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
  const { messages, isStreaming, streamingContent, activeChat } = useChatStore();
  const activeChatId = activeChat?.id;
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const lastUserRef = useRef<number | string | undefined>();

  // Scroll this pane only. Smooth scrolls on every token can lag behind the
  // stream; observing content and viewport also catches Markdown/layout reflow.
  useLayoutEffect(() => { followRef.current = true; }, [activeChatId]);
  useLayoutEffect(() => {
    const userMessages = messages.filter(message => message.role === 'user');
    const lastUser = userMessages[userMessages.length - 1]?.id;
    if (lastUser !== lastUserRef.current) followRef.current = true;
    lastUserRef.current = lastUser;
    const pane = scrollRef.current;
    if (pane && followRef.current) pane.scrollTop = pane.scrollHeight;
  }, [messages, streamingContent, isStreaming, activeChatId]);

  useLayoutEffect(() => {
    const pane = scrollRef.current;
    const content = contentRef.current;
    if (!pane || !content) return;
    const observer = new ResizeObserver(() => {
      if (followRef.current) pane.scrollTop = pane.scrollHeight;
    });
    observer.observe(pane);
    observer.observe(content);
    return () => observer.disconnect();
  }, [messages.length === 0 && !isStreaming]);

  if (messages.length === 0 && !isStreaming) {
    return (
      <Wrap>
        <Empty>
          <EmptyTitle>Задайте юридический вопрос</EmptyTitle>
          <EmptyHint>
            Я помогу с вопросами трудового, гражданского, жилищного и других отраслей права. Готовые файлы (Word, PDF) — ссылка «Документы Word / PDF / TXT» под полем ввода.
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
    <Wrap ref={scrollRef} onScroll={() => {
      const pane = scrollRef.current;
      if (pane) followRef.current = pane.scrollHeight - pane.clientHeight - pane.scrollTop < 48;
    }}>
      <Messages ref={contentRef}>
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isStreaming && <StreamingMessage content={streamingContent} />}
      </Messages>
    </Wrap>
  );
}
