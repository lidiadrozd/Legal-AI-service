export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'error';
export type DocumentType = 'upload' | 'generated' | 'template';
export type AllowedFileType = 'application/pdf' | 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' | 'text/plain';

export const ALLOWED_FILE_TYPES: AllowedFileType[] = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
];
export const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt'];
export const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20 МБ

export interface Document {
  id: string;
  user_id: number;
  title: string;
  type: DocumentType;
  status: DocumentStatus;
  file_path?: string;
  file_size?: number;
  mime_type?: string;
  generation_meta?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface UploadDocumentResponse {
  document_id: string;
  filename: string;
  status: DocumentStatus;
}

export interface GenerateDocumentRequest {
  template_key:
    | 'statement_of_claim_arbitration'
    | 'motion_to_postpone_hearing'
    | 'appeal_complaint';
  filename: string;
  fields: Record<string, string>;
  output_format: 'docx' | 'txt' | 'pdf';
  template_version?: number;
  chat_id?: number;
  court_filing_id?: number;
}

export interface DocumentTemplateField {
  key: string;
  label: string;
  multiline: boolean;
  pattern?: string | null;
}

export interface DocumentTemplateMeta {
  key: GenerateDocumentRequest['template_key'];
  version: number;
  title: string;
  description: string;
  fields: DocumentTemplateField[];
}

export interface SuggestDocumentFieldsRequest {
  template_key: GenerateDocumentRequest['template_key'];
  chat_id?: number;
  court_filing_id?: number;
}

export interface SuggestDocumentFieldsResponse {
  suggested: Record<string, string>;
  sources: Record<string, string>;
  template_version: number;
}
