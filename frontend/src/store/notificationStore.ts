import { create } from 'zustand';
import { notificationsApi } from '@/api/notifications';

export interface Notification {
  id: string;
  title: string;
  body: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  icon: string;
  read: boolean;
  createdAt: string;
}

export interface ServerNotificationRow {
  id: number;
  title: string;
  message: string;
  notification_type?: string | null;
  severity?: string | null;
  is_read: boolean;
  created_at: string;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
}

export type IncomingNotification = {
  title: string;
  body: string;
  severity: Notification['severity'];
  icon: string;
  serverId?: number;
  createdAt?: string;
};

interface NotificationActions {
  addNotification: (n: IncomingNotification) => void;
  hydrateFromServer: (rows: ServerNotificationRow[]) => void;
  markAllRead: () => Promise<void>;
  clearAll: () => void;
}

function normalizeSeverity(
  raw: string | null | undefined,
): Notification['severity'] {
  const value = (raw || 'medium').toLowerCase();

  if (
    value === 'low' ||
    value === 'medium' ||
    value === 'high' ||
    value === 'critical'
  ) {
    return value;
  }

  return 'medium';
}

export const useNotificationStore = create<
  NotificationState & NotificationActions
>((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (n) => {
    const id =
      n.serverId != null
        ? `db-${n.serverId}`
        : crypto.randomUUID();

    set((state) => {
      if (state.notifications.some((item) => item.id === id)) {
        return state;
      }

      const notification: Notification = {
        id,
        title: n.title,
        body: n.body,
        severity: n.severity,
        icon: n.icon,
        read: false,
        createdAt: n.createdAt ?? new Date().toISOString(),
      };

      return {
        notifications: [
          notification,
          ...state.notifications,
        ],
        unreadCount: state.unreadCount + 1,
      };
    });
  },

  hydrateFromServer: (rows) => {
    const serverNotifications: Notification[] = rows.map((row) => ({
      id: `db-${row.id}`,
      title: row.title,
      body: row.message,
      severity: normalizeSeverity(row.severity),
      icon: '🔔',
      read: row.is_read,
      createdAt: row.created_at,
    }));

    const currentNotifications =
      useNotificationStore.getState().notifications;

    // Запоминаем ID уведомлений, полученных с сервера.
    const serverIds = new Set(
      serverNotifications.map((notification) => notification.id),
    );

   
    const transientNotifications = currentNotifications.filter(
      (notification) =>
        !notification.id.startsWith('db-') &&
        !serverIds.has(notification.id),
    );

    const mergedNotifications = [
      ...transientNotifications,
      ...serverNotifications,
    ].sort(
      (a, b) =>
        new Date(b.createdAt).getTime() -
        new Date(a.createdAt).getTime(),
    );

    const unreadCount = mergedNotifications.filter(
      (notification) => !notification.read,
    ).length;

    set({
      notifications: mergedNotifications,
      unreadCount,
    });
  },

  markAllRead: async () => {
    const unread = useNotificationStore
      .getState()
      .notifications.filter(
        (notification) =>
          !notification.read &&
          notification.id.startsWith('db-'),
      );

    // Оптимистично обновляем интерфейс.
    set((state) => ({
      notifications: state.notifications.map(
        (notification) => ({
          ...notification,
          read: true,
        }),
      ),
      unreadCount: 0,
    }));

    await Promise.allSettled(
      unread.map((notification) => {
        const numericId = Number(
          notification.id.slice(3),
        );

        return Number.isFinite(numericId)
          ? notificationsApi.markAsRead(numericId)
          : Promise.resolve();
      }),
    );
  },

  clearAll: () =>
    set({
      notifications: [],
      unreadCount: 0,
    }),
}));

