import styled from 'styled-components';
import { Download, X, FileText } from 'lucide-react';
import { formatDateTime, formatFileSize } from '@/utils/formatDate';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import type { Document } from '@/types/document.types';

const Overlay = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
`;

const Modal = styled.div`
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  width: 100%;
  max-width: 640px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-elevated);
`;

const ModalHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
`;

const HeaderIcon = styled.div`
  width: 40px;
  height: 40px;
  background: var(--color-primary-muted);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
`;

const HeaderInfo = styled.div`
  flex: 1;
  min-width: 0;
`;

const ModalTitle = styled.div`
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ModalMeta = styled.div`
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
`;

const CloseBtn = styled.button`
  background: var(--color-surface-hover);
  border: none;
  border-radius: var(--radius-sm);
  padding: 8px;
  color: var(--color-text-secondary);
  &:hover { color: var(--color-text); }
`;

const ModalBody = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 24px;
`;

const PlaceholderText = styled.div`
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.7;
  text-align: center;
  padding: 32px;
  background: var(--color-surface);
  border-radius: var(--radius-md);
`;

const ModalFooter = styled.div`
  padding: 16px 24px;
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: flex-end;
`;

const DownloadBtn = styled.button`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  transition: background var(--transition-fast);
  &:hover { background: var(--color-primary-hover); }
`;

interface Props {
  document: Document;
  onClose: () => void;
}

export function DocumentViewer({ document: doc, onClose }: Props) {
  const addToast = useUIStore((s) => s.addToast);

  const handleDownload = async () => {
    try {
      await documentsApi.download(doc.id, doc.title);
    } catch {
      addToast({ message: 'Ошибка скачивания', type: 'error' });
    }
  };

  return (
    <Overlay onClick={onClose}>
      <Modal onClick={(e) => e.stopPropagation()}>
        <ModalHeader>
          <HeaderIcon>
            <FileText size={20} />
          </HeaderIcon>
          <HeaderInfo>
            <ModalTitle>{doc.title}</ModalTitle>
            <ModalMeta>
              {formatDateTime(doc.created_at)}
              {doc.file_size ? ` · ${formatFileSize(doc.file_size)}` : ''}
            </ModalMeta>
          </HeaderInfo>
          <CloseBtn onClick={onClose}>
            <X size={18} />
          </CloseBtn>
        </ModalHeader>
        <ModalBody>
          <PlaceholderText>
            Предпросмотр документа недоступен в браузере.<br />
            Скачайте файл для просмотра содержимого.
          </PlaceholderText>
        </ModalBody>
        <ModalFooter>
          <DownloadBtn onClick={handleDownload}>
            <Download size={16} />
            Скачать документ
          </DownloadBtn>
        </ModalFooter>
      </Modal>
    </Overlay>
  );
}
