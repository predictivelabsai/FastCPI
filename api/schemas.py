"""Pydantic models for API request/response validation."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    name: str = ""

class AuthResponse(BaseModel):
    token: str
    email: str
    name: str = ""
    user_id: int

class UserInfo(BaseModel):
    user_id: int
    email: str
    name: str = ""


# ── Chat ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: int | None = None
    lang: str = "en"

class SessionSummary(BaseModel):
    id: int
    title: str
    agent_slug: str | None = None
    updated_at: str

class MessageOut(BaseModel):
    role: str
    content: str
    agent_slug: str | None = None

class SessionDetail(BaseModel):
    id: int
    title: str
    agent_slug: str | None = None
    messages: list[MessageOut]

class ShareResponse(BaseModel):
    token: str
    url: str

class SharedSessionOut(BaseModel):
    title: str
    agent_slug: str | None = None
    messages: list[MessageOut]


# ── Agents ────────────────────────────────────────────────────────────

class AgentOut(BaseModel):
    slug: str
    name: str
    category: str
    icon: str
    one_liner: str
    prefix: str
    example_prompts: list[str]


# ── Favorites ─────────────────────────────────────────────────────────

class FavoriteOut(BaseModel):
    id: int
    listing_id: int
    make: str
    model: str
    variant: str = ""
    year: int | None = None
    mileage_km: int | None = None
    price_eur: int | None = None
    price_at_save: int | None = None
    price_change: int | None = None
    fuel_type: str = ""
    transmission: str = ""
    country: str = ""
    provider: str = ""
    url: str = ""
    note: str = ""

class AddFavoriteRequest(BaseModel):
    listing_id: int

class UpdateNoteRequest(BaseModel):
    note: str = ""


# ── Saved Searches ────────────────────────────────────────────────────

class SavedSearchOut(BaseModel):
    id: int
    name: str
    filters: dict
    last_count: int = 0
    notify_email: bool = False
    created_at: str

class CreateSearchRequest(BaseModel):
    name: str = "Untitled Search"
    filters: dict = {}
    notify_email: bool = False


# ── Garage ────────────────────────────────────────────────────────────

class GarageCarOut(BaseModel):
    id: int
    make: str
    model: str
    variant: str = ""
    year: int
    mileage_km: int | None = None
    purchase_price_eur: float | None = None
    fuel_type: str = ""
    estimated_value: int | None = None
    comparable_count: int = 0

class AddGarageCarRequest(BaseModel):
    make: str
    model: str
    variant: str = ""
    year: int
    mileage_km: int | None = None
    purchase_price_eur: float | None = None
    purchase_date: str | None = None
    fuel_type: str | None = None
    fuel_consumption_l100km: float | None = None
    annual_km: int = 15000
    insurance_annual_eur: float = 1200
    maintenance_annual_eur: float = 800

class ValuationOut(BaseModel):
    estimated_value: int | None = None
    comparable_count: int = 0
    avg_price: int | None = None
    median_price: int | None = None
    min_price: int | None = None
    max_price: int | None = None
    avg_mileage: int | None = None

class TcoOut(BaseModel):
    fuel_annual_eur: int
    insurance_annual_eur: int
    maintenance_annual_eur: int
    depreciation_annual_eur: int
    total_annual_eur: int
    total_monthly_eur: int
    cost_per_km_eur: float
    current_market_value_eur: int | None = None
    valuation: ValuationOut | None = None


# ── Profile ───────────────────────────────────────────────────────────

class UserProfileOut(BaseModel):
    name: str = ""
    email: str
    phone: str = ""
    country: str = ""
    city: str = ""
    currency: str = "EUR"
    language: str = "en"
    budget_min_eur: float | None = None
    budget_max_eur: float | None = None
    preferred_makes: list[str] = []
    preferred_body_types: list[str] = []
    preferred_fuel_types: list[str] = []
    preferred_transmission: str | None = None
    max_mileage_km: int | None = None
    min_year: int | None = None
    max_year: int | None = None
    notify_new_listings: bool = True
    notify_price_drops: bool = True
    notify_weekly_digest: bool = True

class UpdateProfileRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    country: str | None = None
    city: str | None = None
    currency: str | None = None
    language: str | None = None
    budget_min_eur: float | None = None
    budget_max_eur: float | None = None
    preferred_makes: list[str] | None = None
    preferred_body_types: list[str] | None = None
    preferred_fuel_types: list[str] | None = None
    preferred_transmission: str | None = None
    max_mileage_km: int | None = None
    min_year: int | None = None
    max_year: int | None = None
    notify_new_listings: bool | None = None
    notify_price_drops: bool | None = None
    notify_weekly_digest: bool | None = None


# ── Listings ──────────────────────────────────────────────────────────

class ListingOut(BaseModel):
    id: int
    make: str
    model: str
    variant: str = ""
    year: int | None = None
    price_eur: float | None = None
    mileage_km: int | None = None
    fuel_type: str = ""
    transmission: str = ""
    body_type: str = ""
    power_hp: int | None = None
    country: str = ""
    provider: str = ""
    source_url: str = ""
    image_urls: list[str] | None = None
    investment_score: int | None = None
    tier: int | None = None


# ── Analytics ─────────────────────────────────────────────────────────

class AnalyticsRequest(BaseModel):
    question: str

class AnalyticsResponse(BaseModel):
    sql: str
    title: str
    data: list[dict] | None = None
    chart_type: str | None = None
    x_column: str | None = None
    y_column: str | None = None
    color_column: str | None = None
    rows: int = 0


# ── Contact ───────────────────────────────────────────────────────────

class ContactRequest(BaseModel):
    name: str
    email: str
    message: str
