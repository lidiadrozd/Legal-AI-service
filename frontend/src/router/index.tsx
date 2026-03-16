import { Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { AdminRoute } from '@/components/common/AdminRoute';
import { AppLayout } from '@/components/layout/AppLayout';
import { AuthLayout } from '@/components/layout/AuthLayout';
import styled from 'styled-components';

const LandingPage = lazy(() => import('@/pages/Landing/LandingPage'));
const LoginPage = lazy(() => import('@/pages/Auth/LoginPage'));
const RegisterPage = lazy(() => import('@/pages/Auth/RegisterPage'));
const ConsentPage = lazy(() => import('@/pages/Consent/ConsentPage'));
const ChatPage = lazy(() => import('@/pages/Chat/ChatPage'));
const DocumentsPage = lazy(() => import('@/pages/Documents/DocumentsPage'));
const DocumentDetailPage = lazy(() => import('@/pages/Documents/DocumentDetailPage'));
const DashboardPage = lazy(() => import('@/pages/Admin/DashboardPage'));
const UsersPage = lazy(() => import('@/pages/Admin/UsersPage'));
const ChatsPage = lazy(() => import('@/pages/Admin/ChatsPage'));
const FeedbackPage = lazy(() => import('@/pages/Admin/FeedbackPage'));
const StatsPage = lazy(() => import('@/pages/Admin/StatsPage'));

const PageLoader = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--color-bg);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
`;

function Loading() {
  return <PageLoader>Загрузка...</PageLoader>;
}

export function AppRouter() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        {/* Публичный лендинг */}
        <Route path="/" element={<LandingPage />} />

        {/* Авторизация */}
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        {/* Согласие (требует авторизации, до chat) */}
        <Route
          path="/consent"
          element={
            <ProtectedRoute>
              <ConsentPage />
            </ProtectedRoute>
          }
        />

        {/* Защищённые страницы */}
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:chatId" element={<ChatPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:docId" element={<DocumentDetailPage />} />
        </Route>

        {/* Панель администратора */}
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <AppLayout isAdmin />
            </AdminRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="chats" element={<ChatsPage />} />
          <Route path="feedback" element={<FeedbackPage />} />
          <Route path="stats" element={<StatsPage />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
