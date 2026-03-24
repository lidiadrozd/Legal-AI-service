import { Outlet } from 'react-router-dom';
import styled from 'styled-components';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useUIStore } from '@/store/uiStore';
import { ToastContainer } from '@/components/common/ToastContainer';
import { useNotificationWS } from '@/hooks/useNotificationWS';

interface AppLayoutProps {
  isAdmin?: boolean;
}

const Shell = styled.div`
  display: flex;
  min-height: 100vh;
  background: var(--color-bg);
`;

const SidebarWrap = styled.aside<{ $open: boolean }>`
  width: var(--sidebar-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  height: 100vh;
  position: sticky;
  top: 0;
  transition: transform var(--transition-normal), width var(--transition-normal);

  @media (max-width: 768px) {
    position: fixed;
    z-index: 100;
    transform: ${({ $open }) => ($open ? 'translateX(0)' : 'translateX(-100%)')};
  }
`;

const Main = styled.main`
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100vh;
  overflow: hidden;
`;

const Content = styled.div`
  flex: 1;
  overflow-y: auto;
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
  useNotificationWS();

  return (
    <Shell>
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
