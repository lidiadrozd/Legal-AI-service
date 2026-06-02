import { useEffect, useRef, useState, useCallback } from 'react';
import styled from 'styled-components';
import { Send, Paperclip, X, StopCircle, Mic, FolderOpen } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';
import { ALLOWED_EXTENSIONS } from '@/types/document.types';
import { LEGAL_DISCLAIMER } from '@/constants/legal';
import { useFileUpload } from '@/hooks/useFileUpload';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { useUIStore } from '@/store/uiStore';
import { documentsApi } from '@/api/documents';
import type { Document } from '@/types/document.types';

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

const IconBtn = styled.button<{ $primary?: boolean; $recording?: boolean }>`
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${({ $primary, $recording }) =>
    $recording ? 'var(--color-error)' : $primary ? 'var(--color-primary)' : 'var(--color-surface-hover)'};
  color: ${({ $primary, $recording }) => ($primary || $recording ? '#fff' : 'var(--color-text-secondary)')};
  transition: background var(--transition-fast), opacity var(--transition-fast);
  &:hover {
    background: ${({ $primary, $recording }) =>
      $recording ? '#dc2626' : $primary ? 'var(--color-primary-hover)' : 'var(--color-border)'};
  }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
`;

const HiddenInput = styled.input`
  display: none;
`;

const PickerBackdrop = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
`;

const PickerModal = styled.div`
  width: min(640px, calc(100vw - 32px));
  max-height: min(70vh, 520px);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
`;

const PickerHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
`;

const PickerTitle = styled.div`
  font-weight: 700;
  color: var(--color-text);
  font-size: 13px;
  flex: 1;
`;

const PickerSearch = styled.input`
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-bottom: 1px solid var(--color-border);
  outline: none;
  background: var(--color-surface-card);
  color: var(--color-text);
  font-size: 13px;
`;

const PickerList = styled.div`
  overflow: auto;
  padding: 8px;
`;

const PickerItem = styled.button`
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-card);
  color: var(--color-text);
  cursor: pointer;
  margin-bottom: 8px;
  &:hover { border-color: var(--color-primary); }
`;

const PickerItemSub = styled.div`
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-text-tertiary);
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
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState('');
  const [pickerDocs, setPickerDocs] = useState<Document[]>([]);
  const [isPickerLoading, setIsPickerLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const { upload, isUploading, progress, reset } = useFileUpload();
  const addToast = useUIStore((s) => s.addToast);
  const voice = useVoiceInput();

  useEffect(() => {
    if (!isPickerOpen) return;
    setIsPickerLoading(true);
    documentsApi
      .list()
      .then((docs) => setPickerDocs(docs))
      .catch(() => {
        addToast({ type: 'error', message: 'Не удалось загрузить список документов' });
        setPickerDocs([]);
      })
      .finally(() => setIsPickerLoading(false));
  }, [isPickerOpen, addToast]);

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

  const pickDoc = (doc: Document) => {
    setAttachedId(doc.id);
    setAttachedName(doc.title);
    setIsPickerOpen(false);
  };

  const handleVoice = async () => {
    voice.clearError();
    const transcript = await voice.toggleRecording();
    if (transcript) {
      setText((prev) => (prev ? `${prev.trimEnd()} ${transcript}` : transcript));
      autoResize();
      addToast({ type: 'success', message: 'Речь распознана' });
    } else if (voice.error) {
      addToast({ type: 'error', message: voice.error });
    }
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
          disabled={isStreaming || isUploading || voice.isBusy}
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={16} />
        </IconBtn>
        <IconBtn
          type="button"
          title="Прикрепить из «Мои документы»"
          disabled={isStreaming || isUploading || voice.isBusy}
          onClick={() => {
            setPickerQuery('');
            setIsPickerOpen(true);
          }}
        >
          <FolderOpen size={16} />
        </IconBtn>
        {voice.isSupported && (
          <IconBtn
            type="button"
            title={
              voice.isTranscribing
                ? 'Распознавание...'
                : voice.isRecording
                  ? 'Остановить и вставить текст'
                  : 'Голосовой ввод (SaluteSpeech)'
            }
            $recording={voice.isRecording}
            disabled={isStreaming || isUploading || voice.isTranscribing}
            onClick={handleVoice}
            aria-pressed={voice.isRecording}
            aria-label="Голосовой ввод"
          >
            <Mic size={16} />
          </IconBtn>
        )}
        <TextArea
          ref={textareaRef}
          value={text}
          onChange={(e) => { setText(e.target.value); autoResize(); }}
          onKeyDown={handleKeyDown}
          placeholder="Задайте юридический вопрос..."
          rows={1}
          disabled={isStreaming || voice.isBusy}
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
      <Hint>
        Enter — отправить · Shift+Enter — новая строка · Скрепка: PDF, DOCX, TXT, фото (JPG/PNG)
        {voice.isSupported ? ' · 🎤 — голосовой ввод (до 1 мин)' : ''}
        {' · '}
        {LEGAL_DISCLAIMER}
      </Hint>
      {isPickerOpen && (
        <PickerBackdrop onClick={() => setIsPickerOpen(false)} role="dialog" aria-modal="true">
          <PickerModal onClick={(e) => e.stopPropagation()}>
            <PickerHeader>
              <PickerTitle>Прикрепить документ из «Мои документы»</PickerTitle>
              <button
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-tertiary)', padding: 2 }}
                onClick={() => setIsPickerOpen(false)}
              >
                <X size={16} />
              </button>
            </PickerHeader>
            <PickerSearch
              value={pickerQuery}
              onChange={(e) => setPickerQuery(e.target.value)}
              placeholder="Поиск по названию…"
              autoFocus
            />
            <PickerList>
              {isPickerLoading ? (
                <div style={{ padding: 12, color: 'var(--color-text-tertiary)', fontSize: 13 }}>Загрузка…</div>
              ) : (
                pickerDocs
                  .filter((d) => (d.title || '').toLowerCase().includes(pickerQuery.trim().toLowerCase()))
                  .slice(0, 50)
                  .map((d) => (
                    <PickerItem key={d.id} onClick={() => pickDoc(d)}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{d.title}</div>
                      <PickerItemSub>id: {d.id}</PickerItemSub>
                    </PickerItem>
                  ))
              )}
              {!isPickerLoading &&
                pickerDocs.filter((d) => (d.title || '').toLowerCase().includes(pickerQuery.trim().toLowerCase()))
                  .length === 0 && (
                  <div style={{ padding: 12, color: 'var(--color-text-tertiary)', fontSize: 13 }}>
                    Ничего не найдено
                  </div>
                )}
            </PickerList>
          </PickerModal>
        </PickerBackdrop>
      )}
    </Wrap>
  );
}
