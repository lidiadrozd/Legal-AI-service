import { create } from 'zustand';
import { persist } from 'zustand/middleware';
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
  setAuth: (user: User, access: string, refresh: string) => void;
  setConsentGiven: () => void;
  updateUser: (user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState & AuthActions>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isConsentGiven: false,
      isAuthenticated: false,

      setAuth: (user, access, refresh) => {
        setTokens(access, refresh);
        set({
          user,
          accessToken: access,
          refreshToken: refresh,
          isAuthenticated: true,
          isConsentGiven: user.is_consent_given,
        });
      },

      setConsentGiven: () =>
        set((state) => ({
          isConsentGiven: true,
          user: state.user ? { ...state.user, is_consent_given: true } : null,
        })),

      updateUser: (user) => set({ user, isConsentGiven: user.is_consent_given }),

      logout: () => {
        clearTokens();
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isConsentGiven: false,
        });
      },
    }),
    {
      name: 'ai-lawyer-auth',
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isConsentGiven: state.isConsentGiven,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
