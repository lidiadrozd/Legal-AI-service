import apiClient from './client';
import type { FeedbackRequest } from '@/types/chat.types';

export const feedbackApi = {
  submit: async (data: FeedbackRequest): Promise<void> => {
    await apiClient.post('/feedback', data);
  },
};
