import type { GenerateAiDocumentRequest } from '@/types/document.types';

export interface StartInterviewResult {
  chat_id: number;
  context_omitted?: boolean;
}

const documentKinds = [
  ['appeal', 'апелляционн[а-яё]*\\s+жалоб[а-яё]*'],
  ['claim', 'исков[а-яё]*\\s+заявлен[а-яё]*|иск(?:а|у|ом|е|и|ов)?'],
  ['pretense', 'претензи[а-яё]*'],
  ['contract', '(?:трудов[а-яё]*\\s+)?договор[а-яё]*'],
  ['motion', 'ходатайств[а-яё]*'],
  ['power_of_attorney', 'доверенност[а-яё]*'],
  ['complaint', 'жалоб[а-яё]*'],
  ['statement', 'заявлен[а-яё]*'],
  ['receipt', 'расписк[а-яё]*'],
  ['agreement', 'соглашени[а-яё]*'],
  ['act', 'акт(?:а|у|ом|е|ы|ов)?'],
] as const;
const documentPattern = documentKinds.map(([, pattern]) => `(?:${pattern})`).join('|');
const word = (pattern: string) => new RegExp(`(?:^|[^\\p{L}\\p{N}_])(?:${pattern})(?=$|[^\\p{L}\\p{N}_])`, 'u');
const documentWord = word(documentPattern);
const prepareVerb = '(?:подготовить|составить|оформить|написать|сделать|создать|сформировать)';
const draftAction = word(`составь(?:те)?|подготовь(?:те)?|оформи(?:те)?|напиши(?:те)?|сделай(?:те)?|создай(?:те)?|сформируй(?:те)?|нужен|нужна|нужны|(?:нужно|хочу|хотел(?:а)?\\s+бы)\\s+(?:${prepareVerb}|(?:новый\\s+|новую\\s+|новое\\s+)?(?:${documentPattern}))|(?:помоги(?:те)?|можешь|можете|прошу)\\s+(?:мне\\s+)?${prepareVerb}`);
const consultation = word('что\\s+(?:такое|нужно|необходимо)|как\\s+(?:мне\\s+)?(?:оспорить|расторгнуть|изменить|проверить|понять|заключить|обжаловать|составить|подготовить|написать)|(?:можно|нужно|нужен|нужна)\\s+ли|(?:какие|какой|какая|какого)\\s+[а-яё]+|(?:помоги(?:те)?|хочу|прошу)\\s+(?:мне\\s+)?(?:понять|разобраться|проверить|оценить)|объясни(?:те)?|расскажи(?:те)?');
const negatedDraft = word('не\\s+(?:(?:надо|нужно|хочу|буду)\\s+(?:составлять|готовить|создавать|писать)|(?:составляй|готовь|создавай|пиши|составь|подготовь)|нужен|нужна|нужно|нужны)');

function draftingClauses(text: string): string[] {
  return text.toLocaleLowerCase('ru-RU').split(/[.!?;\n]+|,?\s+(?:а|но)\s+/u)
    .map((clause) => clause.trim()).filter(Boolean);
}

function requestedDocumentKind(text: string): string | undefined {
  for (const clause of draftingClauses(text)) {
    if (!documentWord.test(clause) || consultation.test(clause) || negatedDraft.test(clause)) continue;
    const bare = new RegExp(`^(?:${documentPattern})$`, 'u').test(clause);
    if (!bare && !draftAction.test(clause)) continue;
    // Prefer the first named document following the action, not the kind of
    // an agreement mentioned later as factual background to an intended claim.
    const target = bare ? clause : clause.slice(clause.search(draftAction));
    const named = documentKinds.map(([kind, pattern]) => ({ kind, index: target.search(word(pattern)) }))
      .filter(({ index }) => index >= 0).sort((a, b) => a.index - b.index);
    if (named.length && word('расч[её]т|проверку|анализ|обзор|список|перевод|выводы|совет|помощь|пример|ответ|возражени[а-яё]*|отзыв').test(target.slice(0, named[0].index))) continue;
    if (named.length) return named[0].kind;
  }
  return undefined;
}

/**
 * Keep ordinary legal consultations in the regular chat, but let a new chat
 * begin the guided document flow when the person explicitly asks to prepare
 * a named legal document.  The server remains the authority for selecting a
 * supported form; this only removes the need to discover a separate modal.
 */
export function isDocumentDraftIntent(text: string): boolean {
  return requestedDocumentKind(text) !== undefined;
}

/** A completed document stays editable; only another kind or an expressly
 * new document begins another workflow. An explicitly separate case goes to
 * the start endpoint even during intake so the server can reject a conflict.
 */
export function shouldStartDocumentInterview(text: string, current: { phase: string; scenario: string | null }): boolean {
  if (!isDocumentDraftIntent(text)) return false;
  if (current.phase === 'cancelled') return true;
  const kind = requestedDocumentKind(text);
  const value = text.toLocaleLowerCase('ru-RU');
  const newCase = /(?:^|[.!?;\n])\s*(?:(?:теперь|это|у меня)\s+){0,2}(?:другой\s+случай|другое\s+дело|новая\s+ситуация)(?=\s*(?:[:.!;,\n]|$))/u;
  const otherCaseCommand = /(?:^|[.!?;\n])\s*(?:пожалуйста[, ]+)?(?:составь(?:те)?|подготовь(?:те)?|оформи(?:те)?|напиши(?:те)?|сделай(?:те)?|создай(?:те)?)\s+(?:нов(?:ый|ую|ое)\s+)?(?:иск|исковое\s+заявление|претензию|документ)\s+по\s+другому\s+делу(?=$|[^\p{L}\p{N}_])/u;
  if (newCase.test(value) || otherCaseCommand.test(value)) return true;
  if (current.phase !== 'ready') return false;
  if (word(`(?:нов(?:ый|ую|ое)|ещ[её]\\s+од(?:ин|ну|но)|друг(?:ой|ую|ое))\\s+(?:${documentPattern}|документ)`).test(value)) return true;
  const scenarioKind = current.scenario === 'power_of_attorney' ? 'power_of_attorney'
    : current.scenario?.split('_')[0];
  const aliases: Record<string, string> = { labor: 'statement', order: 'statement' };
  return Boolean(kind && scenarioKind && kind !== (aliases[scenarioKind] || scenarioKind));
}

/** A supplied chat is required context. Never silently retry in an empty chat. */
export async function startInterviewWithContextRecovery(
  payload: GenerateAiDocumentRequest,
  send: (payload: GenerateAiDocumentRequest) => Promise<StartInterviewResult>,
): Promise<StartInterviewResult> {
  return send(payload);
}
