import styled from 'styled-components';
import { FileText, Download, Clock, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import { formatDate, formatFileSize } from '@/utils/formatDate';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import type { Document, DocumentStatus } from '@/types/document.types';

const Card = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color var(--transition-fast);
  cursor: pointer;
  &:hover { border-color: var(--color-border-hover); }
`;

const Top = styled.div`
  display: flex;
  gap: 12px;
  align-items: flex-start;
`;

const IconWrap = styled.div`
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  background: var(--color-primary-muted);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
`;

const Info = styled.div`
  flex: 1;
  min-width: 0;
`;

const Title = styled.div`
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const Meta = styled.div`
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
`;

const Footer = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const StatusBadge = styled.span<{ $status: DocumentStatus }>`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: var(--radius-full);
  background: ${({ $status }) => {
    switch ($status) {
      case 'ready':      return 'var(--color-success-muted)';
      case 'error':      return 'var(--color-error-muted)';
      case 'processing': return 'var(--color-info-muted)';
      default:           return 'rgba(255,255,255,0.08)';
    }
  }};
  color: ${({ $status }) => {
    switch ($status) {
      case 'ready':      return 'var(--color-success)';
      case 'error':      return 'var(--color-error)';
      case 'processing': return 'var(--color-info)';
      default:           return 'var(--color-text-secondary)';
    }
  }};
`;

const DownloadBtn = styled.button`
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  color: var(--color-text-secondary);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all var(--transition-fast);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
`;

function StatusIcon({ status }: { status: DocumentStatus }) {
  switch (status) {
    case 'ready':      return <CheckCircle size={12} />;
    case 'error':      return <AlertCircle size={12} />;
    case 'processing': return <Loader size={12} />;
    default:           return <Clock size={12} />;
  }
}

const STATUS_LABELS: Record<DocumentStatus, string> = {
  ready: 'Готов',
  error: 'Ошибка',
  processing: 'Обработка',
  pending: 'В очереди',
};

interface Props {
  document: Document;
  onClick: () => void;
}

export function DocumentCard({ document: doc, onClick }: Props) {
  const addToast = useUIStore((s) => s.addToast);

  const handleDownload = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await documentsApi.download(doc.id, doc.title);
    } catch {
      addToast({ message: 'Ошибка скачивания файла', type: 'error' });
    }
  };

  return (
    <Card onClick={onClick}>
      <Top>
        <IconWrap>
          <FileText size={20} />
        </IconWrap>
        <Info>
          <Title>{doc.title}</Title>
          <Meta>
            {formatDate(doc.created_at)}
            {doc.file_size ? ` · ${formatFileSize(doc.file_size)}` : ''}
          </Meta>
        </Info>
      </Top>
      <Footer>
        <StatusBadge $status={doc.status}>
          <StatusIcon status={doc.status} />
          {STATUS_LABELS[doc.status]}
        </StatusBadge>
        {doc.status === 'ready' && (
          <DownloadBtn onClick={handleDownload}>
            <Download size={13} />
            Скачать
          </DownloadBtn>
        )}
      </Footer>
    </Card>
  );
}
