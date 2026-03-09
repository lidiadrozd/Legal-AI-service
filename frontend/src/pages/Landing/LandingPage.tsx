import { Link } from 'react-router-dom';
import styled, { keyframes } from 'styled-components';
import { Scale, MessageSquare, FileText, Search, Shield, ArrowRight, CheckCircle } from 'lucide-react';

const fadeUp = keyframes`
  from { opacity: 0; transform: translateY(20px); }
  to   { opacity: 1; transform: translateY(0); }
`;

const Page = styled.div`
  min-height: 100vh;
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
`;

// --- Навигация ---

const Nav = styled.nav`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 48px;
  height: 72px;
  border-bottom: 1px solid var(--color-border);
  background: rgba(12, 12, 14, 0.8);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 10;

  @media (max-width: 768px) { padding: 0 20px; }
`;

const NavLogo = styled.span`
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
  span { color: var(--color-primary); }
`;

const NavLinks = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;

  @media (max-width: 640px) { display: none; }
`;

const NavLink = styled(Link)`
  padding: 8px 16px;
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  transition: color var(--transition-fast);
  &:hover { color: var(--color-text); text-decoration: none; }
`;

const NavCta = styled(Link)`
  padding: 9px 20px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: 600;
  transition: background var(--transition-fast);
  &:hover { background: var(--color-primary-hover); text-decoration: none; }
`;

// --- Hero ---

const Hero = styled.section`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 80px 24px;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: -200px;
    left: 50%;
    transform: translateX(-50%);
    width: 800px;
    height: 800px;
    background: radial-gradient(circle, rgba(33, 160, 56, 0.08) 0%, transparent 70%);
    pointer-events: none;
  }
`;

const Badge = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--color-primary-muted);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-full);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 24px;
  animation: ${fadeUp} 0.5s ease both;
`;

const HeroTitle = styled.h1`
  font-size: clamp(32px, 6vw, 64px);
  font-weight: 800;
  color: var(--color-text);
  line-height: 1.15;
  max-width: 800px;
  letter-spacing: -1px;
  animation: ${fadeUp} 0.5s 0.1s ease both;

  span { color: var(--color-primary); }
`;

const HeroSub = styled.p`
  font-size: clamp(16px, 2vw, 20px);
  color: var(--color-text-secondary);
  max-width: 560px;
  line-height: 1.7;
  margin: 24px 0 40px;
  animation: ${fadeUp} 0.5s 0.2s ease both;
`;

const HeroCtas = styled.div`
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  animation: ${fadeUp} 0.5s 0.3s ease both;
`;

const PrimaryBtn = styled(Link)`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 32px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-full);
  font-size: var(--font-size-md);
  font-weight: 700;
  transition: background var(--transition-fast), transform var(--transition-fast);
  &:hover { background: var(--color-primary-hover); transform: translateY(-2px); text-decoration: none; }
`;

const SecondaryBtn = styled(Link)`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 28px;
  background: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  font-size: var(--font-size-md);
  transition: all var(--transition-fast);
  &:hover { border-color: var(--color-border-hover); color: var(--color-text); text-decoration: none; }
`;

// --- Фичи ---

const Features = styled.section`
  padding: 80px 48px;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;

  @media (max-width: 768px) { padding: 60px 20px; }
`;

const SectionTag = styled.div`
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 12px;
`;

const SectionTitle = styled.h2`
  font-size: clamp(24px, 4vw, 40px);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 48px;
  max-width: 480px;
`;

const FeatGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;

  @media (max-width: 900px) { grid-template-columns: 1fr 1fr; }
  @media (max-width: 600px) { grid-template-columns: 1fr; }
`;

const FeatCard = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 28px 24px;
  transition: border-color var(--transition-fast), transform var(--transition-normal);
  &:hover { border-color: var(--color-primary); transform: translateY(-4px); }
`;

const FeatIcon = styled.div`
  width: 48px;
  height: 48px;
  background: var(--color-primary-muted);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
  margin-bottom: 16px;
`;

const FeatTitle = styled.h3`
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 8px;
`;

const FeatDesc = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.65;
`;

// --- Как работает ---

const Steps = styled.section`
  padding: 80px 48px;
  background: var(--color-surface);
  @media (max-width: 768px) { padding: 60px 20px; }
`;

const StepsInner = styled.div`
  max-width: 1200px;
  margin: 0 auto;
`;

const StepList = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  margin-top: 48px;

  @media (max-width: 900px) { grid-template-columns: 1fr 1fr; }
  @media (max-width: 500px) { grid-template-columns: 1fr; }
`;

const StepItem = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
`;

const StepNum = styled.div`
  width: 36px;
  height: 36px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: var(--font-size-md);
`;

const StepTitle = styled.div`
  font-weight: 600;
  color: var(--color-text);
  font-size: var(--font-size-md);
`;

const StepDesc = styled.div`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
`;

// --- CTA Banner ---

const CTABanner = styled.section`
  padding: 80px 48px;
  text-align: center;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;

  @media (max-width: 768px) { padding: 60px 20px; }
`;

const CTABox = styled.div`
  background: linear-gradient(135deg, rgba(33, 160, 56, 0.14) 0%, rgba(12, 12, 14, 0) 100%);
  border: 1px solid rgba(33, 160, 56, 0.3);
  border-radius: var(--radius-xl);
  padding: 60px 40px;
`;

const CTATitle = styled.h2`
  font-size: clamp(24px, 4vw, 36px);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 16px;
