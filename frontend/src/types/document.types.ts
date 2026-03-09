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
  user_id: string;
  title: string;
  type: DocumentType;
  status: DocumentStatus;
  file_path?: string;
  file_size?: number;
  mime_type?: string;
  created_at: string;
  updated_at: string;
}

export interface UploadDocumentResponse {
  document_id: string;
  filename: string;
  status: DocumentStatus;
}
