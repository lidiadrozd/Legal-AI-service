import apiClient from './client';
import type { FeedbackRequest } from '@/types/chat.types';

export const feedbackApi = {
  submit: async (data: FeedbackRequest): Promise<void> => {
    const messageId = Number.parseInt(data.message_id, 10);
    if (!Number.isFinite(messageId)) {
      throw new Error('Invalid message_id');
    }
    await apiClient.post('/chat/feedback', {
      message_id: messageId,
      rating: data.rating,
    });
  },
};
