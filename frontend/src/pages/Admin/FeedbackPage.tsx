import { useQuery } from '@tanstack/react-query';
import styled from 'styled-components';
import { adminApi } from '@/api/admin';
import { FeedbackTable } from '@/components/admin/FeedbackTable';

const Page = styled.div`
  padding: 32px;
  max-width: 1200px;
  height: 100%;
  overflow-y: auto;
`;

const Header = styled.div`
  margin-bottom: 24px;
`;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 4px;
`;

const Sub = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
`;

export default function FeedbackPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin-feedback'],
    queryFn: () => adminApi.getFeedback(),
  });

  return (
    <Page>
      <Header>
        <Title>Обратная связь</Title>
        <Sub>Оценки пользователей на ответы ИИ-ассистента</Sub>
      </Header>
      {isLoading ? (
        <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-sm)' }}>Загрузка...</div>
      ) : (
        <FeedbackTable items={data ?? []} />
      )}
    </Page>
  );
}
