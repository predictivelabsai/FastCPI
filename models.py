from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, DateTime, Text, JSON,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from db import Base, SCHEMA


class CarListing(Base):
    __tablename__ = "car_listings"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True)
    make = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False)
    variant = Column(String(200))
    generation = Column(String(100))

    price_eur = Column(Numeric(12, 2))
    price_original = Column(Numeric(12, 2))
    currency = Column(String(3), default="EUR")

    year = Column(Integer)
    mileage_km = Column(Integer)
    fuel_type = Column(String(50))
    transmission = Column(String(50))
    body_type = Column(String(50))
    engine_size_cc = Column(Integer)
    power_hp = Column(Integer)
    power_kw = Column(Integer)
    torque_nm = Column(Integer)

    drive_type = Column(String(20))
    steering_side = Column(String(5))
    gears = Column(Integer)

    co2_grams = Column(Integer)
    fuel_consumption_l100km = Column(Numeric(4, 1))
    emission_class = Column(String(20))

    doors = Column(Integer)
    seats = Column(Integer)
    exterior_color = Column(String(50))
    interior_color = Column(String(50))
    interior_material = Column(String(50))

    condition = Column(String(20), default="used")
    first_registration_date = Column(Date)
    owners_count = Column(Integer)
    accident_free = Column(Boolean)
    service_history = Column(Boolean)

    features = Column(JSON)
    equipment_packages = Column(JSON)

    source_url = Column(String(500), unique=True)
    provider = Column(String(50), nullable=False, index=True)
    country = Column(String(5))
    city = Column(String(100))
    seller_type = Column(String(20))
    seller_name = Column(String(200))
    listed_date = Column(Date)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    image_urls = Column(JSON)
    image_count = Column(Integer, default=0)

    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    price_history = relationship("PriceHistory", back_populates="listing")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey(f"{SCHEMA}.car_listings.id"))
    price_eur = Column(Numeric(12, 2))
    recorded_at = Column(DateTime, default=datetime.utcnow)

    listing = relationship("CarListing", back_populates="price_history")


class CarModel(Base):
    __tablename__ = "car_models"
    __table_args__ = (
        UniqueConstraint("make", "model", "generation"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, primary_key=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    generation = Column(String(100))
    body_type = Column(String(50))
    production_start = Column(Integer)
    production_end = Column(Integer)
    segment = Column(String(50))


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True)
    make = Column(String(100))
    model = Column(String(100))
    country = Column(String(5))
    avg_price_eur = Column(Numeric(12, 2))
    median_price_eur = Column(Numeric(12, 2))
    listing_count = Column(Integer)
    avg_mileage_km = Column(Integer)
    avg_age_years = Column(Numeric(4, 1))
    snapshot_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
