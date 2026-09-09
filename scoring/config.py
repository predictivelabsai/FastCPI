"""Scoring weights, thresholds, and configuration."""

WEIGHTS = {
    "price": 0.35,
    "mileage": 0.20,
    "depreciation": 0.20,
    "scarcity": 0.15,
    "config": 0.10,
}

TIER_THRESHOLDS = {
    1: 80,
    2: 60,
}

DESIRABLE_TRANSMISSIONS = {"Automatic", "automatic", "Auto"}
DESIRABLE_FUELS = {"Petrol", "Hybrid", "Plugin Hybrid", "Electric"}
DESIRABLE_BODY_TYPES = {"SUV", "Estate", "Sedan", "Coupe", "Convertible"}

CONFIG_BONUSES = {
    "transmission_auto": 15,
    "fuel_desirable": 10,
    "body_desirable": 10,
    "accident_free": 15,
    "service_history": 10,
}

MIN_LISTINGS_FOR_BASELINE = 2
FALLBACK_AVG_MILEAGE = 80000
FALLBACK_AVG_PRICE = 30000
