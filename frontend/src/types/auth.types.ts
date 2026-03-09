export type UserRole = 'user' | 'admin' | 'super_admin';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  is_consent_given: boolean;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  full_name: string;
  password: string;
}

export interface LoginResponse extends AuthTokens {
  user: User;
}

export interface ConsentRequest {
  consent_data_processing: boolean;
  consent_terms: boolean;
  consent_ai_usage: boolean;
}
