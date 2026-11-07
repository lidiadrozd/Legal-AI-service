import apiClient from './client';
import { startInterviewWithContextRecovery, type StartInterviewResult } from '@/utils/documentInterview';
import type {
  Document,
  DocumentPlaceholdersResponse,
  DocumentTemplateMeta,
  FillUploadedTemplateRequest,
  GenerateAiDocumentRequest,
  GenerateDocumentRequest,
  SuggestDocumentFieldsRequest,
  SuggestDocumentFieldsResponse,
  UploadDocumentResponse,
} from '@/types/document.types';

export const documentsApi = {
  startInterview: (payload: GenerateAiDocumentRequest): Promise<StartInterviewResult> =>
    startInterviewWithContextRecovery(payload, async (request) => {
      const response = await apiClient.post<StartInterviewResult>('/documents/interviews', request, { timeout: 300_000 });
      return response.data;
    }),

  getInterview: async (chatId: string): Promise<{ phase: string; scenario: string | null; document_title?: string; text_package?: unknown; unsupported_subject?: boolean }> => {
    const response = await apiClient.get(`/documents/interviews/${chatId}`);
    return response.data;
  },

  exportInterview: async (chatId: string): Promise<UploadDocumentResponse> => {
    const response = await apiClient.post<UploadDocumentResponse>(`/documents/interviews/${chatId}/export`);
    return response.data;
  },
  upload: async (
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<UploadDocumentResponse> => {
    const form = new FormData();
    form.append('file', file, file.name);

    const response = await apiClient.post<UploadDocumentResponse>('/documents/upload', form, {
      transformRequest: [
        (data, headers) => {
          delete headers['Content-Type'];
          return data;
        },
      ],
      onUploadProgress: (e) => {
        if (e.total && onProgress) {
          onProgress(Math.round((e.loaded * 100) / e.total));
        }
      },
    });
    return response.data;
  },

  generate: async (payload: GenerateDocumentRequest): Promise<UploadDocumentResponse> => {
    const response = await apiClient.post<UploadDocumentResponse>('/documents/generate', payload);
    return response.data;
  },

  generateAi: async (payload: GenerateAiDocumentRequest): Promise<UploadDocumentResponse> => {
    const response = await apiClient.post<UploadDocumentResponse>('/documents/generate-ai', payload);
    return response.data;
  },

  getPlaceholders: async (documentId: string): Promise<DocumentPlaceholdersResponse> => {
    const response = await apiClient.get<DocumentPlaceholdersResponse>(
      `/documents/${documentId}/placeholders`
    );
    return response.data;
  },

  fillUploadedTemplate: async (
    payload: FillUploadedTemplateRequest
  ): Promise<UploadDocumentResponse> => {
    const response = await apiClient.post<UploadDocumentResponse>(
      '/documents/fill-uploaded-template',
      payload
    );
    return response.data;
  },

  suggestFields: async (payload: SuggestDocumentFieldsRequest): Promise<SuggestDocumentFieldsResponse> => {
    const response = await apiClient.post<SuggestDocumentFieldsResponse>(
      '/documents/suggest-fields',
      payload
    );
    return response.data;
  },

  listTemplates: async (): Promise<DocumentTemplateMeta[]> => {
    const response = await apiClient.get<DocumentTemplateMeta[]>('/documents/templates');
    return response.data;
  },

  list: async (): Promise<Document[]> => {
    const response = await apiClient.get<Document[]>('/documents');
    return response.data;
  },

  getById: async (id: string): Promise<Document> => {
    const response = await apiClient.get<Document>(`/documents/${id}`);
    return response.data;
  },

  download: async (id: string, filename: string): Promise<void> => {
    const response = await apiClient.get(`/documents/${id}/download`, {
      responseType: 'blob',
      transformRequest: [
        (_data, headers) => {
          delete headers['Content-Type'];
          return undefined;
        },
      ],
    });

    const blob =
      response.data instanceof Blob ? response.data : new Blob([response.data]);

    if (blob.type.includes('application/json')) {
      const text = await blob.text();
      let msg = text;
      try {
        const parsed = JSON.parse(text) as { detail?: unknown };
        if (typeof parsed.detail === 'string') msg = parsed.detail;
        else if (Array.isArray(parsed.detail))
          msg = parsed.detail.map((d: unknown) => JSON.stringify(d)).join('; ');
      } catch {
        /* оставляем msg как текст ответа */
      }
      throw new Error(msg);
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'document';
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/documents/${id}`);
  },
};
