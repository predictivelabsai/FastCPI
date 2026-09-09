import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

DB_URL = os.environ["DB_URL"]
SCHEMA = "carhero"

engine = create_engine(DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)


@event.listens_for(engine, "connect")
def set_search_path(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute(f"SET search_path TO {SCHEMA}, public")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create schema and all tables."""
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    _init_chat_tables()
    _init_car_tables()


def _init_chat_tables():
    """Create chat tables if they don't exist."""
    ddl = [
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.chat_users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255),
            name VARCHAR(200),
            is_verified BOOLEAN DEFAULT FALSE,
            verify_token VARCHAR(64),
            reset_token VARCHAR(64),
            reset_token_expires TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.chat_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES {SCHEMA}.chat_users(id),
            title VARCHAR(255) DEFAULT 'New chat',
            agent_slug VARCHAR(100),
            share_token VARCHAR(64),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.chat_messages (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES {SCHEMA}.chat_sessions(id),
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            agent_slug VARCHAR(100),
            tool_calls JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
    ]
    alters = [
        f"ALTER TABLE {SCHEMA}.chat_users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        f"ALTER TABLE {SCHEMA}.chat_users ADD COLUMN IF NOT EXISTS name VARCHAR(200)",
        f"ALTER TABLE {SCHEMA}.chat_users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE",
        f"ALTER TABLE {SCHEMA}.chat_users ADD COLUMN IF NOT EXISTS verify_token VARCHAR(64)",
        f"ALTER TABLE {SCHEMA}.chat_users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(64)",
        f"ALTER TABLE {SCHEMA}.chat_users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMPTZ",
        f"ALTER TABLE {SCHEMA}.chat_users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'",
    ]
    invitations_ddl = f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.invitations (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        token VARCHAR(64) UNIQUE NOT NULL,
        invited_by INTEGER REFERENCES {SCHEMA}.chat_users(id),
        role VARCHAR(20) DEFAULT 'user',
        message TEXT,
        status VARCHAR(20) DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        expires_at TIMESTAMPTZ,
        accepted_at TIMESTAMPTZ
    )"""
    with engine.connect() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
        conn.execute(text(invitations_ddl))
        for stmt in alters:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
        # Ensure guest user (id=0) exists for unauthenticated mobile API access
        exists = conn.execute(text(f"SELECT 1 FROM {SCHEMA}.chat_users WHERE id = 0")).fetchone()
        if not exists:
            conn.execute(text(
                f"INSERT INTO {SCHEMA}.chat_users (id, email, name, password_hash) "
                f"VALUES (0, 'guest@carhero.chat', 'Guest', 'nologin')"
            ))
        # Seed admin user
        _seed_admin(conn)
        conn.commit()


def _seed_admin(conn):
    """Create the default admin user if it doesn't exist."""
    import bcrypt
    admin_email = "carehero.admin@predictivelabs.co.uk"
    admin_pw = "Autod2$2"
    exists = conn.execute(
        text(f"SELECT 1 FROM {SCHEMA}.chat_users WHERE email = :email"),
        {"email": admin_email},
    ).fetchone()
    if not exists:
        pw_hash = bcrypt.hashpw(admin_pw.encode(), bcrypt.gensalt()).decode()
        conn.execute(text(f"""
            INSERT INTO {SCHEMA}.chat_users (email, password_hash, name, is_verified, role)
            VALUES (:email, :pw, :name, TRUE, 'admin')
        """), {"email": admin_email, "pw": pw_hash, "name": "CarHero Admin"})
    else:
        conn.execute(
            text(f"UPDATE {SCHEMA}.chat_users SET role = 'admin' WHERE email = :email"),
            {"email": admin_email},
        )


def _init_car_tables():
    """Create car listing tables if they don't exist."""
    ddl = [
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.car_listings (
            id SERIAL PRIMARY KEY,
            make VARCHAR(100) NOT NULL,
            model VARCHAR(100) NOT NULL,
            variant VARCHAR(200),
            generation VARCHAR(100),
            price_eur NUMERIC(12,2),
            price_original NUMERIC(12,2),
            currency VARCHAR(3) DEFAULT 'EUR',
            year INTEGER,
            mileage_km INTEGER,
            fuel_type VARCHAR(50),
            transmission VARCHAR(50),
            body_type VARCHAR(50),
            engine_size_cc INTEGER,
            power_hp INTEGER,
            power_kw INTEGER,
            torque_nm INTEGER,
            drive_type VARCHAR(20),
            steering_side VARCHAR(5),
            gears INTEGER,
            co2_grams INTEGER,
            fuel_consumption_l100km NUMERIC(4,1),
            emission_class VARCHAR(20),
            doors INTEGER,
            seats INTEGER,
            exterior_color VARCHAR(50),
            interior_color VARCHAR(50),
            interior_material VARCHAR(50),
            condition VARCHAR(20) DEFAULT 'used',
            first_registration_date DATE,
            owners_count INTEGER,
            accident_free BOOLEAN,
            service_history BOOLEAN,
            features JSONB,
            equipment_packages JSONB,
            source_url VARCHAR(500) UNIQUE,
            provider VARCHAR(50) NOT NULL,
            country VARCHAR(5),
            city VARCHAR(100),
            seller_type VARCHAR(20),
            seller_name VARCHAR(200),
            listed_date DATE,
            scraped_at TIMESTAMPTZ DEFAULT NOW(),
            image_urls JSONB,
            image_count INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.price_history (
            id SERIAL PRIMARY KEY,
            listing_id INTEGER REFERENCES {SCHEMA}.car_listings(id),
            price_eur NUMERIC(12,2),
            recorded_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.car_models (
            id SERIAL PRIMARY KEY,
            make VARCHAR(100) NOT NULL,
            model VARCHAR(100) NOT NULL,
            generation VARCHAR(100),
            body_type VARCHAR(50),
            production_start INTEGER,
            production_end INTEGER,
            segment VARCHAR(50),
            UNIQUE(make, model, generation)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.market_snapshots (
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
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.deals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            make VARCHAR(100) NOT NULL,
            model VARCHAR(100) NOT NULL,
            cheapest_listing_id INTEGER REFERENCES {SCHEMA}.car_listings(id),
            priciest_listing_id INTEGER REFERENCES {SCHEMA}.car_listings(id),
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
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.investment_scores (
            id SERIAL PRIMARY KEY,
            listing_id INTEGER NOT NULL REFERENCES {SCHEMA}.car_listings(id) ON DELETE CASCADE,
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
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.favorites (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES {SCHEMA}.chat_users(id) ON DELETE CASCADE,
            listing_id INTEGER NOT NULL REFERENCES {SCHEMA}.car_listings(id) ON DELETE CASCADE,
            price_at_save NUMERIC(12,2),
            note VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, listing_id)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.saved_searches (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES {SCHEMA}.chat_users(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            filters JSONB NOT NULL,
            last_viewed_at TIMESTAMPTZ DEFAULT NOW(),
            last_count INTEGER DEFAULT 0,
            notify_email BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.garage_cars (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES {SCHEMA}.chat_users(id) ON DELETE CASCADE,
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
        )""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.user_profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES {SCHEMA}.chat_users(id) ON DELETE CASCADE UNIQUE,
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
        )""",
    ]
    indexes = [
        f"CREATE INDEX IF NOT EXISTS idx_car_listings_make ON {SCHEMA}.car_listings(make)",
        f"CREATE INDEX IF NOT EXISTS idx_car_listings_model ON {SCHEMA}.car_listings(make, model)",
        f"CREATE INDEX IF NOT EXISTS idx_car_listings_provider ON {SCHEMA}.car_listings(provider)",
        f"CREATE INDEX IF NOT EXISTS idx_car_listings_price ON {SCHEMA}.car_listings(price_eur)",
        f"CREATE INDEX IF NOT EXISTS idx_car_listings_year ON {SCHEMA}.car_listings(year)",
        f"CREATE INDEX IF NOT EXISTS idx_car_listings_country ON {SCHEMA}.car_listings(country)",
        f"CREATE INDEX IF NOT EXISTS idx_price_history_listing ON {SCHEMA}.price_history(listing_id)",
        f"CREATE INDEX IF NOT EXISTS idx_market_snapshots_date ON {SCHEMA}.market_snapshots(snapshot_date)",
        f"CREATE INDEX IF NOT EXISTS idx_deals_make_model ON {SCHEMA}.deals(make, model)",
        f"CREATE INDEX IF NOT EXISTS idx_deals_status ON {SCHEMA}.deals(status)",
        f"CREATE INDEX IF NOT EXISTS idx_inv_scores_listing ON {SCHEMA}.investment_scores(listing_id)",
        f"CREATE INDEX IF NOT EXISTS idx_inv_scores_score ON {SCHEMA}.investment_scores(score DESC)",
        f"CREATE INDEX IF NOT EXISTS idx_inv_scores_tier ON {SCHEMA}.investment_scores(tier)",
        f"CREATE INDEX IF NOT EXISTS idx_inv_scores_date ON {SCHEMA}.investment_scores(snapshot_date)",
        f"CREATE INDEX IF NOT EXISTS idx_favorites_user ON {SCHEMA}.favorites(user_id)",
        f"CREATE INDEX IF NOT EXISTS idx_favorites_listing ON {SCHEMA}.favorites(listing_id)",
        f"CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON {SCHEMA}.saved_searches(user_id)",
        f"CREATE INDEX IF NOT EXISTS idx_garage_cars_user ON {SCHEMA}.garage_cars(user_id)",
        f"CREATE INDEX IF NOT EXISTS idx_user_profiles_user ON {SCHEMA}.user_profiles(user_id)",
    ]
    alters = [
        f"ALTER TABLE {SCHEMA}.car_listings ADD COLUMN IF NOT EXISTS canonical_variant VARCHAR(200)",
    ]
    alter_indexes = [
        f"CREATE INDEX IF NOT EXISTS idx_car_listings_canonical_variant ON {SCHEMA}.car_listings(canonical_variant)",
    ]
    with engine.connect() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
        for stmt in indexes:
            conn.execute(text(stmt))
        for stmt in alters:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
        for stmt in alter_indexes:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
        conn.commit()
