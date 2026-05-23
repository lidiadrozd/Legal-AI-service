import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { COMPANY } from '@/constants/site';

const Footer = styled.footer`
  border-top: 1px solid var(--color-border);
  padding: 32px 48px 24px;
  color: var(--color-text-tertiary);
  font-size: 12px;

  @media (max-width: 768px) { padding: 24px 20px; }
`;

const Grid = styled.div`
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 24px;
  max-width: 1200px;
  margin: 0 auto 24px;

  @media (max-width: 768px) { grid-template-columns: 1fr; }
`;

const Col = styled.div``;

const ColTitle = styled.div`
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
  font-size: 13px;
`;

const FooterLink = styled(Link)`
  display: block;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
  &:hover { color: var(--color-primary); text-decoration: none; }
`;

const Bottom = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  justify-content: space-between;
  line-height: 1.5;
`;

export function SiteFooter() {
  return (
    <Footer>
      <Grid>
        <Col>
          <ColTitle>ИИ-Юрист</ColTitle>
          <p style={{ margin: '0 0 8px', lineHeight: 1.6 }}>
            {COMPANY.name}
            <br />
            {COMPANY.address}
          </p>
          <p style={{ margin: 0 }}>
            <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>
            <br />
            <a href={`tel:${COMPANY.phone.replace(/\s/g, '')}`}>{COMPANY.phone}</a>
          </p>
        </Col>
        <Col>
          <ColTitle>Сервис</ColTitle>
          <FooterLink to="/pricing">Тарифы</FooterLink>
          <FooterLink to="/faq">Вопросы и ответы</FooterLink>
          <FooterLink to="/about">О сервисе</FooterLink>
          <FooterLink to="/contacts">Контакты</FooterLink>
        </Col>
        <Col>
          <ColTitle>Документы</ColTitle>
          <FooterLink to="/privacy">Политика конфиденциальности</FooterLink>
          <FooterLink to="/terms">Пользовательское соглашение</FooterLink>
        </Col>
      </Grid>
      <Bottom>
        <span>© {new Date().getFullYear()} ИИ-Юрист. Все права защищены.</span>
        <span>
          Информация носит справочный характер и не заменяет консультацию квалифицированного юриста.
        </span>
      </Bottom>
    </Footer>
  );
}
