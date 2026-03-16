import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { useAuth } from '@/hooks/useAuth';

const schema = z.object({
  email: z.string().email('Некорректный email'),
  password: z.string().min(1, 'Введите пароль'),
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

const Footer = styled.div`
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: 8px;
`;

export default function LoginPage() {
  const { login } = useAuth();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    try {
      await login(data);
    } catch {
      setError('root', { message: 'Неверный email или пароль' });
    }
  };

  return (
    <>
      <Title>Вход</Title>
      <Sub>Введите данные вашего аккаунта</Sub>
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
        <Field>
          <Label>Пароль</Label>
          <Input
            {...register('password')}
            type="password"
            placeholder="••••••••"
            $error={!!errors.password}
            autoComplete="current-password"
          />
          {errors.password && <ErrorText>{errors.password.message}</ErrorText>}
        </Field>
        <Btn type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Вход...' : 'Войти'}
        </Btn>
      </Form>
      <Footer>
        Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
      </Footer>
    </>
  );
}
