import styled from 'styled-components';
import { Link } from 'react-router-dom';
import { PageMeta } from '@/components/common/PageMeta';
import { COMPANY } from '@/constants/site';

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 12px;
`;

const Sub = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0 0 32px;
  line-height: 1.6;
`;

const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
`;

const Plan = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
`;

const PlanName = styled.h2`
  font-size: var(--font-size-lg);
  margin: 0 0 8px;
  color: var(--color-text);
`;

const Price = styled.div`
  font-size: 28px;
  font-weight: 700;
  color: var(--color-primary);
  margin-bottom: 12px;
`;

const List = styled.ul`
  margin: 0 0 16px;
  padding-left: 18px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
`;

const Cta = styled(Link)`
  display: inline-block;
  padding: 10px 18px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  &:hover { background: var(--color-primary-hover); text-decoration: none; }
`;

const Note = styled.p`
  margin-top: 24px;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 1.6;
`;

export default function PricingPage() {
  return (
    <>
      <PageMeta title="Тарифы" description="Тарифные планы сервиса ИИ-Юрист" />
      <Title>Тарифы</Title>
      <Sub>
        Выберите подходящий план. Для подключения корпоративного тарифа или пополнения баланса
        обратитесь в поддержку.
      </Sub>
      <Grid>
        <Plan>
          <PlanName>Старт</PlanName>
          <Price>Бесплатно</Price>
          <List>
            <li>Регистрация и доступ к интерфейсу</li>
            <li>Ограниченное число запросов в чат</li>
          </List>
          <Cta to="/register">Зарегистрироваться</Cta>
        </Plan>
        <Plan>
          <PlanName>Базовый</PlanName>
          <Price>по запросу</Price>
          <List>
            <li>Расширенный лимит сообщений</li>
            <li>Генерация документов по шаблонам</li>
          </List>
          <Cta to="/contacts">Связаться</Cta>
        </Plan>
        <Plan>
          <PlanName>Корпоративный</PlanName>
          <Price>индивидуально</Price>
          <List>
            <li>Для организаций и команд</li>
            <li>Отдельные условия и SLA</li>
          </List>
          <Cta to={`mailto:${COMPANY.email}?subject=Корпоративный%20тариф`}>Написать</Cta>
        </Plan>
      </Grid>
      <Note>
        Пополнение баланса и подключение платных функций: {COMPANY.email}. Укажите email аккаунта
        в сервисе.
      </Note>
    </>
  );
}
