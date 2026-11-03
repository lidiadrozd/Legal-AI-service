import { useQuery } from '@tanstack/react-query';
import { AppRouter } from './router';
import { CookieBanner } from '@/components/common/CookieBanner';
import { TermsBanner } from '@/components/TermsBanner';
import { authApi } from '@/api/auth';
import { useAuthStore } from '@/store/authStore';
import { getAccessToken, getRefreshToken, getRememberMe } from '@/utils/tokenStorage';

async function restoreSession() {
  if (!getAccessToken() && !getRefreshToken()) return true;
  const user = await authApi.getMe();
  const access = getAccessToken();
  const refresh = getRefreshToken();
  if (access && refresh) {
    useAuthStore.getState().setAuth(user, access, refresh, getRememberMe());
  }
  return true;
}

function App() {
  const session = useQuery({
    queryKey: ['initial-session'],
    queryFn: restoreSession,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  if (session.isPending) return <div role="status">Проверяем вход...</div>;
  if (session.isError) return (
    <div role="alert">
      Не удалось проверить вход. Проверьте соединение и попробуйте ещё раз.
      <button onClick={() => void session.refetch()}>Повторить</button>
    </div>
  );

  return (
    <>
      <AppRouter />
      <CookieBanner />
      <TermsBanner />
    </>
  );
}

export default App;