-- CarHero database schema
-- Target: PostgreSQL 14+

CREATE SCHEMA IF NOT EXISTS carhero;

-- ─── Chat tables ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS carhero.chat_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    name VARCHAR(200),
    is_verified BOOLEAN DEFAULT FALSE,
    verify_token VARCHAR(64),
    reset_token VARCHAR(64),
    reset_token_expires TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS carhero.chat_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES carhero.chat_users(id),
    title VARCHAR(255) DEFAULT 'New chat',
    agent_slug VARCHAR(100),
    share_token VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS carhero.chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES carhero.chat_sessions(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    agent_slug VARCHAR(100),
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Car listing tables ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS carhero.car_listings (
    id SERIAL PRIMARY KEY,
    -- Identification
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    variant VARCHAR(200),
    generation VARCHAR(100),
    -- Pricing
    price_eur NUMERIC(12,2),
    price_original NUMERIC(12,2),
    currency VARCHAR(3) DEFAULT 'EUR',
    -- Specs
    year INTEGER,
    mileage_km INTEGER,
    fuel_type VARCHAR(50),
    transmission VARCHAR(50),
    body_type VARCHAR(50),
    engine_size_cc INTEGER,
    power_hp INTEGER,
    power_kw INTEGER,
    torque_nm INTEGER,
    -- Drivetrain
    drive_type VARCHAR(20),
    steering_side VARCHAR(5),
    gears INTEGER,
    -- Efficiency
    co2_grams INTEGER,
    fuel_consumption_l100km NUMERIC(4,1),
    emission_class VARCHAR(20),
    -- Body
    doors INTEGER,
    seats INTEGER,
    exterior_color VARCHAR(50),
    interior_color VARCHAR(50),
    interior_material VARCHAR(50),
    -- Condition
    condition VARCHAR(20) DEFAULT 'used',
    first_registration_date DATE,
    owners_count INTEGER,
    accident_free BOOLEAN,
    service_history BOOLEAN,
    -- Features
    features JSONB,
    equipment_packages JSONB,
    -- Listing metadata
    source_url VARCHAR(500) UNIQUE,
    provider VARCHAR(50) NOT NULL,
    country VARCHAR(5),
    city VARCHAR(100),
    seller_type VARCHAR(20),
    seller_name VARCHAR(200),
    listed_date DATE,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    -- Media
    image_urls JSONB,
    image_count INTEGER DEFAULT 0,
    -- Status
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS carhero.price_history (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES carhero.car_listings(id),
    price_eur NUMERIC(12,2),
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS carhero.car_models (
    id SERIAL PRIMARY KEY,
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    generation VARCHAR(100),
    body_type VARCHAR(50),
    production_start INTEGER,
    production_end INTEGER,
    segment VARCHAR(50),
    UNIQUE(make, model, generation)
);

CREATE TABLE IF NOT EXISTS carhero.market_snapshots (
    id SERIAL PRIMARY KEY,
    make VARCHAR(100),
    model VARCHAR(100),
    country VARCHAR(5),
    avg_price_eur NUMERIC(12,2),
    median_price_eur NUMERIC(12,2),
    listing_count INTEGER,
    avg_mileage_km INTEGER,
    avg_age_years NUMERIC(4,1),
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Deals table ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS carhero.deals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    cheapest_listing_id INTEGER REFERENCES carhero.car_listings(id),
    priciest_listing_id INTEGER REFERENCES carhero.car_listings(id),
    cheapest_price_eur NUMERIC(12,2),
    priciest_price_eur NUMERIC(12,2),
    savings_eur NUMERIC(12,2),
    savings_pct NUMERIC(5,1),
    cheapest_country VARCHAR(5),
    cheapest_provider VARCHAR(50),
    priciest_country VARCHAR(5),
    priciest_provider VARCHAR(50),
    listing_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(make, model)
);

-- ─── Investment Scores ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS carhero.investment_scores (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES carhero.car_listings(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 3),
    percentile NUMERIC(4,1),
    price_score INTEGER,
    mileage_score INTEGER,
    depreciation_score INTEGER,
    scarcity_score INTEGER,
    config_score INTEGER,
    strength_summary TEXT,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    snapshot_date DATE NOT NULL,
    UNIQUE(listing_id, snapshot_date)
);

-- ─── User features (Favorites, Saved Searches, Garage) ────────────────────

CREATE TABLE IF NOT EXISTS carhero.favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES carhero.chat_users(id) ON DELETE CASCADE,
    listing_id INTEGER NOT NULL REFERENCES carhero.car_listings(id) ON DELETE CASCADE,
    price_at_save NUMERIC(12,2),
    note VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS carhero.saved_searches (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES carhero.chat_users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    filters JSONB NOT NULL,
    last_viewed_at TIMESTAMPTZ DEFAULT NOW(),
    last_count INTEGER DEFAULT 0,
    notify_email BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS carhero.garage_cars (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES carhero.chat_users(id) ON DELETE CASCADE,
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    variant VARCHAR(200),
    year INTEGER NOT NULL,
    mileage_km INTEGER,
    purchase_price_eur NUMERIC(12,2),
    purchase_date DATE,
    fuel_type VARCHAR(50),
    fuel_consumption_l100km NUMERIC(4,1),
    annual_km INTEGER DEFAULT 15000,
    insurance_annual_eur NUMERIC(10,2) DEFAULT 1200,
    maintenance_annual_eur NUMERIC(10,2) DEFAULT 800,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── User Profiles / Preferences ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS carhero.user_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES carhero.chat_users(id) ON DELETE CASCADE UNIQUE,
    avatar_url VARCHAR(500),
    phone VARCHAR(30),
    country VARCHAR(5),
    city VARCHAR(100),
    currency VARCHAR(3) DEFAULT 'EUR',
    language VARCHAR(5) DEFAULT 'en',
    budget_min_eur NUMERIC(12,2),
    budget_max_eur NUMERIC(12,2),
    preferred_makes JSONB DEFAULT '[]',
    preferred_body_types JSONB DEFAULT '[]',
    preferred_fuel_types JSONB DEFAULT '[]',
    preferred_transmission VARCHAR(20),
    max_mileage_km INTEGER,
    min_year INTEGER,
    max_year INTEGER,
    notify_new_listings BOOLEAN DEFAULT TRUE,
    notify_price_drops BOOLEAN DEFAULT TRUE,
    notify_weekly_digest BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Indexes ────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_car_listings_make ON carhero.car_listings(make);
CREATE INDEX IF NOT EXISTS idx_car_listings_model ON carhero.car_listings(make, model);
CREATE INDEX IF NOT EXISTS idx_car_listings_provider ON carhero.car_listings(provider);
CREATE INDEX IF NOT EXISTS idx_car_listings_price ON carhero.car_listings(price_eur);
CREATE INDEX IF NOT EXISTS idx_car_listings_year ON carhero.car_listings(year);
CREATE INDEX IF NOT EXISTS idx_car_listings_country ON carhero.car_listings(country);
CREATE INDEX IF NOT EXISTS idx_car_listings_fuel ON carhero.car_listings(fuel_type);
CREATE INDEX IF NOT EXISTS idx_car_listings_status ON carhero.car_listings(status);
CREATE INDEX IF NOT EXISTS idx_price_history_listing ON carhero.price_history(listing_id);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_date ON carhero.market_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON carhero.chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON carhero.chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_deals_make_model ON carhero.deals(make, model);
CREATE INDEX IF NOT EXISTS idx_deals_status ON carhero.deals(status);
CREATE INDEX IF NOT EXISTS idx_inv_scores_listing ON carhero.investment_scores(listing_id);
CREATE INDEX IF NOT EXISTS idx_inv_scores_score ON carhero.investment_scores(score DESC);
CREATE INDEX IF NOT EXISTS idx_inv_scores_tier ON carhero.investment_scores(tier);
CREATE INDEX IF NOT EXISTS idx_inv_scores_date ON carhero.investment_scores(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON carhero.favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_listing ON carhero.favorites(listing_id);
CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON carhero.saved_searches(user_id);
CREATE INDEX IF NOT EXISTS idx_garage_cars_user ON carhero.garage_cars(user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_user ON carhero.user_profiles(user_id);
