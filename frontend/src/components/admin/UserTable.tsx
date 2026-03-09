import { useState } from 'react';
import styled from 'styled-components';
import { ChevronUp, ChevronDown, Search } from 'lucide-react';
import { formatDateTime } from '@/utils/formatDate';
import type { AdminUser } from '@/types/admin.types';

const Wrap = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
`;

const SearchBar = styled.div`
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  gap: 8px;
`;

const SearchInput = styled.input`
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--color-text);
  font-size: var(--font-size-sm);
  &::placeholder { color: var(--color-text-tertiary); }
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
  cursor: pointer;
  white-space: nowrap;
  &:hover { color: var(--color-text); }
`;

const ThInner = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const Td = styled.td`
  padding: 12px 16px;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
  &:last-child { border-bottom: 0; }
`;

const Tr = styled.tr`
  cursor: pointer;
  transition: background var(--transition-fast);
  &:hover { background: var(--color-surface-hover); }
  &:last-child td { border-bottom: 0; }
`;

const StatusDot = styled.span<{ $active: boolean }>`
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 6px;
  background: ${({ $active }) => ($active ? 'var(--color-success)' : 'var(--color-error)')};
`;

const RoleBadge = styled.span`
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--color-primary-muted);
  color: var(--color-primary);
  font-weight: 500;
`;

type SortField = 'email' | 'created_at' | 'chat_count';

interface Props {
  users: AdminUser[];
  onUserClick: (user: AdminUser) => void;
}

export function UserTable({ users, onUserClick }: Props) {
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortAsc, setSortAsc] = useState(false);

  const handleSort = (field: SortField) => {
    if (field === sortField) setSortAsc((v) => !v);
    else { setSortField(field); setSortAsc(true); }
  };

  const filtered = users
    .filter((u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      u.full_name.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const mul = sortAsc ? 1 : -1;
      if (sortField === 'email') return mul * a.email.localeCompare(b.email);
      if (sortField === 'chat_count') return mul * ((a.chat_count ?? 0) - (b.chat_count ?? 0));
      return mul * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    });

  function SortIcon({ field }: { field: SortField }) {
    if (field !== sortField) return null;
    return sortAsc ? <ChevronUp size={13} /> : <ChevronDown size={13} />;
  }

  return (
    <Wrap>
      <SearchBar>
        <Search size={16} style={{ color: 'var(--color-text-tertiary)' }} />
        <SearchInput
          placeholder="Поиск по email или имени..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </SearchBar>
      <Table>
        <thead>
          <tr>
            <Th onClick={() => handleSort('email')}>
              <ThInner>Email <SortIcon field="email" /></ThInner>
            </Th>
            <Th>Имя</Th>
            <Th onClick={() => handleSort('created_at')}>
              <ThInner>Регистрация <SortIcon field="created_at" /></ThInner>
            </Th>
            <Th onClick={() => handleSort('chat_count')}>
              <ThInner>Чатов <SortIcon field="chat_count" /></ThInner>
            </Th>
            <Th>Роль</Th>
            <Th>Статус</Th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && (
            <tr>
              <Td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-tertiary)' }}>
                Пользователей не найдено
              </Td>
            </tr>
          )}
          {filtered.map((user) => (
            <Tr key={user.id} onClick={() => onUserClick(user)}>
              <Td>{user.email}</Td>
              <Td>{user.full_name}</Td>
              <Td style={{ color: 'var(--color-text-secondary)' }}>{formatDateTime(user.created_at)}</Td>
              <Td>{user.chat_count ?? 0}</Td>
              <Td><RoleBadge>{user.role === 'super_admin' ? 'Администратор' : 'Пользователь'}</RoleBadge></Td>
              <Td>
                <StatusDot $active={user.is_active} />
                {user.is_active ? 'Активен' : 'Заблокирован'}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Wrap>
  );
}
