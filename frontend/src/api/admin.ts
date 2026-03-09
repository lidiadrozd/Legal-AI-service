import apiClient from './client';
import type { AdminUser, AdminChat, AdminFeedbackItem, AdminStats } from '@/types/admin.types';

export const adminApi = {
  getUsers: async (search?: string): Promise<AdminUser[]> => {
    const response = await apiClient.get<AdminUser[]>('/admin/users', {
      params: search ? { search } : undefined,
    });
    return response.data;
  },

  getUserChats: async (userId: string): Promise<AdminChat[]> => {
    const response = await apiClient.get<AdminChat[]>(`/admin/users/${userId}/chats`);
    return response.data;
  },

  getAllChats: async (): Promise<AdminChat[]> => {
    const response = await apiClient.get<AdminChat[]>('/admin/chats');
    return response.data;
  },

  getChatMessages: async (chatId: string) => {
    const response = await apiClient.get(`/admin/chats/${chatId}/messages`);
    return response.data;
  },

  getFeedback: async (ratingFilter?: 'up' | 'down'): Promise<AdminFeedbackItem[]> => {
    const response = await apiClient.get<AdminFeedbackItem[]>('/admin/feedback', {
      params: ratingFilter ? { rating: ratingFilter } : undefined,
    });
    return response.data;
  },

  getStats: async (): Promise<AdminStats> => {
    const response = await apiClient.get<AdminStats>('/admin/stats');
    return response.data;
  },

  toggleUserActive: async (userId: string, isActive: boolean): Promise<void> => {
    await apiClient.patch(`/admin/users/${userId}`, { is_active: isActive });
  },
};
