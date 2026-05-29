import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { useAuth } from '@/hooks/useAuth';
import { getApiErrorMessage } from '@/utils/apiError';
import { PasswordField } from '@/components/auth/PasswordField';
import { PageMeta } from '@/components/common/PageMeta';

const schema = z
  .object({
    full_name: z.string().min(2, 'Имя должно содержать минимум 2 символа'),
    email: z.string().email('Некорректный email'),
    password: z
      .string()
      .min(8, 'Минимум 8 символов')
      .regex(/[A-Z]/, 'Добавьте хотя бы одну заглавную букву')
      .regex(/[0-9]/, 'Добавьте хотя бы одну цифру'),
    confirm_password: z.string().min(1, 'Подтвердите пароль'),
  })
  .refine((d) => d.password === d.confirm_password, {
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
  gap: 14px;
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
  margin-top: 4px;
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

const Footer = styled.div`
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: 8px;
`;

const ConsentRow = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.5;

  input[type='checkbox'] {
    margin-top: 2px;
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    accent-color: var(--color-primary);
    cursor: pointer;
  }

  label { cursor: pointer; }
`;

export default function RegisterPage() {
  const { register: registerUser } = useAuth();
  const [consentChecked, setConsentChecked] = useState(false);
  const [termsChecked, setTermsChecked] = useState(false);
  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const password = watch('password', '');
  const confirmPassword = watch('confirm_password', '');

  const onSubmit = async (data: FormData) => {
    if (!consentChecked || !termsChecked) {
      setError('root', {
        message:
          'Необходимо принять политику обработки персональных данных и пользовательское соглашение',
      });
      return;
    }
    try {
      await registerUser(
        { email: data.email, full_name: data.full_name, password: data.password },
        true,
      );
    } catch (err) {
      setError('root', {
        message: getApiErrorMessage(err, 'Не удалось зарегистрироваться.'),
      });
    }
  };

  return (
    <>
      <PageMeta title="Регистрация" description="Создание аккаунта в сервисе ИИ-Юрист" />
      <Title>Регистрация</Title>
      <Sub>Создайте аккаунт для доступа к сервису</Sub>
      <Form onSubmit={handleSubmit(onSubmit)} noValidate>
        {errors.root && <ServerError role="alert">{errors.root.message}</ServerError>}
        <Field>
          <Label htmlFor="full_name">Полное имя</Label>
          <Input
            id="full_name"
            {...register('full_name')}
            placeholder="Иванов Иван Иванович"
            $error={!!errors.full_name}
            autoComplete="name"
            required
            aria-invalid={!!errors.full_name}
          />
          {errors.full_name && <ErrorText role="alert">{errors.full_name.message}</ErrorText>}
        </Field>
        <Field>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            {...register('email')}
            type="email"
            placeholder="you@example.com"
            $error={!!errors.email}
            autoComplete="email"
            required
            aria-invalid={!!errors.email}
          />
          {errors.email && <ErrorText role="alert">{errors.email.message}</ErrorText>}
        </Field>
        <PasswordField
          id="password"
          label="Пароль"
          registration={register('password')}
          error={errors.password}
          placeholder="Минимум 8 символов, 1 заглавная, 1 цифра"
          autoComplete="new-password"
          showStrength
          value={password}
        />
        <PasswordField
          id="confirm_password"
          label="Подтверждение пароля"
          registration={register('confirm_password')}
          error={errors.confirm_password}
          placeholder="Повторите пароль"
          autoComplete="new-password"
          value={confirmPassword}
        />
        <ConsentRow>
          <input
            type="checkbox"
            id="consent"
            checked={consentChecked}
            onChange={(e) => setConsentChecked(e.target.checked)}
            required
          />
          <label htmlFor="consent">
            Я согласен с{' '}
            <Link to="/privacy" target="_blank" rel="noopener noreferrer">
              политикой обработки персональных данных
            </Link>
          </label>
        </ConsentRow>
        <ConsentRow>
          <input
            type="checkbox"
            id="terms"
            checked={termsChecked}
            onChange={(e) => setTermsChecked(e.target.checked)}
            required
          />
          <label htmlFor="terms">
            Я принимаю{' '}
            <Link to="/terms" target="_blank" rel="noopener noreferrer">
              пользовательское соглашение
            </Link>
          </label>
        </ConsentRow>
        <Btn type="submit" disabled={isSubmitting} aria-busy={isSubmitting}>
          {isSubmitting ? 'Создание аккаунта...' : 'Создать аккаунт'}
        </Btn>
      </Form>
      <Footer>
        Уже есть аккаунт? <Link to="/login">Войти</Link>
      </Footer>
    </>
  );
}
