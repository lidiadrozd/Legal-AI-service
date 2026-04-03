import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import styled from 'styled-components';
import { Upload, FileText, Trash2 } from 'lucide-react';
import { documentsApi } from '@/api/documents';
import { DocumentCard } from '@/components/documents/DocumentCard';
import { DocumentViewer } from '@/components/documents/DocumentViewer';
import { useFileUpload } from '@/hooks/useFileUpload';
import { useUIStore } from '@/store/uiStore';
import type { Document } from '@/types/document.types';

const Page = styled.div`
  padding: 32px;
  max-width: 1200px;
  height: 100%;
  overflow-y: auto;
`;

const Header = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
  gap: 16px;
  flex-wrap: wrap;
`;

const TitleArea = styled.div``;

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 4px;
`;

const Sub = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
`;

const Actions = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
`;

const UploadBtn = styled.label`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
  &:hover { background: var(--color-primary-hover); }
  input { display: none; }
`;

const ClearBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: transparent;
  color: var(--color-error, #f87171);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast);
  &:hover:not(:disabled) {
    border-color: var(--color-error, #f87171);
    background: var(--color-error-muted, rgba(248, 113, 113, 0.12));
  }
  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
`;

const ProgressBar = styled.div<{ $pct: number }>`
  height: 3px;
  margin-bottom: 16px;
  background: var(--color-surface);
  border-radius: 2px;
  overflow: hidden;
  &::after {
    content: '';
    display: block;
    height: 100%;
    width: ${({ $pct }) => $pct}%;
    background: var(--color-primary);
    transition: width 0.2s;
  }
`;

const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 80px 24px;
  color: var(--color-text-secondary);
`;

const EmptyIcon = styled.div`
  width: 64px;
  height: 64px;
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  color: var(--color-text-tertiary);
`;

const EmptyTitle = styled.div`
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 6px;
`;

const EmptySub = styled.div`
  font-size: var(--font-size-sm);
`;

const RetryBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: var(--color-surface);
  color: var(--color-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  &:hover {
    border-color: var(--color-primary);
  }
`;

const Skeleton = styled.div`
  background: var(--color-surface);
  border-radius: var(--radius-md);
  height: 140px;
  animation: skeleton-pulse 1.4s ease-in-out infinite;

  @keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
`;

export default function DocumentsPage() {
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [clearing, setClearing] = useState(false);
  const addToast = useUIStore((s) => s.addToast);
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['documents'],
    queryFn: documentsApi.list,
    retry: 1,
  });

  const { upload, progress, isUploading } = useFileUpload();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const result = await upload(file);
      if (result) {
        addToast({ type: 'success', message: 'Документ успешно загружен' });
        queryClient.invalidateQueries({ queryKey: ['documents'] });
      }
    }
    e.target.value = '';
  };

  const handleClearAll = useCallback(async () => {
    if (!data?.length) return;
    const ok = window.confirm(
      `Удалить все документы (${data.length} шт.)? Файлы будут стёрты безвозвратно.`
    );
    if (!ok) return;
    setClearing(true);
    try {
      const { deleted } = await documentsApi.clearAll();
      setSelectedDoc(null);
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      addToast({
        type: 'success',
        message: deleted ? `Удалено документов: ${deleted}` : 'Список уже был пуст',
      });
    } catch {
      addToast({ type: 'error', message: 'Не удалось очистить документы' });
    } finally {
      setClearing(false);
    }
  }, [addToast, data, queryClient]);

  return (
    <Page>
      <Header>
        <TitleArea>
          <Title>Документы</Title>
          <Sub>Загрузки и документы, созданные в чате (GigaChat)</Sub>
        </TitleArea>
        <Actions>
          <UploadBtn>
            <Upload size={16} />
            Загрузить документ
            <input
              type="file"
              accept=".pdf,.docx,.txt,.doc"
              onChange={handleFileChange}
              disabled={isUploading || clearing}
            />
          </UploadBtn>
          <ClearBtn
            type="button"
            onClick={handleClearAll}
            disabled={isLoading || isError || !data?.length || isUploading || clearing}
          >
            <Trash2 size={16} />
            Очистить всё
          </ClearBtn>
        </Actions>
      </Header>

      {isUploading && <ProgressBar $pct={progress} />}

      {isError ? (
        <EmptyState>
          <EmptyIcon><FileText size={28} /></EmptyIcon>
          <EmptyTitle>Не удалось загрузить список</EmptyTitle>
          <EmptySub style={{ marginBottom: 16 }}>
            {(error as Error)?.message ||
              'Проверьте авторизацию и что backend запущен; в DevTools → Network посмотрите ответ GET /documents.'}
          </EmptySub>
          <RetryBtn type="button" onClick={() => refetch()}>
            Повторить запрос
          </RetryBtn>
        </EmptyState>
      ) : isLoading ? (
        <Grid>
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} />)}
        </Grid>
      ) : !data?.length ? (
        <EmptyState>
          <EmptyIcon><FileText size={28} /></EmptyIcon>
          <EmptyTitle>Документов пока нет</EmptyTitle>
          <EmptySub>
            Загрузите PDF, DOCX или TXT. Документы, которые чат оформляет автоматически, тоже попадают в этот
            список.
          </EmptySub>
        </EmptyState>
      ) : (
        <Grid>
          {data.map((doc) => (
            <DocumentCard key={doc.id} document={doc} onClick={() => setSelectedDoc(doc)} />
          ))}
        </Grid>
      )}

      {selectedDoc && (
        <DocumentViewer document={selectedDoc} onClose={() => setSelectedDoc(null)} />
      )}
    </Page>
  );
}
