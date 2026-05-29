from pydantic import BaseModel, Field


class AdminUserRow(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    is_consent_given: bool
    created_at: str
    chat_count: int = 0
    tokens_used: int = 0
    cogs_rub: float = 0.0
    llm_requests: int = 0
    cache_hits: int = 0


class DashboardStats(BaseModel):
    total_users: int
    total_chats: int
    messages_today: int
    avg_rating: float
    active_users_today: int
    total_tokens: int = 0
    total_cogs_rub: float = 0.0
    cache_hits: int = 0


class DailyStatPoint(BaseModel):
    date: str
    users: int
    messages: int
    tokens_used: int
    cogs_rub: float = 0.0


class AdminStatsResponse(BaseModel):
    summary: DashboardStats
    daily: list[DailyStatPoint]


class UserCogsRow(BaseModel):
    user_id: str
    email: str
    full_name: str
    tokens_used: int
    cogs_rub: float
    llm_requests: int
    cache_hits: int


class CogsSummaryResponse(BaseModel):
    total_tokens: int
    total_cogs_rub: float
    llm_requests: int
    cache_hits: int
    price_per_1k_tokens: float = Field(description="Тариф COGS за 1000 токенов, ₽")
    users: list[UserCogsRow]
