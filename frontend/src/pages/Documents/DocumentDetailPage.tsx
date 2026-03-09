import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import styled from 'styled-components';
import { ArrowLeft, Download, FileText } from 'lucide-react';
import { documentsApi } from '@/api/documents';
import { formatDateTime, formatFileSize } from '@/utils/formatDate';
import { useUIStore } from '@/store/uiStore';

const Page = styled.div`
  padding: 32px;
  max-width: 800px;
  height: 100%;
  overflow-y: auto;
`;

const BackBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: none;
  border: none;
  padding: 0;
  margin-bottom: 24px;
  cursor: pointer;
  transition: color var(--transition-fast);
  &:hover { color: var(--color-text); }
`;

const Card = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
`;

const DocHeader = styled.div`
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
`;

const DocIcon = styled.div`
  width: 48px;
  height: 48px;
  background: var(--color-primary-muted);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
  flex-shrink: 0;
`;

const DocInfo = styled.div`
  flex: 1;
  min-width: 0;
`;

const DocName = styled.h1`
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 6px;
  word-break: break-word;
`;

const Meta = styled.dl`
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 8px 20px;
  font-size: var(--font-size-sm);
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
`;

const Dt = styled.dt`
  color: var(--color-text-secondary);
`;

const Dd = styled.dd`
  color: var(--color-text);
`;

const DownloadBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
  margin-top: 20px;
  &:hover { background: var(--color-primary-hover); }
`;

const StatusBadge = styled.span<{ $status: string }>`
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  background: ${({ $status }) =>
    $status === 'processed' ? 'var(--color-success-muted)' :
    $status === 'error' ? 'var(--color-error-muted)' : 'var(--color-warning-muted)'};
  color: ${({ $status }) =>
    $status === 'processed' ? 'var(--color-success)' :
    $status === 'error' ? 'var(--color-error)' : 'var(--color-warning)'};
`;

const STATUS_LABELS: Record<string, string> = {
  ready: 'Готов',
  processing: 'Обрабатывается',
  pending: 'В очереди',
  error: 'Ошибка',
};

export default function DocumentDetailPage() {
  const { docId } = useParams<{ docId: string }>();
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);

  const { data: doc, isLoading } = useQuery({
    queryKey: ['document', docId],
    queryFn: () => documentsApi.getById(docId!),
    enabled: !!docId,
  });

  const handleDownload = () => {
    if (!doc) return;
    documentsApi.download(doc.id, doc.title).catch(() => {
      addToast({ type: 'error', message: 'Не удалось скачать файл' });
    });
  };

  return (
    <Page>
      <BackBtn onClick={() => navigate('/documents')}>
        <ArrowLeft size={16} />
        К документам
      </BackBtn>
      {isLoading ? (
        <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-sm)' }}>Загрузка...</div>
      ) : doc ? (
        <Card>
          <DocHeader>
            <DocIcon><FileText size={22} /></DocIcon>
            <DocInfo>
              <DocName>{doc.title}</DocName>
              <StatusBadge $status={doc.status}>{STATUS_LABELS[doc.status] ?? doc.status}</StatusBadge>
            </DocInfo>
          </DocHeader>
          <Meta>
            <Dt>Тип файла</Dt>
            <Dd>{doc.mime_type ?? '—'}</Dd>
            <Dt>Размер</Dt>
            <Dd>{doc.file_size ? formatFileSize(doc.file_size) : '—'}</Dd>
            <Dt>Загружен</Dt>
            <Dd>{formatDateTime(doc.created_at)}</Dd>
          </Meta>
          <DownloadBtn onClick={handleDownload}>
            <Download size={14} />
            Скачать
          </DownloadBtn>
        </Card>
      ) : (
        <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-sm)' }}>Документ не найден</div>
      )}
    </Page>
  );
}
