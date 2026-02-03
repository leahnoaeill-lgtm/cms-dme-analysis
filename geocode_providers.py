#!/usr/bin/env python3
"""
Provider Geocoding Tool
Geocodes provider addresses using Nominatim (OpenStreetMap).
No API key required. Rate limited to 1 request/second.

Usage:
    python3 geocode_providers.py              # Run geocoding
    python3 geocode_providers.py --stats      # Show progress stats
    python3 geocode_providers.py --limit 100  # Process only 100 providers
    python3 geocode_providers.py --state CA   # Process only California providers
"""

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import argparse
import sys
from typing import Optional, Dict

# Configuration
DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_DELAY = 1.1  # seconds between requests (Nominatim requires max 1/sec)


class ProviderGeocoder:
    def __init__(self):
        self.conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CMS-DME-Analysis-Tool/1.0 (medical research project)'
        })
        self.stats = {'success': 0, 'failed': 0, 'skipped': 0}

    def close(self):
        self.conn.close()

    def get_stats(self) -> Dict:
        """Get geocoding progress statistics."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                geocode_status,
                COUNT(*) as count
            FROM providers
            GROUP BY geocode_status
            ORDER BY geocode_status
        """)
        status_counts = {row['geocode_status'] or 'pending': row['count'] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) as total FROM providers")
        total = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) as geocoded FROM providers WHERE latitude IS NOT NULL")
        geocoded = cur.fetchone()['geocoded']

        cur.close()
        return {
            'total': total,
            'geocoded': geocoded,
            'pending': status_counts.get('pending', 0),
            'completed': status_counts.get('completed', 0),
            'failed': status_counts.get('failed', 0),
            'percent_complete': round(geocoded / total * 100, 1) if total > 0 else 0
        }

    def get_pending_providers(self, limit: Optional[int] = None, state: Optional[str] = None):
        """Get providers that haven't been geocoded yet."""
        cur = self.conn.cursor()

        where_clauses = ["(geocode_status IS NULL OR geocode_status = 'pending')"]
        params = []

        if state:
            where_clauses.append("cms_state = %s")
            params.append(state.upper())

        query = f"""
            SELECT npi, cms_street1, cms_street2, cms_city, cms_state, cms_zip
            FROM providers
            WHERE {' AND '.join(where_clauses)}
            ORDER BY npi
        """
        if limit:
            query += f" LIMIT {limit}"

        cur.execute(query, params)
        providers = cur.fetchall()
        cur.close()
        return providers

    def build_address(self, provider: Dict) -> str:
        """Build a geocodable address string from provider fields."""
        parts = []
        if provider.get('cms_street1'):
            parts.append(provider['cms_street1'])
        if provider.get('cms_city'):
            parts.append(provider['cms_city'])
        if provider.get('cms_state'):
            parts.append(provider['cms_state'])
        if provider.get('cms_zip'):
            # Use just the 5-digit zip
            zip_code = str(provider['cms_zip'])[:5]
            parts.append(zip_code)
        return ', '.join(parts)

    def geocode_address(self, address: str) -> Optional[Dict]:
        """Geocode an address using Nominatim."""
        try:
            params = {
                'q': address,
                'format': 'json',
                'limit': 1,
                'countrycodes': 'us'
            }
            response = self.session.get(NOMINATIM_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data:
                return {
                    'lat': float(data[0]['lat']),
                    'lon': float(data[0]['lon']),
                    'display_name': data[0].get('display_name', '')
                }
            return None

        except Exception as e:
            print(f"    Geocoding error: {e}")
            return None

    def update_provider_geocode(self, npi: str, lat: float, lon: float, status: str = 'completed'):
        """Update provider with geocoded coordinates."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE providers
            SET latitude = %s, longitude = %s, geocode_status = %s, updated_at = NOW()
            WHERE npi = %s
        """, [lat, lon, status, npi])
        self.conn.commit()
        cur.close()

    def mark_failed(self, npi: str):
        """Mark provider geocoding as failed."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE providers
            SET geocode_status = 'failed', updated_at = NOW()
            WHERE npi = %s
        """, [npi])
        self.conn.commit()
        cur.close()

    def process_providers(self, limit: Optional[int] = None, state: Optional[str] = None):
        """Process all pending providers."""
        providers = self.get_pending_providers(limit=limit, state=state)
        total = len(providers)

        if total == 0:
            print("No pending providers to geocode.")
            return

        print(f"Processing {total} providers...")
        print("-" * 60)

        for i, provider in enumerate(providers, 1):
            npi = provider['npi']
            address = self.build_address(provider)

            if not address or len(address) < 10:
                print(f"[{i}/{total}] NPI {npi}: Skipping - insufficient address data")
                self.mark_failed(npi)
                self.stats['skipped'] += 1
                continue

            print(f"[{i}/{total}] NPI {npi}: {address[:50]}...")

            result = self.geocode_address(address)

            if result:
                self.update_provider_geocode(npi, result['lat'], result['lon'])
                print(f"    -> ({result['lat']:.4f}, {result['lon']:.4f})")
                self.stats['success'] += 1
            else:
                # Try with just city, state, zip (less specific but better than nothing)
                fallback_address = f"{provider.get('cms_city', '')}, {provider.get('cms_state', '')} {str(provider.get('cms_zip', ''))[:5]}"
                print(f"    Trying fallback: {fallback_address}")
                time.sleep(REQUEST_DELAY)

                result = self.geocode_address(fallback_address)
                if result:
                    self.update_provider_geocode(npi, result['lat'], result['lon'])
                    print(f"    -> ({result['lat']:.4f}, {result['lon']:.4f}) [fallback]")
                    self.stats['success'] += 1
                else:
                    self.mark_failed(npi)
                    print(f"    -> FAILED")
                    self.stats['failed'] += 1

            # Rate limiting
            time.sleep(REQUEST_DELAY)

            # Progress update every 100
            if i % 100 == 0:
                print(f"\n--- Progress: {i}/{total} ({i/total*100:.1f}%) ---")
                print(f"    Success: {self.stats['success']}, Failed: {self.stats['failed']}, Skipped: {self.stats['skipped']}")
                print()

        print("\n" + "=" * 60)
        print("GEOCODING COMPLETE")
        print(f"  Success: {self.stats['success']}")
        print(f"  Failed:  {self.stats['failed']}")
        print(f"  Skipped: {self.stats['skipped']}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Geocode provider addresses')
    parser.add_argument('--stats', action='store_true', help='Show geocoding statistics')
    parser.add_argument('--limit', type=int, help='Limit number of providers to process')
    parser.add_argument('--state', type=str, help='Process only providers in this state (e.g., CA)')
    args = parser.parse_args()

    geocoder = ProviderGeocoder()

    try:
        if args.stats:
            stats = geocoder.get_stats()
            print("\n" + "=" * 50)
            print("PROVIDER GEOCODING STATUS")
            print("=" * 50)
            print(f"  Total providers:    {stats['total']:,}")
            print(f"  Geocoded:           {stats['geocoded']:,}")
            print(f"  Pending:            {stats['pending']:,}")
            print(f"  Completed:          {stats['completed']:,}")
            print(f"  Failed:             {stats['failed']:,}")
            print(f"  Progress:           {stats['percent_complete']}%")
            print("=" * 50)

            if stats['pending'] > 0:
                est_hours = stats['pending'] * REQUEST_DELAY / 3600
                print(f"\nEstimated time to complete: {est_hours:.1f} hours")
        else:
            geocoder.process_providers(limit=args.limit, state=args.state)
    finally:
        geocoder.close()


if __name__ == '__main__':
    main()
