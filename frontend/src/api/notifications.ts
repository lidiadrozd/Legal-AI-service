import apiClient from './client';
import type { ServerNotificationRow } from '@/store/notificationStore';

export const notificationsApi = {
  list: async (params?: { limit?: number; offset?: number; is_read?: boolean }) => {
    const response = await apiClient.get<ServerNotificationRow[]>('/notifications', {
      params: { limit: 100, ...params },
    });
    return response.data;
  },

  markAsRead: async (id: number): Promise<ServerNotificationRow> => {
    const response = await apiClient.patch<ServerNotificationRow>(
      `/notifications/${id}/read`
    );
    return response.data;
  },
};
