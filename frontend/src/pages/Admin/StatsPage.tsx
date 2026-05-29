import { useQuery } from '@tanstack/react-query';
import styled from 'styled-components';
import { adminApi } from '@/api/admin';
import { StatsChart } from '@/components/admin/StatsChart';
import { formatRub } from '@/utils/formatMoney';

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
  margin-bottom: 24px;
`;

const ChartTitle = styled.h2`
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 20px;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
`;

const Th = styled.th`
  padding: 12px 16px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--color-border);
`;

const Td = styled.td`
  padding: 12px 16px;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
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
  const { data: cogs, isLoading: cogsLoading } = useQuery({
    queryKey: ['admin-cogs'],
    queryFn: adminApi.getCogs,
  });

  const kpis = [
    { label: 'Всего пользователей', value: data?.summary.total_users ?? 0 },
    { label: 'Всего чатов', value: data?.summary.total_chats ?? 0 },
    { label: 'Активных сегодня', value: data?.summary.active_users_today ?? 0 },
    { label: 'Сообщений сегодня', value: data?.summary.messages_today ?? 0 },
    { label: 'COGS LLM', value: formatRub(data?.summary.total_cogs_rub ?? 0) },
    { label: 'Токены LLM', value: (data?.summary.total_tokens ?? 0).toLocaleString('ru-RU') },
    { label: 'Попадания в кэш', value: data?.summary.cache_hits ?? 0 },
    { label: 'Тариф / 1k токенов', value: formatRub(cogs?.price_per_1k_tokens ?? 0) },
  ];

  return (
    <Page>
      <Title>Статистика</Title>
      <KpiRow>
        {kpis.map(({ label, value }) => (
          <KpiCard key={label}>
            <KpiLabel>{label}</KpiLabel>
            {isLoading && label !== 'Тариф / 1k токенов' ? (
              <Skel style={{ height: 32, width: '50%' }} />
            ) : cogsLoading && label === 'Тариф / 1k токенов' ? (
              <Skel style={{ height: 32, width: '50%' }} />
            ) : (
              <KpiValue>{typeof value === 'number' ? value.toLocaleString('ru-RU') : value}</KpiValue>
            )}
          </KpiCard>
        ))}
      </KpiRow>

      <ChartCard>
        <ChartTitle>Динамика за последние 30 дней</ChartTitle>
        {isLoading ? (
          <Skel style={{ height: 300 }} />
        ) : (
          <StatsChart data={data?.daily ?? []} showUsageMetrics />
        )}
      </ChartCard>

      <ChartCard>
        <ChartTitle>COGS по пользователям</ChartTitle>
        {cogsLoading ? (
          <Skel style={{ height: 220 }} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Пользователь</Th>
                <Th>Запросы</Th>
                <Th>Кэш</Th>
                <Th>Токены</Th>
                <Th>COGS</Th>
              </tr>
            </thead>
            <tbody>
              {(cogs?.users ?? []).length === 0 && (
                <tr>
                  <Td colSpan={5} style={{ color: 'var(--color-text-tertiary)' }}>
                    Пока нет данных по расходу LLM.
                  </Td>
                </tr>
              )}
              {(cogs?.users ?? []).map((row) => (
                <tr key={row.user_id}>
                  <Td>
                    <div>
                      <strong>{row.full_name}</strong>
                      <div style={{ color: 'var(--color-text-secondary)', fontSize: '12px' }}>{row.email}</div>
                    </div>
                  </Td>
                  <Td>{row.llm_requests.toLocaleString('ru-RU')}</Td>
                  <Td>{row.cache_hits.toLocaleString('ru-RU')}</Td>
                  <Td>{row.tokens_used.toLocaleString('ru-RU')}</Td>
                  <Td>{formatRub(row.cogs_rub)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </ChartCard>
    </Page>
  );
}
