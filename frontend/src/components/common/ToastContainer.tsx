import styled, { keyframes } from 'styled-components';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';
import type { Toast } from '@/store/uiStore';

const slideIn = keyframes`
  from { transform: translateX(110%); opacity: 0; }
  to   { transform: translateX(0);    opacity: 1; }
`;

const Container = styled.div`
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 360px;
  width: 100%;
`;

const ToastItem = styled.div<{ $type: Toast['type'] }>`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-left: 3px solid
    ${({ $type }) => {
      switch ($type) {
        case 'success': return 'var(--color-success)';
        case 'error':   return 'var(--color-error)';
        case 'warning': return 'var(--color-warning)';
        default:        return 'var(--color-info)';
      }
    }};
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-elevated);
  animation: ${slideIn} 200ms ease;
`;

const IconWrap = styled.div<{ $type: Toast['type'] }>`
  flex-shrink: 0;
  color: ${({ $type }) => {
    switch ($type) {
      case 'success': return 'var(--color-success)';
      case 'error':   return 'var(--color-error)';
      case 'warning': return 'var(--color-warning)';
      default:        return 'var(--color-info)';
    }
  }};
`;

const Msg = styled.div`
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  line-height: 1.4;
`;

const CloseBtn = styled.button`
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  padding: 2px;
  &:hover { color: var(--color-text); }
`;

function ToastIcon({ type }: { type: Toast['type'] }) {
  const size = 16;
  switch (type) {
    case 'success': return <CheckCircle size={size} />;
    case 'error':   return <AlertCircle size={size} />;
    case 'warning': return <AlertTriangle size={size} />;
    default:        return <Info size={size} />;
  }
}

export function ToastContainer() {
  const { toasts, removeToast } = useUIStore();

  return (
    <Container>
      {toasts.map((toast) => (
        <ToastItem key={toast.id} $type={toast.type}>
          <IconWrap $type={toast.type}>
            <ToastIcon type={toast.type} />
          </IconWrap>
          <Msg>{toast.message}</Msg>
          <CloseBtn onClick={() => removeToast(toast.id)}>
            <X size={14} />
          </CloseBtn>
        </ToastItem>
      ))}
    </Container>
  );
}
