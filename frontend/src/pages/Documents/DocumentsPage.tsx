import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import styled from 'styled-components';
import { Upload, FileText, Sparkles, X } from 'lucide-react';
import { chatApi } from '@/api/chat';
import { courtFilingsApi } from '@/api/courtFilings';
import { documentsApi } from '@/api/documents';
import { DocumentCard } from '@/components/documents/DocumentCard';
import { DocumentViewer } from '@/components/documents/DocumentViewer';
import { useFileUpload } from '@/hooks/useFileUpload';
import { useUIStore } from '@/store/uiStore';
import type {
  Document,
  DocumentTemplateMeta,
  GenerateDocumentRequest,
} from '@/types/document.types';

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

const Actions = styled.div`
  display: flex;
  gap: 10px;
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

const GenerateBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: var(--color-surface-card);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  &:hover { border-color: var(--color-primary); color: var(--color-primary); }
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

const ModalOverlay = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
`;

const Modal = styled.div`
  width: 100%;
  max-width: 560px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-elevated);
`;

const ModalHeader = styled.div`
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const ModalTitle = styled.h3`
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--color-text);
`;

const CloseBtn = styled.button`
  border: none;
  background: none;
  color: var(--color-text-tertiary);
  padding: 4px;
`;

const ModalBody = styled.div`
  padding: 18px 20px;
  display: grid;
  gap: 10px;
`;

const Label = styled.label`
  display: grid;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
`;

const Input = styled.input`
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  padding: 0 10px;
`;

const TextArea = styled.textarea`
  min-height: 74px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  padding: 8px 10px;
  resize: vertical;
`;

const Select = styled.select`
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  padding: 0 10px;
`;

const ModalFooter = styled.div`
  border-top: 1px solid var(--color-border);
  padding: 14px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
`;

const Button = styled.button<{ $primary?: boolean }>`
  height: 36px;
  padding: 0 14px;
  border-radius: var(--radius-sm);
  border: ${({ $primary }) => ($primary ? 'none' : '1px solid var(--color-border)')};
  background: ${({ $primary }) => ($primary ? 'var(--color-primary)' : 'var(--color-surface)')};
  color: ${({ $primary }) => ($primary ? '#fff' : 'var(--color-text)')};
