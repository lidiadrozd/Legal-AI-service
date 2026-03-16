import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';

interface Props {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: Props) {
  const { isAuthenticated, isConsentGiven } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Редирект на согласие при попытке попасть в защищённый раздел
  // (кроме самой страницы /consent)
  if (!isConsentGiven && window.location.pathname !== '/consent') {
    return <Navigate to="/consent" replace />;
  }

  return <>{children}</>;
}
