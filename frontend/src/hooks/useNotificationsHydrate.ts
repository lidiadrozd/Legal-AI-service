import { useEffect } from 'react';
import apiClient from '@/api/client';
import { useAuthStore } from '@/store/authStore';
import { useNotificationStore, type ServerNotificationRow } from '@/store/notificationStore';

export function useNotificationsHydrate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hydrateFromServer = useNotificationStore((s) => s.hydrateFromServer);
  const clearAll = useNotificationStore((s) => s.clearAll);

  useEffect(() => {
    if (!isAuthenticated) {
      clearAll();
      return;
    }

    let cancelled = false;
    apiClient
      .get<ServerNotificationRow[]>('/notifications', { params: { limit: 100 } })
      .then((res) => {
        if (!cancelled) hydrateFromServer(res.data);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, hydrateFromServer, clearAll]);
}
