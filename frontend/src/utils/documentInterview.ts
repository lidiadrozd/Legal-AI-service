import type { GenerateAiDocumentRequest } from '@/types/document.types';

export interface StartInterviewResult {
  chat_id: number;
  context_omitted?: boolean;
}

/**
 * Keep ordinary legal consultations in the regular chat, but let a new chat
 * begin the guided document flow when the person explicitly asks to prepare
 * a named legal document.  The server remains the authority for selecting a
 * supported form; this only removes the need to discover a separate modal.
 */
export function isDocumentDraftIntent(text: string): boolean {
  const value = text.trim().toLocaleLowerCase('ru-RU');
  if (!value) return false;

  const documentName = /(?:исков\w*\s+заявлен\w*|претензи\w*|трудов\w*\s+договор\w*|договор\w*|ходатайств\w*|доверенност\w*|апелляционн\w*\s+жалоб\w*|жалоб\w*|заявлен\w*|расписк\w*|соглашени\w*|акт\w*)/u;
  if (!documentName.test(value)) return false;

  // Do not intercept an advice request merely because it mentions a document:
  // “как оспорить договор?” and “помоги проверить договор” must remain a
  // consultation.  A short bare document name is deliberately treated as a
  // drafting request: this is how people commonly answer “какой документ
  // нужен?” (for example, simply “трудовой договор”).
  const consultation = /(?:\b(?:что|какой|какая|какие)\b|\bкак\s+(?:оспорить|расторгнуть|изменить|проверить|понять|заключить|обжаловать)\b|\b(?:можно|нуж\w*)\s+ли\b|\bпомог(?:и|ите)\s+(?:понять|разобраться|проверить|оценить)\b|\bобъясн\w*\b|\bрасскаж\w*\b)/u;
  if (consultation.test(value)) return false;

  const draftingAction = /(?:\bнуж\w*\b|\b(?:подготов|состав|оформ|напис|сдела)\w*\b|\bпомог(?:и|ите)\s+(?:мне\s+)?(?:подготов|состав|оформ|напис|сдела)\w*)/u;
  return draftingAction.test(value) || value.length <= 90;
}

/** Retry only when the server rejected the optional source chat before creation.
 * Timeouts and generic 404s must not create a second interview.
 */
export async function startInterviewWithContextRecovery(
  payload: GenerateAiDocumentRequest,
  send: (payload: GenerateAiDocumentRequest) => Promise<StartInterviewResult>,
): Promise<StartInterviewResult> {
  try {
    return await send(payload);
  } catch (error) {
    const response = (error as { response?: { status?: number; data?: { detail?: unknown; error?: unknown } } })?.response;
    const detail = response?.data?.detail ?? response?.data?.error;
    const code = detail && typeof detail === 'object' && 'code' in detail ? detail.code : null;
    if (payload.chat_id == null || response?.status !== 404 || code !== 'chat_context_unavailable') throw error;
    const retryPayload = { ...payload };
    delete retryPayload.chat_id;
    const result = await send(retryPayload);
    return { ...result, context_omitted: true };
  }
}
