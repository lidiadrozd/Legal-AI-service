const labels: Record<string, string> = {
  вид_документа: 'Вид документа', суд: 'Суд', истец: 'Заявитель', ответчик: 'Адресат',
  адрес_истца: 'Адрес заявителя', адрес_ответчика: 'Адрес адресата', номер_дела: 'Номер дела',
  дата: 'Дата', приложения: 'Приложения', подпись: 'Подпись',
  арендодатель: 'Арендодатель', арендатор: 'Арендатор',
};

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
  const levels: Record<string, string> = { high: 'высокая', medium: 'средняя', low: 'низкая' };
  return text.replace(/\bconfidence\s*[:=]\s*(high|medium|low)\b/gi,
    (_, level: string) => `\n\n**Уверенность:** ${levels[level.toLowerCase()]}`)
    .replace(/\[РЕКОМЕНДАЦИЯ\]\s*/gi, '\n\n**Рекомендация:** ')
    .replace(/\*{0,2}(?:Уверенность|Достоверность)\*{0,2}\s*:\*{0,2}\s*(высокая|средняя|низкая)/gi,
      (_, level: string) => `\n\n**Уверенность:** ${level.toLowerCase()}`)
    .replace(/\*{0,2}Рекомендация\*{0,2}\s*:\*{0,2}\s*/gi, '\n\n**Рекомендация:** ')
    // These markers remain in the backend text for verified source tracking.
    .replace(/[ \t]*(?:\*{1,2})?\[Источник\s+[1-9]\d*\](?:\*{1,2})?/gi, '')
    .replace(/\n{3,}/g, '\n\n').trim();
}
