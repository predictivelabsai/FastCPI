#!/bin/bash
# Run all scrapers sequentially, load each into DB after scraping
# Target: 1000+ items per brand per site
set -e

cd "$(dirname "$0")/.."

PROVIDERS="autoscout24 autotrader mobile_de autohero theparking auto24_ee auto24_lt auto24_lv blocket collectingcars"

for provider in $PROVIDERS; do
    echo ""
    echo "=========================================="
    echo "  SCRAPING: $provider"
    echo "  Started: $(date)"
    echo "=========================================="

    python -m scripts.scrape_cars --provider "$provider" --headless 2>&1 || {
        echo "WARNING: $provider scrape failed, continuing..."
    }

    echo "Loading $provider into DB..."
    python -m scripts.scrape_cars --load --provider "$provider" 2>&1 || {
        echo "WARNING: $provider load failed, continuing..."
    }

    echo "$provider done at $(date)"
    echo ""
done

echo ""
echo "=========================================="
echo "  ALL SCRAPERS COMPLETE: $(date)"
echo "=========================================="

# Print final counts
python -c "
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
load_dotenv()
engine = create_engine(os.environ['DB_URL'])
with engine.connect() as conn:
    rows = conn.execute(text('''
        SELECT provider, make, COUNT(*) as cnt
        FROM carhero.car_listings
        GROUP BY provider, make
        ORDER BY provider, make
    ''')).fetchall()
    print(f'{\"Provider\":<15} {\"Make\":<20} {\"Count\":>8}')
    print('-' * 45)
    for r in rows:
        print(f'{r[0]:<15} {r[1]:<20} {r[2]:>8}')
"
