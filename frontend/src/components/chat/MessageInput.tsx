import { useRef, useState, useCallback } from 'react';
import styled from 'styled-components';
import { Send, Paperclip, X, StopCircle } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';
import { ALLOWED_EXTENSIONS } from '@/types/document.types';
import { useFileUpload } from '@/hooks/useFileUpload';

const Wrap = styled.div`
  padding: 12px 24px 20px;
  background: var(--color-bg);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
`;

const AttachedFile = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-text-secondary);
  max-width: 280px;
`;

const ProgressBar = styled.div<{ $pct: number }>`
  height: 3px;
  background: var(--color-border);
  border-radius: 2px;
  margin-bottom: 8px;
  &::after {
    content: '';
    display: block;
    height: 100%;
    width: ${({ $pct }) => $pct}%;
    background: var(--color-primary);
    transition: width 200ms;
    border-radius: 2px;
  }
`;

const InputRow = styled.div`
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 10px 12px;
  transition: border-color var(--transition-fast);
  &:focus-within { border-color: var(--color-primary); }
`;

const TextArea = styled.textarea`
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--color-text);
  font-size: var(--font-size-sm);
  line-height: 1.5;
  resize: none;
  min-height: 22px;
  max-height: 160px;
  font-family: var(--font-family);
  &::placeholder { color: var(--color-text-tertiary); }
`;

const IconBtn = styled.button<{ $primary?: boolean }>`
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${({ $primary }) => ($primary ? 'var(--color-primary)' : 'var(--color-surface-hover)')};
  color: ${({ $primary }) => ($primary ? '#fff' : 'var(--color-text-secondary)')};
  transition: background var(--transition-fast), opacity var(--transition-fast);
  &:hover { background: ${({ $primary }) => ($primary ? 'var(--color-primary-hover)' : 'var(--color-border)')}; }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
`;

const HiddenInput = styled.input`
  display: none;
`;

const Hint = styled.div`
  text-align: center;
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 8px;
`;

interface Props {
  onSend: (content: string, attachmentId?: string) => void;
  onStopStreaming?: () => void;
}

export function MessageInput({ onSend, onStopStreaming }: Props) {
  const [text, setText] = useState('');
  const [attachedId, setAttachedId] = useState<string | null>(null);
  const [attachedName, setAttachedName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const { upload, isUploading, progress, reset } = useFileUpload();

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    const content = text.trim();
    if (!content || isStreaming) return;
    onSend(content, attachedId ?? undefined);
    setText('');
    setAttachedId(null);
    setAttachedName(null);
    reset();
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const autoResize = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  };

  const handleFile = useCallback(
    async (file: File) => {
      const result = await upload(file);
      if (result) {
        setAttachedId(result.document_id);
        setAttachedName(file.name);
      }
    },
    [upload]
  );

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  return (
    <Wrap>
      {isUploading && <ProgressBar $pct={progress} />}
      {attachedName && !isUploading && (
        <AttachedFile>
          <Paperclip size={12} />
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {attachedName}
          </span>
          <button
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-tertiary)', padding: 2 }}
            onClick={() => { setAttachedId(null); setAttachedName(null); reset(); }}
          >
            <X size={12} />
          </button>
        </AttachedFile>
      )}
      <InputRow>
        <HiddenInput
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={handleFilePick}
        />
        <IconBtn
          type="button"
          title="Прикрепить файл"
          disabled={isStreaming || isUploading}
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={16} />
        </IconBtn>
        <TextArea
          ref={textareaRef}
          value={text}
          onChange={(e) => { setText(e.target.value); autoResize(); }}
          onKeyDown={handleKeyDown}
          placeholder="Задайте юридический вопрос..."
          rows={1}
          disabled={isStreaming}
        />
        {isStreaming ? (
          <IconBtn type="button" onClick={onStopStreaming} title="Остановить">
            <StopCircle size={18} style={{ color: 'var(--color-error)' }} />
          </IconBtn>
        ) : (
          <IconBtn
            $primary
            type="button"
            onClick={handleSend}
            disabled={!text.trim()}
            title="Отправить (Enter)"
          >
            <Send size={16} />
          </IconBtn>
        )}
      </InputRow>
      <Hint>Enter — отправить · Shift+Enter — новая строка</Hint>
    </Wrap>
  );
}
