import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { adminApi } from '@/api/admin';
import { UserTable } from '@/components/admin/UserTable';
import type { AdminUser } from '@/types/admin.types';

const Page = styled.div`
  padding: 32px;
  max-width: 1200px;
  height: 100%;
  overflow-y: auto;
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
`;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
`;

const SearchInput = styled.input`
  padding: 9px 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  width: 260px;
  outline: none;
  &::placeholder { color: var(--color-text-tertiary); }
  &:focus { border-color: var(--color-primary); }
`;

const Total = styled.div`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: 12px;
`;

export default function UsersPage() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => adminApi.getUsers(),
  });

  const filtered = data?.filter((u) =>
    search
      ? u.email.toLowerCase().includes(search.toLowerCase()) ||
        u.full_name.toLowerCase().includes(search.toLowerCase())
      : true,
  ) ?? [];

  return (
    <Page>
      <Header>
        <Title>Пользователи</Title>
        <SearchInput
          placeholder="Поиск по email или имени..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </Header>

      {!isLoading && (
        <Total>{filtered.length} пользователей</Total>
      )}

      {isLoading ? (
        <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-sm)', padding: '24px 0' }}>Загрузка...</div>
      ) : (
        <UserTable
          users={filtered}
          onUserClick={(user: AdminUser) => navigate(`/admin/chats?userId=${user.id}`)}
        />
      )}
    </Page>
  );
}
