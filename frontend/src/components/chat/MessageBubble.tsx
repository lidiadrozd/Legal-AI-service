import styled from 'styled-components';
import { formatTime } from '@/utils/formatDate';
import { FeedbackButtons } from './FeedbackButtons';
import type { Message } from '@/types/chat.types';
import { Paperclip } from 'lucide-react';

const Wrap = styled.div<{ $isUser: boolean }>`
  display: flex;
  flex-direction: ${({ $isUser }) => ($isUser ? 'row-reverse' : 'row')};
  align-items: flex-end;
  gap: 8px;
  padding: 4px 24px;
  max-width: 100%;
`;

const Bubble = styled.div<{ $isUser: boolean }>`
  max-width: min(680px, 80%);
  padding: 12px 16px;
  border-radius: ${({ $isUser }) =>
    $isUser ? '18px 18px 4px 18px' : '4px 18px 18px 18px'};
  background: ${({ $isUser }) =>
    $isUser ? 'var(--color-primary)' : 'var(--color-surface-card)'};
  color: var(--color-text);
  font-size: var(--font-size-sm);
  line-height: 1.65;
  border: ${({ $isUser }) => ($isUser ? 'none' : '1px solid var(--color-border)')};
  word-break: break-word;
  white-space: pre-wrap;
`;

const Meta = styled.div<{ $isUser: boolean }>`
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: ${({ $isUser }) => ($isUser ? 'flex-end' : 'flex-start')};
  margin-top: 4px;
  padding: 0 4px;
`;

const Time = styled.span`
  font-size: 11px;
  color: var(--color-text-tertiary);
`;

const AttachmentList = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
`;

const AttachmentChip = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-full);
  font-size: 12px;
  color: var(--color-text-secondary);
`;

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';

  return (
    <div>
      <Wrap $isUser={isUser}>
        <Bubble $isUser={isUser}>
          {message.content}
          {message.attachments && message.attachments.length > 0 && (
            <AttachmentList>
              {message.attachments.map((a) => (
                <AttachmentChip key={a.id}>
                  <Paperclip size={12} />
                  {a.filename}
                </AttachmentChip>
              ))}
            </AttachmentList>
          )}
        </Bubble>
      </Wrap>
      <Meta $isUser={isUser}>
        <Time>{formatTime(message.created_at)}</Time>
        {!isUser && (
          <FeedbackButtons messageId={message.id} currentRating={message.feedback} />
        )}
      </Meta>
    </div>
  );
}
