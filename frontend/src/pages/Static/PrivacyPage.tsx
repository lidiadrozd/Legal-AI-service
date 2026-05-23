import { CONSENT_PARAGRAPHS } from '@/constants/site';
import { LegalTextPage } from './LegalTextPage';

export default function PrivacyPage() {
  return (
    <LegalTextPage
      title="Политика конфиденциальности"
      description="Политика обработки персональных данных сервиса ИИ-Юрист"
      paragraphs={CONSENT_PARAGRAPHS}
    />
  );
}
