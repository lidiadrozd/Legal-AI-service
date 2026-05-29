import { TERMS_PARAGRAPHS } from '@/constants/site';
import { LegalTextPage } from './LegalTextPage';

export default function TermsPage() {
  return (
    <LegalTextPage
      title="Пользовательское соглашение"
      description="Условия использования сервиса ИИ-Юрист"
      paragraphs={TERMS_PARAGRAPHS}
    />
  );
}
