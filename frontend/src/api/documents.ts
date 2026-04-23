import apiClient from './client';
import type {
  Document,
  DocumentTemplateMeta,
  GenerateDocumentRequest,
  SuggestDocumentFieldsRequest,
  SuggestDocumentFieldsResponse,
  UploadDocumentResponse,
} from '@/types/document.types';

export const documentsApi = {
  upload: async (
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<UploadDocumentResponse> => {
    const form = new FormData();
    form.append('file', file);

    const response = await apiClient.post<UploadDocumentResponse>('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
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
    });
    const url = URL.createObjectURL(new Blob([response.data]));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/documents/${id}`);
  },
};
