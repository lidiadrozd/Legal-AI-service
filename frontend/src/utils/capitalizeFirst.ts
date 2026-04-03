/**
 * Первая буква в строке (Unicode) — заглавная; остальной текст без изменений.
 */
export function capitalizeFirstLetter(text: string): string {
  const s = text.trim();
  if (!s) return '';
  const chars = [...s];
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    if (/\p{L}/u.test(ch)) {
      chars[i] = ch.toLocaleUpperCase('ru-RU');
      break;
    }
  }
  return chars.join('');
}

/** Имя файла: первая буква основы (до последней точки) — заглавная, расширение как есть. */
export function capitalizeFilename(filename: string): string {
  const s = filename.trim();
  if (!s) return '';
  const lastDot = s.lastIndexOf('.');
  if (lastDot <= 0 || lastDot === s.length - 1) {
    return capitalizeFirstLetter(s);
  }
  const stem = s.slice(0, lastDot);
  const ext = s.slice(lastDot);
  return capitalizeFirstLetter(stem) + ext;
}
