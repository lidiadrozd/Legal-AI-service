import { useQuery } from '@tanstack/react-query';
import styled from 'styled-components';
import { adminApi } from '@/api/admin';
import { StatsChart } from '@/components/admin/StatsChart';

const Page = styled.div`
  padding: 32px;
  max-width: 1200px;
  height: 100%;
  overflow-y: auto;
`;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 28px;
`;

const KpiRow = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
`;

const KpiCard = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
`;

const KpiLabel = styled.div`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: 8px;
`;

const KpiValue = styled.div`
  font-size: 26px;
  font-weight: 700;
  color: var(--color-text);
`;

const ChartCard = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
`;

const ChartTitle = styled.h2`
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 20px;
`;

const Skel = styled.div`
  background: var(--color-surface);
  border-radius: var(--radius-md);
  animation: skeleton-pulse 1.4s ease-in-out infinite;
  @keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
`;

export default function StatsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: adminApi.getStats,
  });

  const kpis = [
    { label: 'Всего пользователей', value: data?.summary.total_users ?? 0 },
    { label: 'Всего чатов', value: data?.summary.total_chats ?? 0 },
    { label: 'Активных сегодня', value: data?.summary.active_users_today ?? 0 },
    { label: 'Сообщений сегодня', value: data?.summary.messages_today ?? 0 },
  ];

  return (
    <Page>
      <Title>Статистика</Title>
      <KpiRow>
        {kpis.map(({ label, value }) => (
          <KpiCard key={label}>
            <KpiLabel>{label}</KpiLabel>
            {isLoading ? (
              <Skel style={{ height: 32, width: '50%' }} />
            ) : (
              <KpiValue>{value.toLocaleString('ru-RU')}</KpiValue>
            )}
          </KpiCard>
        ))}
      </KpiRow>

      <ChartCard>
        <ChartTitle>Динамика за последние 30 дней</ChartTitle>
        {isLoading ? (
          <Skel style={{ height: 300 }} />
        ) : (
          <StatsChart data={data?.daily ?? []} />
        )}
      </ChartCard>
    </Page>
  );
}
