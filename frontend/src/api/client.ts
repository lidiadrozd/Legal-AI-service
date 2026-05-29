import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getRestApiBaseUrl } from '@/config/apiEnv';
import { getAccessToken, getRefreshToken, getRememberMe, setTokens, clearTokens } from '@/utils/tokenStorage';

const BASE_URL = getRestApiBaseUrl();

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
});

// Добавляем access token к каждому запросу
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // FormData: убрать Content-Type, иначе axios/json ломает boundary multipart.
  if (config.data instanceof FormData && config.headers) {
    const h = config.headers as { delete?: (key: string) => void } & Record<string, unknown>;
    if (typeof h.delete === 'function') {
      h.delete('Content-Type');
    } else {
      delete h['Content-Type'];
      delete h['content-type'];
    }
  }
  return config;
});

let isRefreshing = false;
let refreshQueue: Array<(token: string) => void> = [];

function processQueue(token: string) {
  refreshQueue.forEach((cb) => cb(token));
  refreshQueue = [];
}

// При ответе 401 — тихо обновляем токен и повторяем запрос
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !original._retry) {
      const refreshToken = getRefreshToken();

      if (!refreshToken) {
        clearTokens();
        window.location.href = '/login';
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve) => {
          refreshQueue.push((token: string) => {
            original.headers.Authorization = `Bearer ${token}`;
            resolve(apiClient(original));
          });
        });
      }

      original._retry = true;
      isRefreshing = true;

      try {
        const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const newAccessToken = data.access_token;
        const newRefreshToken = data.refresh_token ?? refreshToken;

        setTokens(newAccessToken, newRefreshToken, getRememberMe());
        processQueue(newAccessToken);

        original.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(original);
      } catch {
        clearTokens();
        window.location.href = '/login';
        return Promise.reject(error);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;

