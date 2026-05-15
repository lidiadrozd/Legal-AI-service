import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { authApi } from '@/api/auth';
import { getApiErrorMessage } from '@/utils/apiError';

const schema = z.object({
  email: z.string().email('Некорректный email'),
});

type FormData = z.infer<typeof schema>;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 6px;
`;

const Sub = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: 28px;
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
  padding: 11px 14px;
  background: var(--color-surface);
  border: 1px solid ${({ $error }) => ($error ? 'var(--color-error)' : 'var(--color-border)')};
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--font-size-sm);
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
  transition: background var(--transition-fast);
  &:hover:not(:disabled) { background: var(--color-primary-hover); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
`;

const ServerError = styled.div`
  padding: 10px 14px;
  background: var(--color-error-muted);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-error);
`;

const SuccessBox = styled.div`
  padding: 16px;
  background: var(--color-success-muted, #f0fdf4);
  border: 1px solid var(--color-success, #22c55e);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-success, #16a34a);
  line-height: 1.5;
`;

const Footer = styled.div`
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: 8px;
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
        message: getApiErrorMessage(err, 'Произошла ошибка. Попробуйте позже.'),
      });
    }
  };

  if (sent) {
    return (
      <>
        <Title>Письмо отправлено</Title>
        <SuccessBox>
          Если аккаунт с таким email существует, мы отправили инструкции по сбросу пароля.
          Проверьте папку «Входящие» и «Спам».
        </SuccessBox>
        <Footer style={{ marginTop: 24 }}>
          <Link to="/login">Вернуться ко входу</Link>
        </Footer>
      </>
    );
  }

  return (
    <>
      <Title>Забыли пароль?</Title>
      <Sub>Введите ваш email и мы отправим ссылку для сброса пароля</Sub>
      <Form onSubmit={handleSubmit(onSubmit)}>
        {errors.root && <ServerError>{errors.root.message}</ServerError>}
        <Field>
          <Label>Email</Label>
          <Input
            {...register('email')}
            type="email"
            placeholder="you@example.com"
            $error={!!errors.email}
            autoComplete="email"
          />
          {errors.email && <ErrorText>{errors.email.message}</ErrorText>}
        </Field>
        <Btn type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Отправка...' : 'Отправить ссылку'}
        </Btn>
      </Form>
      <Footer>
        <Link to="/login">Вернуться ко входу</Link>
      </Footer>
    </>
  );
}
