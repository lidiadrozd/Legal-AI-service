import { create } from 'zustand';

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
  markAllRead: () => void;
  clearAll: () => void;
}

function normalizeSeverity(raw: string | null | undefined): Notification['severity'] {
  const v = (raw || 'medium').toLowerCase();
  if (v === 'low' || v === 'medium' || v === 'high' || v === 'critical') return v;
  return 'medium';
}

export const useNotificationStore = create<NotificationState & NotificationActions>((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (n) => {
    const id = n.serverId != null ? `db-${n.serverId}` : crypto.randomUUID();
    set((s) => {
      if (s.notifications.some((x) => x.id === id)) return s;
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
        notifications: [notification, ...s.notifications],
        unreadCount: s.unreadCount + 1,
      };
    });
  },

  hydrateFromServer: (rows) => {
    const notifications: Notification[] = rows.map((row) => ({
      id: `db-${row.id}`,
      title: row.title,
      body: row.message,
      severity: normalizeSeverity(row.severity),
      icon: '🔔',
      read: row.is_read,
      createdAt: row.created_at,
    }));
    const unreadCount = notifications.filter((n) => !n.read).length;
    set({ notifications, unreadCount });
  },

  markAllRead: () =>
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),

  clearAll: () => set({ notifications: [], unreadCount: 0 }),
}));

