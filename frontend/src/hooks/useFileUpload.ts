import { useEffect, useRef } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useNotificationStore } from '@/store/notificationStore';
import { useUIStore } from '@/store/uiStore';

const RECONNECT_DELAY_MS = 3000;

function getWsBaseUrl(): string {
  const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
  return apiUrl.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://');
}

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

      const url = `${getWsBaseUrl()}/ws/notifications?token=${accessToken}`;
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
          const data = JSON.parse(event.data);
          const notification = {
            title: data.title ?? 'Уведомление',
            body: data.body ?? '',
            severity: data.severity ?? 'medium',
            icon: data.icon ?? '🔔',
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

