import { useEffect, useCallback, useRef, useState } from 'react';
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
import { isDocumentDraftIntent, shouldStartDocumentInterview } from '@/utils/documentInterview';

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
  const interviewRequest = useRef(0);
  const routeChatId = useRef(chatId);
  routeChatId.current = chatId;
  const startingInterview = useRef(false);
  const startAttempt = useRef<{ chatId?: string; prompt: string; id: string } | null>(null);
  const addToast = useUIStore((state) => state.addToast);

  const refreshInterview = useCallback(async (id: string) => {
    const request = ++interviewRequest.current;
    try {
      const state = await documentsApi.getInterview(id);
      if (request !== interviewRequest.current || routeChatId.current !== id) return;
      setInterviewPhase(state.phase);
      setHasTextPackage(Boolean(state.text_package));
      setUnsupportedForm(Boolean(state.unsupported_subject));
      setDocumentTitle(state.document_title || '');
    } catch {
      if (request === interviewRequest.current && routeChatId.current === id) setInterviewPhase(null);
    }
  }, []);

  useEffect(() => {
    setInterviewPhase(null);
    setHasTextPackage(false);
    setUnsupportedForm(false);
    setDocumentTitle('');
  }, [chatId]);

  useEffect(() => {
    if (chatId && !isStreaming) void refreshInterview(chatId);
    return () => { interviewRequest.current += 1; };
  }, [chatId, isStreaming, refreshInterview]);

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
      if (startingInterview.current) {
        addToast({ type: 'info', message: 'Подготовка документа ещё запускается. Дождитесь следующего вопроса.' });
        return;
      }
      // The route is authoritative. In particular, /chat is a genuinely new
      // conversation even briefly before the route-reset effect clears a
      // stale active-chat record from the previous page.
      let chatIdToUse = chatId;

      // A person should not have to find the separate document modal before
      // saying "нужен трудовой договор".  Only an explicit request to prepare
      // a named document starts the guided interview; advice questions stay in
      // the ordinary consultation flow.
      let startsNewInterview = !fileId && isDocumentDraftIntent(content);
      const retryingStart = startAttempt.current?.chatId === chatIdToUse && startAttempt.current?.prompt === content;
      if (startsNewInterview && chatIdToUse) {
        // Do not turn an answer in an active interview into a second document.
        // Completed documents can lead to another document in the same chat.
        try {
          const current = await documentsApi.getInterview(chatIdToUse);
          startsNewInterview = retryingStart || shouldStartDocumentInterview(content, current);
        } catch (error) {
          const status = (error as { response?: { status?: number } })?.response?.status;
          if (status !== 404) {
            addToast({ type: 'error', message: getApiErrorMessage(error, 'Не удалось проверить текущую подготовку документа. Повторите запрос.') });
            return;
          }
          startsNewInterview = true;
        }
      }

      if (startsNewInterview) {
        if (startingInterview.current) return;
        startingInterview.current = true;
        if (startAttempt.current?.chatId !== chatIdToUse || startAttempt.current?.prompt !== content) {
          startAttempt.current = { chatId: chatIdToUse, prompt: content, id: crypto.randomUUID() };
        }
        try {
          const interview = await documentsApi.startInterview({
            prompt: content,
            filename: 'document-draft',
            output_format: 'docx',
            start_request_id: startAttempt.current.id,
            ...(chatIdToUse ? { chat_id: Number(chatIdToUse) } : {}),
          });
          startAttempt.current = null;
          const interviewChatId = String(interview.chat_id);
          if (routeChatId.current !== chatId) {
            await loadChats().catch(() => undefined);
            return;
          }
          if (interviewChatId === chatIdToUse) {
            // Same-route navigation does not rerun effects. Reload persisted
            // messages and the banner without duplicating or renaming a chat.
            const refreshed = await Promise.allSettled([
              openChat(interviewChatId), refreshInterview(interviewChatId),
            ]);
            if (refreshed[0].status === 'rejected') {
              addToast({ type: 'error', message: 'Подготовка начата в этом чате, но сообщения не загрузились. Откройте чат ещё раз.' });
            }
          } else {
            const store = useChatStore.getState();
            const existing = store.chats.find((chat) => chat.id === interviewChatId);
            const newChat = existing ?? {
              id: interviewChatId, title: 'Подготовка документа', user_id: '', message_count: 2,
              created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
            };
            if (!existing) store.addChat(newChat);
            store.setActiveChat(newChat);
            navigate(`/chat/${interviewChatId}`, { replace: true });
          }
          // Refreshing the sidebar is non-essential. If it transiently fails
          // after the interview was created, still take the person to the
          // newly created chat instead of displaying a false start failure.
          await loadChats().catch(() => undefined);
          return;
        } catch (error) {
          addToast({ type: 'error', message: getApiErrorMessage(error, 'Не удалось начать подготовку документа') });
          return;
        } finally {
          startingInterview.current = false;
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
      }, async (recoveredChatId) => {
        await refreshInterview(recoveredChatId);
      });
    },
    [addToast, chatId, loadChats, navigate, openChat, refreshInterview, stream],
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
