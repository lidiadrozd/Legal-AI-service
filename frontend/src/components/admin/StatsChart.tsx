import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import styled from 'styled-components';
import { formatShortDate } from '@/utils/formatDate';
import type { DailyStatPoint } from '@/types/admin.types';

const Wrap = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px 16px 12px;
`;

const ChartTitle = styled.div`
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 20px;
  padding: 0 4px;
`;

const CustomTooltipWrap = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  font-size: 13px;
`;

const TooltipLabel = styled.div`
  color: var(--color-text-secondary);
  margin-bottom: 6px;
  font-size: 12px;
`;

const TooltipRow = styled.div<{ $color: string }>`
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text);
  &::before {
    content: '';
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: ${({ $color }) => $color};
  }
`;

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <CustomTooltipWrap>
      <TooltipLabel>{label}</TooltipLabel>
      {payload.map((p) => (
        <TooltipRow key={p.name} $color={p.color}>
          {p.name}: <strong>{p.value.toLocaleString('ru-RU')}</strong>
        </TooltipRow>
      ))}
    </CustomTooltipWrap>
  );
}

interface Props {
  data: DailyStatPoint[];
  title?: string;
}

export function StatsChart({ data, title = 'Активность за последние 30 дней' }: Props) {
  const formatted = data.map((d) => ({
    ...d,
    label: formatShortDate(d.date),
  }));

  return (
    <Wrap>
      <ChartTitle>{title}</ChartTitle>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={formatted} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
          <XAxis
            dataKey="label"
            tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }}
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: '12px', color: 'rgba(255,255,255,0.56)', paddingTop: '12px' }}
          />
          <Line
            type="monotone"
            dataKey="users"
            name="Активные пользователи"
            stroke="#21A038"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
          <Line
            type="monotone"
            dataKey="messages"
            name="Сообщения"
            stroke="#4A90E2"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </Wrap>
  );
}
