import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { PageMeta } from '@/components/common/PageMeta';

const Wrap = styled.div`
  text-align: center;
  padding: 48px 0;
`;

const Code = styled.div`
  font-size: 72px;
  font-weight: 800;
  color: var(--color-primary);
  line-height: 1;
  margin-bottom: 12px;
`;

const Title = styled.h1`
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0 0 12px;
`;

const Sub = styled.p`
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  margin: 0 0 24px;
`;

const HomeLink = styled(Link)`
  display: inline-block;
  padding: 12px 24px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-md);
  font-weight: 600;
  &:hover { background: var(--color-primary-hover); text-decoration: none; }
`;

export default function NotFoundPage() {
  return (
    <Wrap>
      <PageMeta title="Страница не найдена" />
      <Code aria-hidden>404</Code>
      <Title>Страница не найдена</Title>
      <Sub>Запрашиваемый адрес не существует или был перемещён.</Sub>
      <HomeLink to="/">На главную</HomeLink>
    </Wrap>
  );
}
