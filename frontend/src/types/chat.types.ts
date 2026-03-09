export type MessageRole = 'user' | 'assistant';
export type FeedbackRating = 'up' | 'down';

export interface Message {
  id: string;
  chat_id: string;
  role: MessageRole;
  content: string;
  tokens?: number;
  feedback?: FeedbackRating;
  attachments?: MessageAttachment[];
  created_at: string;
}

export interface MessageAttachment {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
}

export interface Chat {
  id: string;
  user_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface SendMessageRequest {
  chat_id: string;
  content: string;
  attachment_ids?: string[];
}

export interface CreateChatResponse {
  chat_id: string;
  title: string;
}

export interface FeedbackRequest {
  message_id: string;
  rating: FeedbackRating;
}
