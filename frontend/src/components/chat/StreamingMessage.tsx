import styled, { keyframes } from 'styled-components';

const blink = keyframes`
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
`;

const Wrap = styled.div`
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 4px 24px;
`;

const Bubble = styled.div`
  max-width: min(680px, 80%);
  padding: 12px 16px;
  border-radius: 4px 18px 18px 18px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  line-height: 1.65;
  word-break: break-word;
  white-space: pre-wrap;
`;

const Cursor = styled.span`
  display: inline-block;
  width: 2px;
  height: 14px;
  background: var(--color-primary);
  margin-left: 2px;
  vertical-align: middle;
  border-radius: 1px;
  animation: ${blink} 900ms step-end infinite;
`;

const TypingDots = styled.div`
  display: flex;
  gap: 4px;
  padding: 4px 0;
`;

const Dot = styled.span<{ $delay: number }>`
  width: 6px;
  height: 6px;
  background: var(--color-text-tertiary);
  border-radius: 50%;
  animation: ${blink} 1.2s ${({ $delay }) => $delay}s ease-in-out infinite;
`;

interface Props {
  content: string;
}

export function StreamingMessage({ content }: Props) {
  return (
    <Wrap>
      <Bubble>
        {content ? (
          <>
            {content}
            <Cursor />
          </>
        ) : (
          <TypingDots>
            <Dot $delay={0} />
            <Dot $delay={0.2} />
            <Dot $delay={0.4} />
          </TypingDots>
        )}
      </Bubble>
    </Wrap>
  );
}
