import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { authApi } from '@/api/auth';
import { useUIStore } from '@/store/uiStore';
import type { LoginRequest, RegisterRequest } from '@/types/auth.types';

export function useAuth() {
  const navigate = useNavigate();
  const { setAuth, setConsentGiven, logout: storeLogout } = useAuthStore();
  const addToast = useUIStore((s) => s.addToast);

  const login = async (data: LoginRequest) => {
    const result = await authApi.login(data);
    setAuth(result.user, result.access_token, result.refresh_token);
    if (!result.user.is_consent_given) {
      navigate('/consent');
    } else {
      navigate('/chat');
    }
  };

  const register = async (data: RegisterRequest, consentGiven = false) => {
    const result = await authApi.register(data);
    setAuth(result.user, result.access_token, result.refresh_token);
    if (consentGiven) {
      await authApi.consent({
        consent_data_processing: true,
        consent_terms: true,
        consent_ai_usage: true,
      });
      setConsentGiven();
      navigate('/chat');
    } else {
      navigate('/consent');
    }
  };

  const consent = async () => {
    await authApi.consent({
      consent_data_processing: true,
      consent_terms: true,
      consent_ai_usage: true,
    });
    setConsentGiven();
    navigate('/chat');
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } catch {
      // игнорируем ошибку выхода
    } finally {
      storeLogout();
      navigate('/login');
      addToast({ message: 'Вы вышли из системы', type: 'info' });
    }
  };

  return { login, register, consent, logout };
}

