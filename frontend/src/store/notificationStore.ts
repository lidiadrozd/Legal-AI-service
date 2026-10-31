import { create } from 'zustand';
import { z } from 'zod';
import { notificationsApi } from '@/api/notifications';

const notificationMetaSchema = z.object({
  notification_basis: z.enum(['article_change', 'personal_relevance']).optional(),
  personal_relevance_checked: z.boolean().optional(),
  law_change_id: z.number().int().positive().optional(),
  chat_id: z.number().int().positive().nullable().optional(),
  related_chat_ids: z.array(z.number().int().positive()).optional(),
  reference_ids: z.array(z.number().int().positive()).optional(),
  norms: z.array(z.object({
    document_key: z.string(), article: z.string(), part: z.string(), point: z.string(),
  })).optional(),
  reasons: z.array(z.string()).optional(),
  topic_key: z.string().optional(),
  topic_label: z.string().optional(),
});

export type NotificationMeta = z.infer<typeof notificationMetaSchema>;

export function parseNotificationMeta(raw: unknown): NotificationMeta | undefined {
  const parsed = notificationMetaSchema.safeParse(raw);
  return parsed.success ? parsed.data : undefined;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  icon: string;
  read: boolean;
  createdAt: string;
  meta?: NotificationMeta;
}

export interface ServerNotificationRow {
  id: number;
  title: string;
  message: string;
  notification_type?: string | null;
  severity?: string | null;
  is_read: boolean;
  created_at: string;
  meta?: NotificationMeta | null;
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
  meta?: NotificationMeta;
};

interface NotificationActions {
  addNotification: (n: IncomingNotification) => void;
  hydrateFromServer: (rows: ServerNotificationRow[]) => void;
  markAllRead: () => Promise<void>;
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
        meta: n.meta,
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
      meta: parseNotificationMeta(row.meta),
    }));
    const unreadCount = notifications.filter((n) => !n.read).length;
    set({ notifications, unreadCount });
  },

  markAllRead: async () => {
    const unread = useNotificationStore
      .getState()
      .notifications.filter((n) => !n.read && n.id.startsWith('db-'));

    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }));

    await Promise.allSettled(
      unread.map((n) => {
        const numericId = Number(n.id.slice(3));
        return Number.isFinite(numericId)
          ? notificationsApi.markAsRead(numericId)
          : Promise.resolve();
      })
    );
  },

  clearAll: () => set({ notifications: [], unreadCount: 0 }),
}));

