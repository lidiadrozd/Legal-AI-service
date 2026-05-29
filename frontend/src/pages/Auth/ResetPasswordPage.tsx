import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { authApi } from '@/api/auth';
import { getApiErrorMessage } from '@/utils/apiError';

const schema = z
  .object({
    new_password: z
      .string()
      .min(8, 'Минимум 8 символов')
      .regex(/[A-Z]/, 'Нужна хотя бы одна заглавная буква')
      .regex(/[0-9]/, 'Нужна хотя бы одна цифра'),
    confirm_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: 'Пароли не совпадают',
    path: ['confirm_password'],
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

const InvalidBox = styled.div`
  padding: 16px;
  background: var(--color-error-muted);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-error);
  line-height: 1.5;
`;

const Footer = styled.div`
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: 8px;
`;

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [done, setDone] = useState(false);
  const token = searchParams.get('token');

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  if (!token) {
    return (
      <>
        <Title>Сброс пароля</Title>
        <InvalidBox>
          Ссылка недействительна или истекла.{' '}
          <Link to="/forgot-password">Запросить новую ссылку</Link>
        </InvalidBox>
      </>
    );
  }

  const onSubmit = async (data: FormData) => {
    try {
      await authApi.resetPassword(token, data.new_password);
      setDone(true);
      setTimeout(() => navigate('/login'), 3000);
    } catch (err) {
      setError('root', {
        message: getApiErrorMessage(err, 'Ссылка недействительна или истекла.'),
      });
    }
  };

  if (done) {
    return (
      <>
        <Title>Готово!</Title>
        <SuccessBox>
          Пароль успешно изменён. Сейчас вы будете перенаправлены на страницу входа...
        </SuccessBox>
      </>
    );
  }

  return (
    <>
      <Title>Новый пароль</Title>
      <Sub>Придумайте новый пароль для вашего аккаунта</Sub>
      <Form onSubmit={handleSubmit(onSubmit)}>
        {errors.root && <ServerError>{errors.root.message}</ServerError>}
        <Field>
          <Label>Новый пароль</Label>
          <Input
            {...register('new_password')}
            type="password"
            placeholder="••••••••"
            $error={!!errors.new_password}
            autoComplete="new-password"
          />
          {errors.new_password && <ErrorText>{errors.new_password.message}</ErrorText>}
        </Field>
        <Field>
          <Label>Подтвердите пароль</Label>
          <Input
            {...register('confirm_password')}
            type="password"
            placeholder="••••••••"
            $error={!!errors.confirm_password}
            autoComplete="new-password"
          />
          {errors.confirm_password && <ErrorText>{errors.confirm_password.message}</ErrorText>}
        </Field>
        <Btn type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Сохранение...' : 'Сохранить пароль'}
        </Btn>
      </Form>
      <Footer>
        <Link to="/login">Вернуться ко входу</Link>
      </Footer>
    </>
  );
}
