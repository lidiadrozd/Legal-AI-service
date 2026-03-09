const RU_LOCALE = 'ru-RU';

export function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat(RU_LOCALE, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date(dateStr));
}

export function formatDateTime(dateStr: string): string {
  return new Intl.DateTimeFormat(RU_LOCALE, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(dateStr));
}

export function formatTime(dateStr: string): string {
  return new Intl.DateTimeFormat(RU_LOCALE, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(dateStr));
}

export function formatShortDate(dateStr: string): string {
  return new Intl.DateTimeFormat(RU_LOCALE, {
    day: 'numeric',
    month: 'short',
  }).format(new Date(dateStr));
}

export function formatRelative(dateStr: string): string {
  const now = Date.now();
  const date = new Date(dateStr).getTime();
  const diff = now - date;

  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diff < minute) return 'только что';
  if (diff < hour) return `${Math.floor(diff / minute)} мин. назад`;
  if (diff < day) return `${Math.floor(diff / hour)} ч. назад`;
  if (diff < 2 * day) return 'вчера';
  return formatShortDate(dateStr);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}
