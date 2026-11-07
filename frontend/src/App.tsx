import { AppRouter } from './router';
import { CookieBanner } from '@/components/common/CookieBanner';
import { TermsUpdateBanner } from '@/components/common/TermsUpdateBanner';
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
  return (
    <>
      <AppRouter />
      <CookieBanner />
    </>
  );

  return (
    <>
      <AppRouter />
      <CookieBanner />
      <TermsUpdateBanner />
    </>
  );
}

export default App;