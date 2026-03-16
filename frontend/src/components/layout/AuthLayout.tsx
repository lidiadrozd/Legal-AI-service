import { Outlet } from 'react-router-dom';
import styled from 'styled-components';

const Wrap = styled.div`
  min-height: 100vh;
  background: var(--color-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
`;

const Card = styled.div`
  width: 100%;
  max-width: 440px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 40px 36px;
  box-shadow: var(--shadow-elevated);

  @media (max-width: 480px) {
    padding: 28px 20px;
    border-radius: var(--radius-lg);
  }
`;

const Logo = styled.div`
  text-align: center;
  margin-bottom: 32px;
`;

const LogoText = styled.span`
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.3px;

  span {
    color: var(--color-primary);
  }
`;

export function AuthLayout() {
  return (
    <Wrap>
      <Card>
        <Logo>
          <LogoText>
            ИИ<span>-Юрист</span>
          </LogoText>
        </Logo>
        <Outlet />
      </Card>
    </Wrap>
  );
}
