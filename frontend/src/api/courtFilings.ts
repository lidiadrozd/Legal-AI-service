import apiClient from './client';

export interface CourtFilingSummary {
  id: number;
  case_number: string;
  court_name: string;
  claim_type: string;
}

export const courtFilingsApi = {
  list: async (): Promise<CourtFilingSummary[]> => {
    const response = await apiClient.get<CourtFilingSummary[]>('/court-filings/submissions');
    return response.data;
  },
};
