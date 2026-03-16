import { useState } from 'react';
import styled from 'styled-components';
import { ThumbsUp, ThumbsDown, Filter } from 'lucide-react';
import { formatDateTime } from '@/utils/formatDate';
import type { AdminFeedbackItem } from '@/types/admin.types';

const Wrap = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
`;

const Toolbar = styled.div`
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  gap: 8px;
`;

const FilterBtn = styled.button<{ $active?: boolean }>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius-full);
  border: 1px solid ${({ $active }) => ($active ? 'var(--color-primary)' : 'var(--color-border)')};
  background: ${({ $active }) => ($active ? 'var(--color-primary-muted)' : 'transparent')};
  color: ${({ $active }) => ($active ? 'var(--color-primary)' : 'var(--color-text-secondary)')};
  font-size: 12px;
  transition: all var(--transition-fast);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
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

const Tr = styled.tr`
  &:last-child td { border-bottom: 0; }
  &:hover td { background: var(--color-surface-hover); }
`;

const Preview = styled.div`
  color: var(--color-text-secondary);
  font-style: italic;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const RatingIcon = styled.span<{ $isUp: boolean }>`
  display: flex;
  align-items: center;
  gap: 4px;
  color: ${({ $isUp }) => ($isUp ? 'var(--color-success)' : 'var(--color-error)')};
  font-weight: 600;
`;

type FilterType = 'all' | 'up' | 'down';

interface Props {
  items: AdminFeedbackItem[];
}

export function FeedbackTable({ items }: Props) {
  const [filter, setFilter] = useState<FilterType>('all');

  const filtered = filter === 'all' ? items : items.filter((i) => i.rating === filter);

  const upCount = items.filter((i) => i.rating === 'up').length;
  const downCount = items.filter((i) => i.rating === 'down').length;

  return (
    <Wrap>
      <Toolbar>
        <Filter size={14} style={{ color: 'var(--color-text-tertiary)' }} />
        <FilterBtn $active={filter === 'all'} onClick={() => setFilter('all')}>
          Все ({items.length})
        </FilterBtn>
        <FilterBtn $active={filter === 'up'} onClick={() => setFilter('up')}>
          <ThumbsUp size={12} /> Полезно ({upCount})
        </FilterBtn>
        <FilterBtn $active={filter === 'down'} onClick={() => setFilter('down')}>
          <ThumbsDown size={12} /> Не помогло ({downCount})
        </FilterBtn>
      </Toolbar>
      <Table>
        <thead>
          <tr>
            <Th>Пользователь</Th>
            <Th>Ответ ИИ</Th>
            <Th>Оценка</Th>
            <Th>Дата</Th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && (
            <Tr>
              <Td colSpan={4} style={{ textAlign: 'center', color: 'var(--color-text-tertiary)' }}>
                Нет данных
              </Td>
            </Tr>
          )}
          {filtered.map((item) => (
            <Tr key={item.id}>
              <Td style={{ color: 'var(--color-text-secondary)' }}>{item.user_email}</Td>
              <Td><Preview>«{item.message_preview}»</Preview></Td>
              <Td>
                <RatingIcon $isUp={item.rating === 'up'}>
                  {item.rating === 'up' ? <ThumbsUp size={14} /> : <ThumbsDown size={14} />}
                  {item.rating === 'up' ? 'Полезно' : 'Не помогло'}
                </RatingIcon>
              </Td>
              <Td style={{ color: 'var(--color-text-secondary)' }}>{formatDateTime(item.created_at)}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Wrap>
  );
}
