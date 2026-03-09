import { useQuery } from '@tanstack/react-query';
import styled from 'styled-components';
import { Users, MessageSquare, ThumbsUp, Activity } from 'lucide-react';
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
  margin-bottom: 24px;
`;

const KpiGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
`;

const KpiCard = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
`;

const KpiHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
`;

const KpiLabel = styled.div`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
`;

const KpiIcon = styled.div<{ $color: string }>`
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: ${({ $color }) => $color}22;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${({ $color }) => $color};
`;

const KpiValue = styled.div`
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1;
`;

const KpiSub = styled.div`
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 6px;
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

const Skeleton = styled.div<{ $h?: number; $w?: string }>`
  background: var(--color-surface);
  border-radius: var(--radius-md);
  height: ${({ $h }) => $h ?? 40}px;
  width: ${({ $w }) => $w ?? '100%'};
  animation: skeleton-pulse 1.4s ease-in-out infinite;
  @keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
`;

const kpis = [
  { key: 'total_users' as const, label: 'Пользователей', icon: Users, color: '#21A038' },
  { key: 'total_chats' as const, label: 'Чатов', icon: MessageSquare, color: '#4A90E2' },
  { key: 'messages_today' as const, label: 'Сообщений сегодня', icon: Activity, color: '#FF9500' },
  { key: 'avg_rating' as const, label: 'Средняя оценка', icon: ThumbsUp, color: '#30D158', format: (v: number) => `${(v * 100).toFixed(0)}%` },
];

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: adminApi.getStats,
  });

  return (
    <Page>
      <Title>Панель управления</Title>

      <KpiGrid>
        {kpis.map(({ key, label, icon: Icon, color, format }) => (
          <KpiCard key={key}>
            <KpiHeader>
              <KpiLabel>{label}</KpiLabel>
              <KpiIcon $color={color}><Icon size={16} /></KpiIcon>
            </KpiHeader>
            {isLoading ? (
              <Skeleton $h={32} $w="60%" />
            ) : (
              <>
                <KpiValue>
                  {format
                    ? format(data?.summary[key] as number ?? 0)
                    : (data?.summary[key] ?? 0).toLocaleString('ru-RU')}
                </KpiValue>
                <KpiSub>за всё время</KpiSub>
              </>
            )}
          </KpiCard>
        ))}
      </KpiGrid>

      <ChartCard>
        <ChartTitle>Активность пользователей</ChartTitle>
        {isLoading ? (
          <Skeleton $h={280} />
        ) : (
          <StatsChart data={data?.daily ?? []} />
        )}
      </ChartCard>
    </Page>
  );
}
