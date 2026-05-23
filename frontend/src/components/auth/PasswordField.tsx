import { useState } from 'react';
import styled from 'styled-components';
import { Eye, EyeOff } from 'lucide-react';
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
`;

const StrengthBar = styled.div`
  height: 4px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
`;

const StrengthFill = styled.div<{ $level: number }>`
  height: 100%;
  width: ${({ $level }) => `${$level}%`};
  background: ${({ $level }) =>
    $level < 40 ? 'var(--color-error)' : $level < 70 ? '#e6a700' : 'var(--color-primary)'};
  transition: width 0.2s ease;
`;

const StrengthHint = styled.span`
  font-size: 11px;
  color: var(--color-text-tertiary);
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

  return (
    <Field>
      <Label htmlFor={id}>{label}</Label>
      <InputWrap>
        <Input
          id={id}
          type={visible ? 'text' : 'password'}
          placeholder={placeholder}
          $error={!!error}
          autoComplete={autoComplete}
          required
          aria-invalid={!!error}
          aria-describedby={showStrength ? `${id}-strength` : undefined}
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
      {showStrength && value && (
        <>
          <StrengthBar id={`${id}-strength`} aria-hidden>
            <StrengthFill $level={strength} />
          </StrengthBar>
          <StrengthHint>
            {strength < 50
              ? 'Слабый пароль: минимум 8 символов, заглавная буква и цифра'
              : strength < 100
                ? 'Средний пароль'
                : 'Надёжный пароль'}
          </StrengthHint>
        </>
      )}
      {error && <ErrorText role="alert">{error.message}</ErrorText>}
    </Field>
  );
}
