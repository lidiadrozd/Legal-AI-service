import { useEffect } from 'react';
import { notificationsApi } from '@/api/notifications';
import { useAuthStore } from '@/store/authStore';
import { useNotificationStore } from '@/store/notificationStore';

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
    notificationsApi
      .list({ limit: 100 })
      .then((rows) => {
        if (!cancelled) hydrateFromServer(rows);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, hydrateFromServer, clearAll]);
}
