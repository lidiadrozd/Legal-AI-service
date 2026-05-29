import { useEffect } from 'react';

type PageMetaProps = {
  title?: string;
  description?: string;
};

export function PageMeta({ title, description }: PageMetaProps) {
  useEffect(() => {
    const base = 'ИИ-Юрист';
    document.title = title ? `${title} — ${base}` : base;
    if (description) {
      const el = document.querySelector('meta[name="description"]');
      if (el) el.setAttribute('content', description);
    }
    return () => {
      document.title = base;
    };
  }, [title, description]);

  return null;
}
