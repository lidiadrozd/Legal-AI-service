import styled from 'styled-components';
import { PageMeta } from '@/components/common/PageMeta';
import { COMPANY, SITE_DESCRIPTION } from '@/constants/site';

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 16px;
`;

const Text = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.75;
  margin: 0 0 16px;
`;

export default function AboutPage() {
  return (
    <>
      <PageMeta title="О сервисе" description="О платформе ИИ-Юрист" />
      <Title>О сервисе</Title>
      <Text>{SITE_DESCRIPTION}</Text>
      <Text>
        Платформа разработана для сотрудников и пользователей, которым нужна быстрая справочная
        информация по законодательству Российской Федерации, подготовка черновиков документов и
        поиск релевантных норм.
      </Text>
      <Text>
        <strong>Оператор:</strong> {COMPANY.name}, {COMPANY.address}.
      </Text>
      <Text>
        Ответы формируются автоматически с помощью языковой модели. Перед принятием юридически
        значимых решений рекомендуем обратиться к квалифицированному специалисту.
      </Text>
    </>
  );
}
