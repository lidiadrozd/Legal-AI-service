import { useState } from 'react';
import styled from 'styled-components';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { feedbackApi } from '@/api/feedback';
import { useChatStore } from '@/store/chatStore';
import { useUIStore } from '@/store/uiStore';
import type { FeedbackRating } from '@/types/chat.types';

const Wrap = styled.div`
  display: flex;
  gap: 4px;
`;

const FBtn = styled.button<{ $active?: boolean; $type: 'up' | 'down' }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid ${({ $active, $type }) => {
    if (!$active) return 'transparent';
    return $type === 'up' ? 'var(--color-success)' : 'var(--color-error)';
  }};
  background: ${({ $active, $type }) => {
    if (!$active) return 'transparent';
    return $type === 'up' ? 'var(--color-success-muted)' : 'var(--color-error-muted)';
  }};
  color: ${({ $active, $type }) => {
    if (!$active) return 'var(--color-text-tertiary)';
    return $type === 'up' ? 'var(--color-success)' : 'var(--color-error)';
  }};
  transition: all var(--transition-fast);
  &:hover {
    background: ${({ $type }) =>
      $type === 'up' ? 'var(--color-success-muted)' : 'var(--color-error-muted)'};
    color: ${({ $type }) =>
      $type === 'up' ? 'var(--color-success)' : 'var(--color-error)'};
    border-color: ${({ $type }) =>
      $type === 'up' ? 'var(--color-success)' : 'var(--color-error)'};
  }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
`;

interface Props {
  messageId: string;
  currentRating?: FeedbackRating;
}

export function FeedbackButtons({ messageId, currentRating }: Props) {
  const [loading, setLoading] = useState(false);
  const setMessageFeedback = useChatStore((s) => s.setMessageFeedback);
  const addToast = useUIStore((s) => s.addToast);

  const handleRate = async (rating: FeedbackRating) => {
    if (currentRating === rating || loading) return;
    setLoading(true);
    try {
      await feedbackApi.submit({ message_id: messageId, rating });
      setMessageFeedback(messageId, rating);
    } catch {
      addToast({ message: 'Не удалось отправить оценку', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Wrap>
      <FBtn
        $type="up"
        $active={currentRating === 'up'}
        disabled={loading}
        onClick={() => handleRate('up')}
        title="Полезно"
      >
        <ThumbsUp size={13} />
      </FBtn>
      <FBtn
        $type="down"
        $active={currentRating === 'down'}
        disabled={loading}
        onClick={() => handleRate('down')}
        title="Не помогло"
      >
        <ThumbsDown size={13} />
      </FBtn>
    </Wrap>
  );
}
