import { useEffect, useCallback, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import styled from 'styled-components';
import { FileText } from 'lucide-react';
import { ChatWindow } from '@/components/chat/ChatWindow';
import { MessageInput } from '@/components/chat/MessageInput';
import { useChat } from '@/hooks/useChat';
import { useSSE } from '@/hooks/useSSE';
import { useChatStore } from '@/store/chatStore';
import { chatApi } from '@/api/chat';
import { documentsApi } from '@/api/documents';
import { useUIStore } from '@/store/uiStore';
import { getApiErrorMessage } from '@/utils/apiError';
import { isDocumentDraftIntent } from '@/utils/documentInterview';

const Wrapper = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const WindowWrap = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
`;

const InterviewStatus = styled.div`
  align-self: center;
  width: calc(100% - 48px);
  max-width: 760px;
  box-sizing: border-box;
  margin: 12px 24px 0;
  padding: 10px 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-card);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  line-height: 1.5;
  text-align: center;
  flex-shrink: 0;
  small { display: block; margin-top: 4px; color: var(--color-text-secondary); }
  button { margin-top: 8px; cursor: pointer; }
  @media (max-width: 600px) {
    width: calc(100% - 24px);
    margin: 8px 12px 0;
    padding: 8px 12px;
  }
`;

const DocsBar = styled(Link)`
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 24px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-surface-card);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  text-decoration: none;
  flex-shrink: 0;
  transition:
    border-color var(--transition-fast),
    color var(--transition-fast),
    background var(--transition-fast);
  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: var(--color-primary-muted);
  }
`;

const DocsBarTitle = styled.span`
  font-weight: 600;
  color: var(--color-text);
`;

const DocsBarHint = styled.span`
  color: var(--color-text-tertiary);
  font-size: 12px;
  font-weight: 400;
