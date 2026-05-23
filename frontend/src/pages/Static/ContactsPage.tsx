import styled from 'styled-components';
import { PageMeta } from '@/components/common/PageMeta';
import { COMPANY } from '@/constants/site';
import { Link } from 'react-router-dom';

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 16px;
`;

const Card = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
  margin-bottom: 16px;
`;

const Row = styled.p`
  margin: 0 0 10px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
`;

export default function ContactsPage() {
  return (
    <>
      <PageMeta title="Контакты" description="Контакты и реквизиты сервиса ИИ-Юрист" />
      <Title>Контакты</Title>
      <Card>
        <Row>
          <strong>Организация:</strong> {COMPANY.name}
        </Row>
        <Row>
          <strong>Адрес:</strong> {COMPANY.address}
        </Row>
        <Row>
          <strong>Email:</strong>{' '}
          <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>
        </Row>
        <Row>
          <strong>Телефон:</strong>{' '}
          <a href={`tel:${COMPANY.phone.replace(/\s/g, '')}`}>{COMPANY.phone}</a>
        </Row>
        <Row>
          <strong>Поддержка по тарифам:</strong> напишите на {COMPANY.email} с темой «Тарифы».
        </Row>
      </Card>
      <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
        По вопросам персональных данных см.{' '}
        <Link to="/privacy">политику конфиденциальности</Link>.
      </p>
    </>
  );
}
