import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { authApi } from '@/api/auth';
import { getApiErrorMessage } from '@/utils/apiError';
import { Mail, ArrowLeft, AlertCircle } from 'lucide-react'; // Добавил иконки

const schema = z.object({
  email: z.string().email('Некорректный email'),
});

type FormData = z.infer<typeof schema>;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
  text-align: center;
`;

const Sub = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: 24px;
  text-align: center;
  line-height: 1.4;
`;

const Form = styled.form`
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const Field = styled.div`
  display: flex;
  flex-direction: column;
  gap: 6px;
`;

const Label = styled.label`
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
`;

const Input = styled.input<{ $error?: boolean }>`
  padding: 12px 14px;
  background: var(--color-surface);
  border: 1px solid ${({ $error }) => ($error ? 'var(--color-error)' : 'var(--color-border)')};
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--font-size-md); /* Увеличил для мобилок, чтобы не зумилось */
  outline: none;
  transition: border-color var(--transition-fast);
  &::placeholder { color: var(--color-text-tertiary); }
  &:focus { border-color: ${({ $error }) => ($error ? 'var(--color-error)' : 'var(--color-primary)')}; }
`;

const ErrorText = styled.span`
  font-size: 12px;
  color: var(--color-error);
`;

const Btn = styled.button`
  padding: 12px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  transition: background var(--transition-fast);
  &:hover:not(:disabled) { background: var(--color-primary-hover); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
`;

const ServerError = styled.div`
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--color-error);
  display: flex;
  gap: 8px;
  align-items: flex-start;
`;

const SuccessBox = styled.div`
  padding: 20px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-lg);
  text-align: center;
`;

const Footer = styled.div`
  text-align: center;
  margin-top: 24px;
  
  a {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--font-size-sm);
    color: var(--color-primary);
    text-decoration: none;
    &:hover { text-decoration: underline; }
  }
`;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    try {
      await authApi.forgotPassword(data.email);
      setSent(true);
    } catch (err) {
      setError('root', {
        message: 'Не удалось отправить письмо. Возможно, сервис почты временно недоступен или указан неверный email.',
      });
    }
  };

  if (sent) {
    return (
      <SuccessBox>
        <div style={{ marginBottom: 12 }}><Mail size={40} color="var(--color-success)" /></div>
        <Title>Проверьте почту</Title>
        <Sub>
          Мы отправили инструкции по сбросу пароля на ваш email. 
          Если письма нет, проверьте папку «Спам».
        </Sub>
        <Footer>
          <Link to="/login"><ArrowLeft size={16} /> Вернуться ко входу</Link>
        </Footer>
      </SuccessBox>
    );
  }

  return (
    <>
      <Title>Восстановление доступа</Title>
      <Sub>Введите email, указанный при регистрации, и мы пришлем ссылку для сброса пароля</Sub>
      
      <Form onSubmit={handleSubmit(onSubmit)}>
        {errors.root && (
          <ServerError>
            <AlertCircle size={18} style={{ flexShrink: 0 }} />
            {errors.root.message}
          </ServerError>
        )}
        
        <Field>
          <Label>Ваш Email</Label>
          <Input
            {...register('email')}
            type="email"
            placeholder="example@mail.ru"
            $error={!!errors.email}
            autoComplete="email"
          />
          {errors.email && <ErrorText>{errors.email.message}</ErrorText>}
        </Field>

        <Btn type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Отправка...' : 'Получить ссылку'}
        </Btn>
      </Form>

      <Footer>
        <Link to="/login"><ArrowLeft size={16} /> Вернуться ко входу</Link>
      </Footer>
    </>
  );
}