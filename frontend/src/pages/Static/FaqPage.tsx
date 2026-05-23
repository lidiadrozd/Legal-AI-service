import styled from 'styled-components';
import { PageMeta } from '@/components/common/PageMeta';
import { FAQ_ITEMS } from '@/constants/site';

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 28px;
`;

const Item = styled.details`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  margin-bottom: 12px;

  summary {
    cursor: pointer;
    font-weight: 600;
    color: var(--color-text);
    list-style: none;
  }

  p {
    margin: 12px 0 0;
    font-size: var(--font-size-sm);
    color: var(--color-text-secondary);
    line-height: 1.65;
  }
`;

export default function FaqPage() {
  return (
    <>
      <PageMeta title="Вопросы и ответы" description="Частые вопросы о сервисе ИИ-Юрист" />
      <Title>Вопросы и ответы</Title>
      {FAQ_ITEMS.map((item) => (
        <Item key={item.q}>
          <summary>{item.q}</summary>
          <p>{item.a}</p>
        </Item>
      ))}
    </>
  );
}
