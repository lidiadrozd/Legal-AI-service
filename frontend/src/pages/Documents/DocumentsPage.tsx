import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import styled from 'styled-components';
import { Upload, FileText } from 'lucide-react';
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
  const addToast = useUIStore((s) => s.addToast);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: documentsApi.list,
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

  return (
    <Page>
      <Header>
        <TitleArea>
          <Title>Документы</Title>
          <Sub>Загруженные файлы для анализа</Sub>
        </TitleArea>
        <UploadBtn>
          <Upload size={16} />
          Загрузить документ
          <input
            type="file"
            accept=".pdf,.docx,.txt,.doc"
            onChange={handleFileChange}
            disabled={isUploading}
          />
        </UploadBtn>
      </Header>

      {isUploading && <ProgressBar $pct={progress} />}

      {isLoading ? (
        <Grid>
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} />)}
        </Grid>
      ) : !data?.length ? (
        <EmptyState>
          <EmptyIcon><FileText size={28} /></EmptyIcon>
          <EmptyTitle>Документов пока нет</EmptyTitle>
          <EmptySub>Загрузите файл PDF, DOCX или TXT для анализа</EmptySub>
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
