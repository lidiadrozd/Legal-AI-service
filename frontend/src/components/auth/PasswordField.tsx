import { useState } from 'react';
import styled from 'styled-components';
import { Eye, EyeOff, Check, X } from 'lucide-react'; // Добавил иконки для наглядности
import type { FieldError, UseFormRegisterReturn } from 'react-hook-form';

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

const InputWrap = styled.div`
  position: relative;
`;

const Input = styled.input<{ $error?: boolean }>`
  width: 100%;
  padding: 11px 42px 11px 14px;
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

const ToggleBtn = styled.button`
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  padding: 4px;
  display: flex;
  &:hover { color: var(--color-text-secondary); }
`;

const ErrorText = styled.span`
  font-size: 12px;
  color: var(--color-error);
  margin-top: 4px;
`;

const StrengthBar = styled.div`
  height: 4px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 8px;
`;

const StrengthFill = styled.div<{ $level: number }>`
  height: 100%;
  width: ${({ $level }) => `${$level}%`};
  background: ${({ $level }) =>
    $level < 40 ? 'var(--color-error)' : $level < 70 ? '#e6a700' : 'var(--color-primary)'};
  transition: width 0.2s ease;
`;

const Requirements = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  padding: 8px;
  background: var(--color-surface-hover);
  border-radius: var(--radius-sm);
`;

const ReqItem = styled.div<{ $met: boolean }>`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: ${({ $met }) => ($met ? 'var(--color-primary)' : 'var(--color-text-tertiary)')};
  transition: color 0.2s ease;

  svg { flex-shrink: 0; }
`;

function passwordStrength(value: string): number {
  if (!value) return 0;
  let score = 0;
  if (value.length >= 8) score += 25;
  if (/[A-Z]/.test(value)) score += 25;
  if (/[0-9]/.test(value)) score += 25;
  if (/[^A-Za-z0-9]/.test(value)) score += 25;
  return score;
}

type PasswordFieldProps = {
  id: string;
  label: string;
  registration: UseFormRegisterReturn;
  error?: FieldError;
  placeholder?: string;
  autoComplete?: string;
  showStrength?: boolean;
  value?: string;
};

export function PasswordField({
  id,
  label,
  registration,
  error,
  placeholder,
  autoComplete,
  showStrength,
  value = '',
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const strength = passwordStrength(value);

  // Проверки для списка требований
  const checks = {
    length: value.length >= 8,
    upper: /[A-Z]/.test(value),
    number: /[0-9]/.test(value),
  };

  return (
    <Field>
      <Label htmlFor={id}>{label}</Label>
      <InputWrap>
        <Input
          id={id}
          type={visible ? 'text' : 'password'}
          placeholder="Введите пароль" // Сделали коротким
          $error={!!error}
          autoComplete={autoComplete}
          required
          aria-invalid={!!error}
          {...registration}
        />
        <ToggleBtn
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Скрыть пароль' : 'Показать пароль'}
          tabIndex={-1}
        >
          {visible ? <EyeOff size={18} /> : <Eye size={18} />}
        </ToggleBtn>
      </InputWrap>

      {showStrength && (
        <>
          {value && (
            <StrengthBar id={`${id}-strength`}>
              <StrengthFill $level={strength} />
            </StrengthBar>
          )}
          
          <Requirements>
            <ReqItem $met={checks.length}>
              {checks.length ? <Check size={12} /> : <X size={12} />}
              Минимум 8 символов
            </ReqItem>
            <ReqItem $met={checks.upper}>
              {checks.upper ? <Check size={12} /> : <X size={12} />}
              Одна заглавная буква
            </ReqItem>
            <ReqItem $met={checks.number}>
              {checks.number ? <Check size={12} /> : <X size={12} />}
              Одна цифра
            </ReqItem>
          </Requirements>
        </>
      )}
      
      {error && <ErrorText role="alert">{error.message}</ErrorText>}
    </Field>
  );
}