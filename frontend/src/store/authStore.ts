import { create } from 'zustand';
import type { User } from '@/types/auth.types';
import { setTokens, clearTokens } from '@/utils/tokenStorage';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isConsentGiven: boolean;
  isAuthenticated: boolean;
}

interface AuthActions {
  setAuth: (user: User, access: string, refresh: string, remember?: boolean) => void;
  setConsentGiven: () => void;
  updateUser: (user: User) => void;
  logout: () => void;
}

// Remove the legacy persistent copy, including tokens saved without consent to remember.
localStorage.removeItem('ai-lawyer-auth');

export const useAuthStore = create<AuthState & AuthActions>()((set) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isConsentGiven: false,
  isAuthenticated: false,

  setAuth: (user, access, refresh, remember = true) => {
    setTokens(access, refresh, remember);
    set({ user, accessToken: access, refreshToken: refresh,
      isAuthenticated: true, isConsentGiven: user.is_consent_given });
  },
  setConsentGiven: () => set((state) => ({
    isConsentGiven: true,
    user: state.user ? { ...state.user, is_consent_given: true } : null,
  })),
  updateUser: (user) => set({ user, isConsentGiven: user.is_consent_given }),
  logout: () => {
    clearTokens();
    set({ user: null, accessToken: null, refreshToken: null,
      isAuthenticated: false, isConsentGiven: false });
  },
}));
