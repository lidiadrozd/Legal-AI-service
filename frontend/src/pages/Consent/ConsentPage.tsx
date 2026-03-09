import { useState } from 'react';
import styled from 'styled-components';
import { Shield, CheckCircle, Circle, AlertTriangle } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';

const Page = styled.div`
  min-height: 100vh;
  background: var(--color-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
`;

const Card = styled.div`
  width: 100%;
  max-width: 560px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 40px;
  box-shadow: var(--shadow-elevated);
`;

const IconWrap = styled.div`
  width: 56px;
  height: 56px;
  background: var(--color-primary-muted);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
  margin-bottom: 20px;
`;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
`;

const Sub = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin-bottom: 28px;
`;

const ConsentList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 28px;
`;

const ConsentItem = styled.div<{ $checked: boolean }>`
  display: flex;
  gap: 12px;
  padding: 16px;
  background: ${({ $checked }) => ($checked ? 'var(--color-primary-muted)' : 'var(--color-surface)')};
  border: 1px solid ${({ $checked }) => ($checked ? 'var(--color-primary)' : 'var(--color-border)')};
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  &:hover { border-color: var(--color-primary); }
`;

const ConsentCheck = styled.div`
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-primary);
`;

const ConsentText = styled.div``;

const ConsentTitle = styled.div`
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 4px;
`;

const ConsentDesc = styled.div`
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
`;

const Warning = styled.div`
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  background: var(--color-warning-muted);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: 20px;
  line-height: 1.5;
`;

const Btn = styled.button<{ $disabled?: boolean }>`
  width: 100%;
  padding: 13px;
  background: ${({ $disabled }) => ($disabled ? 'var(--color-surface)' : 'var(--color-primary)')};
  color: ${({ $disabled }) => ($disabled ? 'var(--color-text-tertiary)' : '#fff')};
  border: 1px solid ${({ $disabled }) => ($disabled ? 'var(--color-border)' : 'var(--color-primary)')};
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: ${({ $disabled }) => ($disabled ? 'not-allowed' : 'pointer')};
  transition: all var(--transition-fast);
  &:hover:not([disabled]) { background: var(--color-primary-hover); }
`;

const CONSENTS = [
  {
    key: 'data' as const,
    title: 'Обработка персональных данных',
    desc: 'Я даю согласие на обработку моих персональных данных (имя, email) в соответствии с действующим законодательством РФ.',
  },
  {
    key: 'terms' as const,
    title: 'Пользовательское соглашение',
    desc: 'Я ознакомился(-ась) с условиями использования платформы и принимаю их.',
  },
  {
    key: 'ai' as const,
    title: 'Использование ИИ-технологий',
    desc: 'Я понимаю, что ответы формируются на основе ИИ и носят информационный характер, не заменяя профессиональную юридическую konsultację.',
  },
];

export default function ConsentPage() {
  const { consent } = useAuth();
  const [checked, setChecked] = useState({ data: false, terms: false, ai: false });
  const [loading, setLoading] = useState(false);

  const allChecked = Object.values(checked).every(Boolean);

  const toggle = (key: keyof typeof checked) =>
    setChecked((c) => ({ ...c, [key]: !c[key] }));

  const handleAccept = async () => {
    if (!allChecked) return;
    setLoading(true);
    try {
      await consent();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Page>
      <Card>
        <IconWrap>
          <Shield size={26} />
        </IconWrap>
        <Title>Согласие на обработку данных</Title>
        <Sub>
          Перед началом работы с платформой необходимо ознакомиться с условиями и дать согласие
          на использование ваших данных.
        </Sub>

        <ConsentList>
          {CONSENTS.map((c) => (
            <ConsentItem key={c.key} $checked={checked[c.key]} onClick={() => toggle(c.key)}>
              <ConsentCheck>
                {checked[c.key] ? <CheckCircle size={18} /> : <Circle size={18} style={{ color: 'var(--color-text-tertiary)' }} />}
              </ConsentCheck>
              <ConsentText>
                <ConsentTitle>{c.title}</ConsentTitle>
                <ConsentDesc>{c.desc}</ConsentDesc>
              </ConsentText>
            </ConsentItem>
          ))}
        </ConsentList>

        {!allChecked && (
          <Warning>
            <AlertTriangle size={16} style={{ flexShrink: 0, color: 'var(--color-warning)', marginTop: 2 }} />
            Для продолжения необходимо принять все три пункта соглашения.
          </Warning>
        )}

        <Btn
          $disabled={!allChecked}
          disabled={!allChecked || loading}
          onClick={handleAccept}
        >
          {loading ? 'Сохранение...' : 'Принять и продолжить'}
        </Btn>
      </Card>
    </Page>
  );
}
