import axios, { type AxiosError } from 'axios';

const DETAIL_RU: Record<string, string> = {
  'Email already registered':
    'Этот email уже зарегистрирован. Войдите или укажите другой адрес.',
  'Incorrect email or password': 'Неверный email или пароль.',
};

function normalizeDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return DETAIL_RU[detail] ?? detail;
  }
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item: { msg?: string }) => item.msg)
      .filter(Boolean) as string[];
    if (msgs.length) return msgs.join(' ');
  }
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    return detail.message;
  }
  return null;
}

/** Текст ошибки из ответа FastAPI/Axios или запасная строка. */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const err = error as AxiosError<{ detail?: unknown; error?: unknown }>;
    if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT') {
      return 'Сервер не успел ответить за отведённое время. Модель могла ещё обрабатывать запрос; проверьте список чатов перед повторной попыткой.';
    }
    if (!err.response) {
      return 'Не удалось связаться с сервером. Проверьте подключение и повторите попытку.';
    }
    const data = err.response.data;
    const msg =
      normalizeDetail(data?.detail) ??
      normalizeDetail(data?.error);
    if (msg) return msg;
    if (err.response.status >= 500) {
      return `Ошибка сервера (${err.response.status}). Смотрите лог в терминале uvicorn.`;
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
