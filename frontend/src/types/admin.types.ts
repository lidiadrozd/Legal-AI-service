import type { User } from './auth.types';
import type { FeedbackRating } from './chat.types';

export interface AdminUser extends User {
  chat_count: number;
  last_active?: string;
}

export interface AdminChat {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminFeedbackItem {
  id: string;
  message_id: string;
  message_preview: string;
  chat_id: string;
  user_id: string;
  user_email: string;
  rating: FeedbackRating;
  created_at: string;
}

export interface DashboardStats {
  total_users: number;
  total_chats: number;
  messages_today: number;
  avg_rating: number;
  active_users_today: number;
}

export interface DailyStatPoint {
  date: string;
  users: number;
  messages: number;
  tokens_used: number;
}

export interface AdminStats {
  summary: DashboardStats;
  daily: DailyStatPoint[];
}
