const ACCESS_KEY = 'ai_lawyer_access_token';
const REFRESH_KEY = 'ai_lawyer_refresh_token';
const REMEMBER_KEY = 'ai_lawyer_remember';

function storage(persistent: boolean): Storage {
  return persistent ? localStorage : sessionStorage;
}

export function getRememberMe(): boolean {
  return localStorage.getItem(REMEMBER_KEY) !== '0';
}

export function setRememberMe(remember: boolean): void {
  if (remember) {
    localStorage.removeItem(REMEMBER_KEY);
  } else {
    localStorage.setItem(REMEMBER_KEY, '0');
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY) ?? sessionStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY) ?? sessionStorage.getItem(REFRESH_KEY);
}

export function setTokens(accessToken: string, refreshToken: string, remember = true): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);

  const store = storage(remember);
  store.setItem(ACCESS_KEY, accessToken);
  store.setItem(REFRESH_KEY, refreshToken);
  setRememberMe(remember);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}
