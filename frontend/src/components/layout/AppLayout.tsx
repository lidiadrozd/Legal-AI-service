import { Outlet } from 'react-router-dom';
import styled, { createGlobalStyle } from 'styled-components';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useUIStore } from '@/store/uiStore';
import { ToastContainer } from '@/components/common/ToastContainer';
import { useNotificationWS } from '@/hooks/useNotificationWS';
import { useNotificationsHydrate } from '@/hooks/useNotificationsHydrate';

interface AppLayoutProps {
  isAdmin?: boolean;
}

/*
 * На мобильных браузерах 100vh считается по "высокому" экрану (адресная строка скрыта),
 * поэтому страница была выше видимой области: прокручивался весь документ, шапка уезжала
 * вверх, а блок ввода уходил под панель браузера. Пока открыт AppLayout, документ не
 * должен прокручиваться вообще: прокручивается только область контента внутри Shell.
 */
const AppViewportLock = createGlobalStyle`
  html, body {
    height: 100%;
    overflow: hidden;
    overscroll-behavior: none;
  }

  #root {
    min-height: 0;
    height: 100%;
  }
`;

const Shell = styled.div`
  position: fixed;
  inset: 0;
  display: flex;
  overflow: hidden;
  background: var(--color-bg);
`;

const SidebarWrap = styled.aside<{ $open: boolean }>`
  width: var(--sidebar-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  height: 100%;
  transition: transform var(--transition-normal), width var(--transition-normal);

  @media (max-width: 768px) {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    height: auto;
    z-index: 100;
    transform: ${({ $open }) => ($open ? 'translateX(0)' : 'translateX(-100%)')};
  }
`;

const Main = styled.main`
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
`;

const Content = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
`;

const Overlay = styled.div<{ $visible: boolean }>`
  display: none;
  @media (max-width: 768px) {
    display: ${({ $visible }) => ($visible ? 'block' : 'none')};
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 99;
  }
`;

export function AppLayout({ isAdmin = false }: AppLayoutProps) {
  const { sidebarOpen, setSidebarOpen } = useUIStore();
  useNotificationsHydrate();
  useNotificationWS();

  return (
    <Shell>
      <AppViewportLock />
      <Overlay $visible={sidebarOpen} onClick={() => setSidebarOpen(false)} />
      <SidebarWrap $open={sidebarOpen}>
        <Sidebar isAdmin={isAdmin} />
      </SidebarWrap>
      <Main>
        <Header />
        <Content>
          <Outlet />
        </Content>
      </Main>
      <ToastContainer />
    </Shell>
  );
}

