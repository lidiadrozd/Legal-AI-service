/**
 * База REST без завершающего слэша.
 * `/api` — Vite proxy на локальный бэкенд.
 * Иначе — полный URL из VITE_API_BASE_URL (демо-сервер).
 */
export function getRestApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (raw != null && String(raw).trim() !== '') {
    return String(raw).trim().replace(/\/$/, '');
  }
  return '/api';
}

export function getNotificationWebSocketUrl(accessToken: string): string {
  const token = encodeURIComponent(accessToken);
  const raw = (import.meta.env.VITE_API_BASE_URL ?? '').trim();
  if (!raw || raw === '/api') {
    const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost:3000';
    return `${proto}//${host}/api/ws/notifications?token=${token}`;
  }
  const baseHttp = raw.replace(/\/$/, '');
  const withApi = baseHttp.endsWith('/api') ? baseHttp : `${baseHttp}/api`;
  const wsBase = withApi.replace(/^https:\/\//i, 'wss://').replace(/^http:\/\//i, 'ws://');
  return `${wsBase}/ws/notifications?token=${token}`;
}
