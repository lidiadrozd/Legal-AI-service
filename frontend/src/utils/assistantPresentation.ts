const labels: Record<string, string> = {
  вид_документа: 'Вид документа', суд: 'Суд', истец: 'Заявитель', ответчик: 'Адресат',
  адрес_истца: 'Адрес заявителя', адрес_ответчика: 'Адрес адресата', номер_дела: 'Номер дела',
  дата: 'Дата', приложения: 'Приложения', подпись: 'Подпись',
  арендодатель: 'Арендодатель', арендатор: 'Арендатор',
};

/** Fix sentence starts while preserving links, code and legal/address abbreviations. */
export function capitalizeSentences(text: string): string {
  return text.split(/(```[\s\S]*?```|`[^`\n]+`|https?:\/\/[^\s)]+|\]\([^\n)]+\))/g)
    .map((part, index) => {
      if (index % 2) return part;
      return part.replace(/(^|\n[\t ]*(?:[-*#>]\s+|\d+[.)]\s+)?|[.!?][»”"')]*\s+)([«„"'(*_]*)([а-яёa-z])/g,
        (match, boundary: string, quotes: string, letter: string, offset: number) => {
          const prefix = part.slice(0, offset + boundary.length);
          if (boundary.includes('.') && /(?:^|[^а-яёa-z])(?:e\.g|i\.e|ст|ч|п|подп|абз|г|ул|д|кв|им|руб|тыс|т\.\s*д|т\.\s*п)\.\s*$/iu.test(prefix)) return match;
          return boundary + quotes + letter.toUpperCase();
        });
    }).join('');
}

/** Display legacy replies without modifying their stored text or legal references. */
export function presentAssistantMessage(content: string): string {
  let text = content.replace(/(^|\n)\s*Не является юридической консультацией\.\s*/g, '$1').trim();
  const raw = text.replace(/^```(?:json)?\s*/i, '');
  if (raw.startsWith('{')) {
    const end = raw.lastIndexOf('}');
    try {
      const draft: unknown = JSON.parse(raw.slice(0, end + 1));
      if (draft && typeof draft === 'object' && 'заголовок' in draft && 'текст' in draft &&
          typeof draft.заголовок === 'string' && typeof draft.текст === 'string') {
        let requisites = '';
        if ('реквизиты' in draft && draft.реквизиты && typeof draft.реквизиты === 'object') {
          const lines = Object.entries(draft.реквизиты).filter(([, value]) =>
            typeof value === 'string' ? value.trim() : Array.isArray(value) && value.length
          ).map(([key, value]) => `- **${labels[key] || key.replace(/_/g, ' ')}:** ${
            Array.isArray(value) ? value.join('; ') : value
          }`);
          if (lines.length) requisites = `\n\n**Реквизиты**\n\n${lines.join('\n')}`;
        }
        const suffix = raw.slice(end + 1).replace(/^\s*```/, '').trim();
        text = `**${draft.заголовок}**\n\n${draft.текст}${requisites}${suffix ? '\n\n' + suffix : ''}`;
      }
    } catch {
      // Incomplete streaming JSON is left intact until the object is complete.
    }
  }
  return capitalizeSentences(text
    .replace(/(?:\*{1,2})?\bconfidence\s*[:=]\s*(?:high|medium|low)(?:\*{1,2})?/gi, '')
    .replace(/\*{0,2}(?:Уверенность|Достоверность)\*{0,2}\s*:\*{0,2}\s*(?:высокая|средняя|низкая)\*{0,2}[^\S\n]*\.?/gi, '')
    .replace(/\[РЕКОМЕНДАЦИЯ\]\s*/gi, '\n\n**Рекомендация:** ')
    .replace(/\*{0,2}Рекомендация\*{0,2}\s*:\*{0,2}\s*/gi, '\n\n**Рекомендация:** ')
    // These markers remain in the backend text for verified source tracking.
    .replace(/[ \t]*(?:\*{1,2})?\[Источник\s+[1-9]\d*\](?:\*{1,2})?/gi, '')
    .replace(/\n{3,}/g, '\n\n').trim());
}
