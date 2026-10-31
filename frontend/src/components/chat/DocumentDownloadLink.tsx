import { useState, type ReactNode } from 'react';
import styled from 'styled-components';
import { FileDown } from 'lucide-react';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import { getApiErrorMessage } from '@/utils/apiError';

const FileButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 6px 0;
  padding: 12px 16px;
  color: var(--color-text);
  background: var(--color-primary);
  border: 0;
  border-radius: 10px;
  font: inherit;
  cursor: pointer;
  &:disabled { opacity: 0.65; cursor: wait; }
`;

export function DocumentDownloadLink({ href, children }: { href?: string; children?: ReactNode }) {
  const [downloading, setDownloading] = useState(false);
  const addToast = useUIStore((s) => s.addToast);
  const match = href?.match(/^\/documents\/([0-9a-f-]{36})\/download$/i);
  if (!match) return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  const download = async () => {
    setDownloading(true);
    try {
      const doc = await documentsApi.getById(match[1]);
      await documentsApi.download(match[1], doc.title);
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, 'Не удалось скачать файл') });
    } finally {
      setDownloading(false);
    }
  };
  return <FileButton type="button" disabled={downloading} onClick={download}>
    <FileDown size={22} />{downloading ? 'Скачивание…' : children}
  </FileButton>;
}
