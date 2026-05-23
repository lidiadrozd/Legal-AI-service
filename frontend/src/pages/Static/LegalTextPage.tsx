import styled from 'styled-components';
import { PageMeta } from '@/components/common/PageMeta';

const Title = styled.h1`
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 24px;
`;

const Paragraph = styled.p`
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.75;
  margin: 0 0 16px;
`;

type LegalTextPageProps = {
  title: string;
  description: string;
  paragraphs: string[];
};

export function LegalTextPage({ title, description, paragraphs }: LegalTextPageProps) {
  return (
    <>
      <PageMeta title={title} description={description} />
      <Title>{title}</Title>
      {paragraphs.map((text, i) => (
        <Paragraph key={i}>{text}</Paragraph>
      ))}
    </>
  );
}