`;

export default function DocumentsPage() {
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [templateKey, setTemplateKey] = useState<GenerateDocumentRequest['template_key']>('statement_of_claim_arbitration');
  const [outputFormat, setOutputFormat] = useState<GenerateDocumentRequest['output_format']>('docx');
  const [filename, setFilename] = useState('document-draft');
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [selectedChatId, setSelectedChatId] = useState('');
  const [selectedFilingId, setSelectedFilingId] = useState('');
  const addToast = useUIStore((s) => s.addToast);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: documentsApi.list,
  });
  const { data: templates } = useQuery({
    queryKey: ['document-templates'],
    queryFn: documentsApi.listTemplates,
  });
  const { data: chats } = useQuery({
    queryKey: ['chats'],
    queryFn: chatApi.getChats,
    enabled: showGenerateModal,
  });
  const { data: filings } = useQuery({
    queryKey: ['court-filings-submissions'],
    queryFn: courtFilingsApi.list,
    enabled: showGenerateModal,
  });

  const { upload, progress, isUploading } = useFileUpload();
  const selectedTemplate = useMemo(
    () => templates?.find((t) => t.key === templateKey),
    [templates, templateKey]
  );

  useEffect(() => {
    if (!selectedTemplate) return;
    setFieldValues((prev) => {
      const next: Record<string, string> = {};
      for (const field of selectedTemplate.fields) {
        next[field.key] = prev[field.key] ?? '';
      }
      return next;
    });
  }, [selectedTemplate]);

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

  const handleSuggestFromContext = async () => {
    try {
      setIsSuggesting(true);
      const res = await documentsApi.suggestFields({
        template_key: templateKey,
        ...(selectedChatId ? { chat_id: Number(selectedChatId) } : {}),
        ...(selectedFilingId ? { court_filing_id: Number(selectedFilingId) } : {}),
      });
      setFieldValues((prev) => {
        const next: Record<string, string> = { ...prev };
        for (const [key, value] of Object.entries(res.suggested)) {
          if (!(next[key] ?? '').trim()) {
            next[key] = value;
          }
        }
        return next;
      });
      addToast({ type: 'success', message: 'Поля подставлены (пустые ячейки заполнены)' });
    } catch {
      addToast({ type: 'error', message: 'Не удалось подставить поля' });
    } finally {
      setIsSuggesting(false);
    }
  };

  const handleGenerate = async () => {
    try {
      setIsGenerating(true);
      if (selectedTemplate) {
        for (const field of selectedTemplate.fields) {
          const value = fieldValues[field.key] ?? '';
          if (field.pattern) {
            const re = new RegExp(field.pattern);
            if (!re.test(value)) {
              addToast({
                type: 'error',
                message: `Поле "${field.label}" заполнено в неверном формате`,
              });
              setIsGenerating(false);
              return;
            }
          }
        }
      }
      const chatIdNum = selectedChatId ? Number(selectedChatId) : undefined;
      const filingIdNum = selectedFilingId ? Number(selectedFilingId) : undefined;
      await documentsApi.generate({
        template_key: templateKey,
        filename: filename.trim() || 'generated-document',
        fields: fieldValues,
        output_format: outputFormat,
        template_version: selectedTemplate?.version,
        ...(chatIdNum ? { chat_id: chatIdNum } : {}),
        ...(filingIdNum ? { court_filing_id: filingIdNum } : {}),
      });
      setShowGenerateModal(false);
      setFieldValues({});
      addToast({ type: 'success', message: 'Документ сгенерирован' });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    } catch {
      addToast({ type: 'error', message: 'Ошибка генерации документа' });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <Page>
      <Header>
        <TitleArea>
          <Title>Документы</Title>
          <Sub>Загруженные файлы для анализа</Sub>
        </TitleArea>
        <Actions>
          <GenerateBtn onClick={() => setShowGenerateModal(true)}>
            <Sparkles size={16} />
            Заполнить по шаблону
          </GenerateBtn>
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
        </Actions>
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

      {showGenerateModal && (
        <ModalOverlay onClick={() => setShowGenerateModal(false)}>
          <Modal onClick={(e) => e.stopPropagation()}>
            <ModalHeader>
              <ModalTitle>Генерация документа</ModalTitle>
              <CloseBtn onClick={() => setShowGenerateModal(false)}>
                <X size={18} />
              </CloseBtn>
            </ModalHeader>
            <ModalBody>
              <Label>
                Шаблон
                <Select value={templateKey} onChange={(e) => setTemplateKey(e.target.value as GenerateDocumentRequest['template_key'])}>
                  {templates?.map((tpl: DocumentTemplateMeta) => (
                    <option key={tpl.key} value={tpl.key}>
                      {tpl.title}
                    </option>
                  ))}
                </Select>
              </Label>
              <Label>
                Формат
                <Select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value as GenerateDocumentRequest['output_format'])}>
                  <option value="docx">DOCX (с форматированием)</option>
                  <option value="pdf">PDF</option>
                  <option value="txt">TXT</option>
                </Select>
              </Label>
              <Label>
                Имя файла
                <Input value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="my-document" />
              </Label>
              <Label>
                Чат (опционально)
                <Select value={selectedChatId} onChange={(e) => setSelectedChatId(e.target.value)}>
                  <option value="">— не использовать —</option>
                  {chats?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </Select>
              </Label>
              <Label>
                Подача в суд (опционально)
                <Select value={selectedFilingId} onChange={(e) => setSelectedFilingId(e.target.value)}>
                  <option value="">— не использовать —</option>
                  {filings?.map((f) => (
                    <option key={f.id} value={String(f.id)}>
                      {f.case_number} — {f.court_name}
                    </option>
                  ))}
                </Select>
              </Label>
              <GenerateBtn type="button" onClick={handleSuggestFromContext} disabled={isSuggesting}>
                <Sparkles size={16} />
                {isSuggesting ? 'Подстановка…' : 'Подставить из чата / подачи'}
              </GenerateBtn>
              {selectedTemplate?.fields.map((field) => (
                <Label key={field.key}>
                  {field.label}
                  {field.pattern && <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>Формат: {field.pattern}</span>}
                  {field.multiline ? (
                    <TextArea
                      value={fieldValues[field.key] ?? ''}
                      onChange={(e) =>
                        setFieldValues((prev) => ({
                          ...prev,
                          [field.key]: e.target.value,
                        }))
                      }
                    />
                  ) : (
                    <Input
                      value={fieldValues[field.key] ?? ''}
                      onChange={(e) =>
                        setFieldValues((prev) => ({
                          ...prev,
                          [field.key]: e.target.value,
                        }))
                      }
                    />
                  )}
                </Label>
              ))}
            </ModalBody>
            <ModalFooter>
              <Button onClick={() => setShowGenerateModal(false)}>Отмена</Button>
              <Button $primary onClick={handleGenerate} disabled={isGenerating}>
                {isGenerating ? 'Генерация...' : 'Сгенерировать'}
              </Button>
            </ModalFooter>
          </Modal>
        </ModalOverlay>
      )}
    </Page>
  );
}