`;

const CTASub = styled.p`
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  margin-bottom: 32px;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.6;
`;

const CheckList = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16px 32px;
  margin-bottom: 36px;
`;

const CheckItem = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
`;

// --- Footer ---

const Footer = styled.footer`
  border-top: 1px solid var(--color-border);
  padding: 24px 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--color-text-tertiary);
  font-size: 12px;

  @media (max-width: 640px) {
    flex-direction: column;
    gap: 8px;
    padding: 20px;
    text-align: center;
  }
`;

export default function LandingPage() {
  return (
    <Page>
      <Nav>
        <NavLogo>ИИ<span>-Юрист</span></NavLogo>
        <NavLinks>
          <NavLink to="#features">Возможности</NavLink>
          <NavLink to="#how">Как работает</NavLink>
        </NavLinks>
        <div style={{ display: 'flex', gap: 8 }}>
          <NavLink to="/login">Войти</NavLink>
          <NavCta to="/register">Начать бесплатно</NavCta>
        </div>
      </Nav>

      <Hero>
        <Badge><Scale size={13} />Юридический ИИ-ассистент</Badge>
        <HeroTitle>
          Юридическая помощь<br />на основе <span>искусственного интеллекта</span>
        </HeroTitle>
        <HeroSub>
          Получите профессиональную юридическую консультацию, сгенерируйте документы и найдите
          актуальную судебную практику за секунды.
        </HeroSub>
        <HeroCtas>
          <PrimaryBtn to="/register">
            Начать бесплатно <ArrowRight size={18} />
          </PrimaryBtn>
          <SecondaryBtn to="/login">Уже есть аккаунт?</SecondaryBtn>
        </HeroCtas>
      </Hero>

      <Features id="features">
        <SectionTag>Возможности</SectionTag>
        <SectionTitle>Всё необходимое для юридической помощи</SectionTitle>
        <FeatGrid>
          {[
            { icon: <MessageSquare size={22} />, title: 'Чат с ИИ', desc: 'Задавайте вопросы по трудовому, гражданскому, жилищному и другим отраслям права и получайте ответы в режиме реального времени.' },
            { icon: <FileText size={22} />, title: 'Генерация документов', desc: 'Составьте договор аренды, претензию, исковое заявление или любой другой юридический документ за несколько секунд.' },
            { icon: <Search size={22} />, title: 'База законодательства', desc: 'Доступ к ГК, ТК, НК, ЖК и другим кодексам РФ с автоматическим поиском релевантных норм.' },
            { icon: <Scale size={22} />, title: 'Судебная практика', desc: 'Поиск актуальных решений судов по вашей ситуации с анализом сложившейся практики.' },
            { icon: <Shield size={22} />, title: 'Конфиденциальность', desc: 'Ваши данные защищены. Все консультации проходят в зашифрованном канале и не передаются третьим лицам.' },
            { icon: <CheckCircle size={22} />, title: 'История консультаций', desc: 'Все ваши чаты и документы сохраняются в личном кабинете и доступны в любое время.' },
          ].map((f) => (
            <FeatCard key={f.title}>
              <FeatIcon>{f.icon}</FeatIcon>
              <FeatTitle>{f.title}</FeatTitle>
              <FeatDesc>{f.desc}</FeatDesc>
            </FeatCard>
          ))}
        </FeatGrid>
      </Features>

      <Steps id="how">
        <StepsInner>
          <SectionTag>Как это работает</SectionTag>
          <SectionTitle>Начните работу за 4 шага</SectionTitle>
          <StepList>
            {[
              { n: '1', title: 'Зарегистрируйтесь', desc: 'Создайте аккаунт и подтвердите согласие на обработку данных.' },
              { n: '2', title: 'Задайте вопрос', desc: 'Опишите вашу ситуацию в чате так, как вы бы рассказали юристу.' },
              { n: '3', title: 'Получите ответ', desc: 'ИИ-ассистент проанализирует нормы закона и сформирует рекомендацию.' },
              { n: '4', title: 'Скачайте документ', desc: 'При необходимости сгенерируйте и скачайте готовый юридический документ.' },
            ].map((s) => (
              <StepItem key={s.n}>
                <StepNum>{s.n}</StepNum>
                <StepTitle>{s.title}</StepTitle>
                <StepDesc>{s.desc}</StepDesc>
              </StepItem>
            ))}
          </StepList>
        </StepsInner>
      </Steps>

      <CTABanner>
        <CTABox>
          <CTATitle>Начните прямо сейчас</CTATitle>
          <CTASub>Зарегистрируйтесь бесплатно и получите доступ ко всем возможностям платформы.</CTASub>
          <CheckList>
            {['Бесплатная регистрация', 'Ответ за секунды', 'Конфиденциально', 'Актуальная база законов'].map((c) => (
              <CheckItem key={c}><CheckCircle size={15} style={{ color: 'var(--color-primary)' }} />{c}</CheckItem>
            ))}
          </CheckList>
          <PrimaryBtn to="/register" style={{ display: 'inline-flex', justifyContent: 'center' }}>
            Создать аккаунт <ArrowRight size={18} />
          </PrimaryBtn>
        </CTABox>
      </CTABanner>

      <Footer>
        <span>© 2026 ИИ-Юрист. Все права защищены.</span>
        <span>Информация носит справочный характер и не заменяет профессиональную юридическую консультацию.</span>
      </Footer>
    </Page>
  );
}
