import apiClient from './client';

export interface TranscribeResponse {
  text: string;
  language: string;
}

export const speechApi = {
  transcribe: async (audioBlob: Blob, filename = 'recording.webm'): Promise<TranscribeResponse> => {
    const form = new FormData();
    form.append('audio', audioBlob, filename);

    const response = await apiClient.post<TranscribeResponse>('/speech/transcribe', form, {
      transformRequest: [
        (data, headers) => {
          delete headers['Content-Type'];
          return data;
        },
      ],
      timeout: 120_000,
    });
    return response.data;
  },
};
