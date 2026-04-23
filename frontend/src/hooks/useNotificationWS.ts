import { useEffect, useRef } from 'react';
import { getNotificationWebSocketUrl } from '@/config/apiEnv';
import { useAuthStore } from '@/store/authStore';
import { useNotificationStore, type IncomingNotification } from '@/store/notificationStore';
import { useUIStore } from '@/store/uiStore';

const RECONNECT_DELAY_MS = 3000;

export function useNotificationWS() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const addNotification = useNotificationStore((s) => s.addNotification);
  const addToast = useUIStore((s) => s.addToast);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) return;

    unmountedRef.current = false;

    function connect() {
      if (unmountedRef.current) return;

      const url = getNotificationWebSocketUrl(accessToken);
      let ws: WebSocket;

      try {
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }

      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as Record<string, unknown>;
          const rawId = data.id;
          const serverId =
            typeof rawId === 'number'
              ? rawId
              : typeof rawId === 'string' && /^\d+$/.test(rawId)
                ? parseInt(rawId, 10)
                : undefined;
          const rawSev = data.severity;
          const severity =
            rawSev === 'low' ||
            rawSev === 'medium' ||
            rawSev === 'high' ||
            rawSev === 'critical'
              ? rawSev
              : 'medium';
          const body =
            typeof data.message === 'string'
              ? data.message
              : typeof data.body === 'string'
                ? data.body
                : '';
          const createdAt =
            typeof data.timestamp === 'string' ? data.timestamp : undefined;
          const notification: IncomingNotification = {
            title: typeof data.title === 'string' ? data.title : 'Уведомление',
            body,
            severity,
            icon: typeof data.icon === 'string' ? data.icon : '🔔',
            serverId,
            createdAt,
          };
          addNotification(notification);
          if (notification.severity === 'high' || notification.severity === 'critical') {
            addToast({ message: notification.title, type: 'warning' });
          }
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (!unmountedRef.current) scheduleReconnect();
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    function scheduleReconnect() {
      reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
    }

    connect();

    return () => {
      unmountedRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [isAuthenticated, accessToken, addNotification, addToast]);
}