`;

export default function ChatPage() {
  const { chatId } = useParams<{ chatId?: string }>();
  const navigate = useNavigate();
  const { loadChats, openChat } = useChat();
  const { stream, cancel } = useSSE();
  const isStreaming = useChatStore((state) => state.isStreaming);
  const [interviewPhase, setInterviewPhase] = useState<string | null>(null);
  const [hasTextPackage, setHasTextPackage] = useState(false);
  const [unsupportedForm, setUnsupportedForm] = useState(false);
  const [documentTitle, setDocumentTitle] = useState('');
  const [isExporting, setIsExporting] = useState(false);
  const addToast = useUIStore((state) => state.addToast);

  useEffect(() => {
    setInterviewPhase(null);
    setHasTextPackage(false);
    setUnsupportedForm(false);
    setDocumentTitle('');
  }, [chatId]);

  useEffect(() => {
    let current = true;
    if (chatId && !isStreaming) {
      documentsApi.getInterview(chatId).then((state) => {
        if (current) {
          setInterviewPhase(state.phase);
          setHasTextPackage(Boolean(state.text_package));
          setUnsupportedForm(Boolean(state.unsupported_subject));
          setDocumentTitle(state.document_title || '');
        }
      }).catch(() => { if (current) setInterviewPhase(null); });
    }
    return () => { current = false; };
  }, [chatId, isStreaming]);

  const exportInterview = async () => {
    if (!chatId) return;
    setIsExporting(true);
    try {
      const document = await documentsApi.exportInterview(chatId);
      await documentsApi.download(document.document_id, document.filename);
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, 'Не удалось скачать черновик') });
    } finally {
      setIsExporting(false);
    }
  };

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  useEffect(() => {
    const state = useChatStore.getState();
    // The first send changes /chat to /chat/:id while its stream is already active.
    if (chatId && state.activeChat?.id === chatId && state.isStreaming) return;
    useChatStore.getState().resetStreaming();
    if (chatId) {
      const found = useChatStore.getState().chats.find((c) => c.id === chatId);
      useChatStore.getState().setActiveChat(found ?? {
        id: chatId, title: 'Чат', user_id: '', message_count: 0,
        created_at: '', updated_at: '',
      });
      useChatStore.getState().clearMessages();
      openChat(chatId);
    } else {
      useChatStore.getState().setActiveChat(null);
      useChatStore.getState().clearMessages();
    }
  }, [chatId, openChat]);

  const handleSend = useCallback(
    async (content: string, fileId?: string) => {
      // The route is authoritative. In particular, /chat is a genuinely new
      // conversation even briefly before the route-reset effect clears a
      // stale active-chat record from the previous page.
      let chatIdToUse = chatId;

      // A person should not have to find the separate document modal before
      // saying "нужен трудовой договор".  Only an explicit request to prepare
      // a named document starts the guided interview; advice questions stay in
      // the ordinary consultation flow.
      let startsNewInterview = !fileId && isDocumentDraftIntent(content);
      if (startsNewInterview && chatIdToUse) {
        // Do not turn an answer in an active interview into a second document.
        // A generic or cancelled chat, on the other hand, is precisely where
        // an explicit new document request should start a clean guided flow.
        try {
          const current = await documentsApi.getInterview(chatIdToUse);
          startsNewInterview = current.phase === 'cancelled';
        } catch (error) {
          const status = (error as { response?: { status?: number } })?.response?.status;
          startsNewInterview = status === 404;
        }
      }

      if (startsNewInterview) {
        try {
          const interview = await documentsApi.startInterview({
            prompt: content,
            filename: 'document-draft',
            output_format: 'docx',
            ...(chatIdToUse ? { chat_id: Number(chatIdToUse) } : {}),
          });
          const newChat = {
            id: String(interview.chat_id),
            title: 'Подготовка документа',
            user_id: '',
            message_count: 2,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          useChatStore.getState().addChat(newChat);
          useChatStore.getState().setActiveChat(newChat);
          // Refreshing the sidebar is non-essential. If it transiently fails
          // after the interview was created, still take the person to the
          // newly created chat instead of displaying a false start failure.
          await loadChats().catch(() => undefined);
          navigate(`/chat/${interview.chat_id}`, { replace: true });
          return;
        } catch (error) {
          addToast({ type: 'error', message: getApiErrorMessage(error, 'Не удалось начать подготовку документа') });
          return;
        }
      }

      if (!chatIdToUse) {
        const result = await chatApi.createChat();
        const newChat = {
          id: result.chat_id,
          title: result.title,
          user_id: '',
          message_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        useChatStore.getState().addChat(newChat);
        useChatStore.getState().setActiveChat(newChat);
        chatIdToUse = result.chat_id;
        navigate(`/chat/${chatIdToUse}`, { replace: true });
      }

      const userMsg = {
        id: `tmp-${Date.now()}`,
        chat_id: chatIdToUse,
        role: 'user' as const,
        content,
        created_at: new Date().toISOString(),
      };
      useChatStore.getState().appendMessage(userMsg);

      await stream({
        chat_id: chatIdToUse,
        content,
        attachment_ids: fileId ? [fileId] : undefined,
      });
    },
    [addToast, chatId, loadChats, navigate, stream],
  );

  const handleSuggestion = useCallback(
    (text: string) => handleSend(text),
    [handleSend],
  );

  const currentChatId = chatId ?? '';
  const documentsHref = currentChatId
    ? `/documents?chatId=${encodeURIComponent(currentChatId)}&openGenerate=1&mode=ai`
    : '/documents?openGenerate=1&mode=ai';

  return (
    <Wrapper>
      {interviewPhase && interviewPhase !== 'cancelled' && (
        <InterviewStatus role="status">
            {documentTitle && <strong>{documentTitle}<br /></strong>}
          {unsupportedForm ? 'Готовая форма для этого вида документа пока недоступна.' : interviewPhase === 'ready' ? (
            <button type="button" disabled={isExporting || isStreaming} onClick={exportInterview}>
              {isExporting ? 'Подготовка файла…' : hasTextPackage ? 'Скачать черновик' : 'Скачать черновую структуру'}
            </button>
          ) : 'Заполняем документ — по одному вопросу. Можно попросить пояснение или ответить «не знаю».'}
          <small>{unsupportedForm ? 'Можно выбрать поддерживаемую форму или написать «консультация».' : hasTextPackage
            ? 'Шаблон подготовлен по открытым источникам. Перед использованием нужна проверка юристом.'
            : 'Подбираем подходящий шаблон.'}</small>
        </InterviewStatus>
      )}
      <WindowWrap>
        <ChatWindow onSuggestionClick={handleSuggestion} />
      </WindowWrap>
      <DocsBar to={documentsHref}>
        <FileText size={18} aria-hidden />
        <span>
          <DocsBarTitle>Документы Word / PDF / TXT</DocsBarTitle>
          {' — '}
          <DocsBarHint>
            {currentChatId
              ? 'откроется подготовка по шаблону с уточняющими вопросами'
              : 'начните чат или откройте существующий — тогда подставится его контекст'}
          </DocsBarHint>
        </span>
      </DocsBar>
      <MessageInput onSend={handleSend} onStopStreaming={cancel} />
    </Wrapper>
  );
}
