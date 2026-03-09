import { useCallback, useRef, useState } from 'react';
import styled from 'styled-components';
import { Paperclip, X, Upload } from 'lucide-react';
import { useFileUpload } from '@/hooks/useFileUpload';
import { ALLOWED_EXTENSIONS } from '@/types/document.types';

const Zone = styled.div<{ $drag: boolean }>`
  border: 2px dashed ${({ $drag }) => ($drag ? 'var(--color-primary)' : 'var(--color-border)')};
  border-radius: var(--radius-md);
  padding: 20px;
  text-align: center;
  background: ${({ $drag }) => ($drag ? 'var(--color-primary-muted)' : 'var(--color-surface)')};
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
`;

const HiddenInput = styled.input`
  display: none;
`;

const AttachedFile = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
`;

const FileName = styled.span`
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const RemoveBtn = styled.button`
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  padding: 2px;
  &:hover { color: var(--color-error); }
`;

const ProgressBar = styled.div<{ $pct: number }>`
  height: 3px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
  &::after {
    content: '';
    display: block;
    height: 100%;
    width: ${({ $pct }) => $pct}%;
    background: var(--color-primary);
    transition: width 200ms;
  }
`;

const Hint = styled.div`
  font-size: 11px;
  color: var(--color-text-tertiary);
`;

interface Props {
  onUploaded: (documentId: string, filename: string) => void;
}

export function FileAttachment({ onUploaded }: Props) {
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { upload, isUploading, progress, reset } = useFileUpload();

  const handleFile = useCallback(
    async (f: File) => {
      setFile(f);
      const result = await upload(f);
      if (result) {
        onUploaded(result.document_id, f.name);
      }
    },
    [upload, onUploaded]
  );

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleRemove = () => {
    setFile(null);
    reset();
    if (inputRef.current) inputRef.current.value = '';
  };

  if (file) {
    return (
      <div>
        <AttachedFile>
          <Paperclip size={14} />
          <FileName>{file.name}</FileName>
          {isUploading && <span style={{ fontSize: '11px', color: 'var(--color-text-tertiary)' }}>{progress}%</span>}
          <RemoveBtn onClick={handleRemove}><X size={14} /></RemoveBtn>
        </AttachedFile>
        {isUploading && <ProgressBar $pct={progress} style={{ marginTop: 4 }} />}
      </div>
    );
  }

  return (
    <Zone
      $drag={drag}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <HiddenInput
        ref={inputRef}
        type="file"
        accept={ALLOWED_EXTENSIONS.join(',')}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
        }}
      />
      <Upload size={20} />
      <span>Перетащите файл сюда или нажмите для выбора</span>
      <Hint>Поддерживаются: PDF, DOCX, TXT · до 20 МБ</Hint>
    </Zone>
  );
}
