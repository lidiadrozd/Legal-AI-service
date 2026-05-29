import { Link, Outlet } from 'react-router-dom';
import styled from 'styled-components';
import { SiteFooter } from './SiteFooter';

const Page = styled.div`
  min-height: 100vh;
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
`;

const Nav = styled.nav`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 48px;
  height: 72px;
  border-bottom: 1px solid var(--color-border);
  background: rgba(12, 12, 14, 0.9);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 10;

  @media (max-width: 768px) { padding: 0 20px; }
`;

const NavLogo = styled(Link)`
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
  text-decoration: none;
  span { color: var(--color-primary); }
`;

const NavLinks = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const NavLink = styled(Link)`
  padding: 8px 14px;
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  &:hover { color: var(--color-text); text-decoration: none; }
`;

const Main = styled.main`
  flex: 1;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
  padding: 48px 24px 64px;
`;

export function PublicLayout() {
  return (
    <Page>
      <Nav aria-label="Основная навигация">
        <NavLogo to="/">
          ИИ<span>-Юрист</span>
        </NavLogo>
        <NavLinks>
          <NavLink to="/">Главная</NavLink>
          <NavLink to="/pricing">Тарифы</NavLink>
          <NavLink to="/contacts">Контакты</NavLink>
          <NavLink to="/login">Войти</NavLink>
        </NavLinks>
      </Nav>
      <Main>
        <Outlet />
      </Main>
      <SiteFooter />
    </Page>
  );
}
