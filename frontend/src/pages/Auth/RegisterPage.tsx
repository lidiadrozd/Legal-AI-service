import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { useAuth } from '@/hooks/useAuth';
import { getApiErrorMessage } from '@/utils/apiError';

const schema = z
  .object({
    full_name: z.string().min(2, 'Имя должно содержать минимум 2 символа'),
    email: z.string().email('Некорректный email'),
    password: z
      .string()
      .min(8, 'Минимум 8 символов')
      .regex(/[A-Z]/, 'Добавьте хотя бы одну заглавную букву')
      .regex(/[0-9]/, 'Добавьте хотя бы одну цифру'),
    confirm_password: z.string(),
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

export default function RegisterPage() {
  const { register: registerUser } = useAuth();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    try {
      await registerUser({ email: data.email, full_name: data.full_name, password: data.password });
    } catch (err) {
      setError('root', {
        message: getApiErrorMessage(err, 'Не удалось зарегистрироваться.'),
      });
    }
  };

  return (
    <>
      <Title>Регистрация</Title>
      <Sub>Создайте аккаунт для получения консультаций</Sub>
      <Form onSubmit={handleSubmit(onSubmit)}>
        {errors.root && <ServerError>{errors.root.message}</ServerError>}
        <Field>
          <Label>Полное имя</Label>
          <Input
            {...register('full_name')}
            placeholder="Иванов Иван Иванович"
            $error={!!errors.full_name}
            autoComplete="name"
          />
          {errors.full_name && <ErrorText>{errors.full_name.message}</ErrorText>}
        </Field>
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
        <Field>
          <Label>Пароль</Label>
          <Input
            {...register('password')}
            type="password"
            placeholder="Минимум 8 символов, 1 заглавная, 1 цифра"
            $error={!!errors.password}
            autoComplete="new-password"
          />
          {errors.password && <ErrorText>{errors.password.message}</ErrorText>}
        </Field>
        <Field>
          <Label>Подтверждение пароля</Label>
          <Input
            {...register('confirm_password')}
            type="password"
            placeholder="Повторите пароль"
            $error={!!errors.confirm_password}
            autoComplete="new-password"
          />
          {errors.confirm_password && <ErrorText>{errors.confirm_password.message}</ErrorText>}
        </Field>
        <Btn type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Создание аккаунта...' : 'Создать аккаунт'}
        </Btn>
      </Form>
      <Footer>
        Уже есть аккаунт? <Link to="/login">Войти</Link>
      </Footer>
    </>
  );
}
