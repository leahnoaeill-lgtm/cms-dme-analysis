#!/usr/bin/env python3
"""
Clinic Name Enrichment Tool
Searches OpenStreetMap (free) to find facility/clinic names for addresses.
No API key required.
"""

import requests
import psycopg2
import time
import re
from typing import Optional, List, Dict

# Configuration
DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

# OpenStreetMap APIs (free, no key required)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Rate limiting: Nominatim requires max 1 request/second
REQUEST_DELAY = 1.2  # seconds between requests


class ClinicNameEnricher:
    def __init__(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CMS-DME-Analysis-Tool/1.0 (medical research project)'
        })

    def close(self):
        self.conn.close()

    def get_clinics_without_names(self, limit: Optional[int] = None) -> List[Dict]:
        """Get clinics that don't have a facility name."""
        cur = self.conn.cursor()
        query = """
            SELECT c.id, c.npi, c.street_address, c.city, c.state, c.zip,
                   p.first_name, p.last_name, p.specialty_desc
            FROM clinics c
            JOIN providers p ON c.npi = p.npi
            WHERE c.clinic_name IS NULL OR c.clinic_name = ''
            ORDER BY c.id
        """
        if limit:
            query += f" LIMIT {limit}"

        cur.execute(query)
        columns = ['id', 'npi', 'street_address', 'city', 'state', 'zip',
                   'first_name', 'last_name', 'specialty']
        results = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        return results

    def geocode_address(self, address: str) -> Optional[Dict]:
        """Geocode an address to get coordinates using Nominatim."""
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

    def search_overpass_healthcare(self, lat: float, lon: float, radius: int = 100) -> Optional[str]:
        """Search Overpass API for healthcare facilities near coordinates."""
        try:
            # Query for healthcare facilities within radius
            query = f"""
            [out:json][timeout:25];
            (
              node["amenity"="hospital"](around:{radius},{lat},{lon});
              node["amenity"="clinic"](around:{radius},{lat},{lon});
              node["amenity"="doctors"](around:{radius},{lat},{lon});
              node["healthcare"](around:{radius},{lat},{lon});
              way["amenity"="hospital"](around:{radius},{lat},{lon});
              way["amenity"="clinic"](around:{radius},{lat},{lon});
              way["healthcare"](around:{radius},{lat},{lon});
            );
            out body;
            """

            response = self.session.post(OVERPASS_URL, data={'data': query}, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('elements'):
                # Find the closest one with a name
                for element in data['elements']:
                    tags = element.get('tags', {})
                    name = tags.get('name')
                    if name:
                        return name

            return None

        except Exception as e:
            print(f"    Overpass error: {e}")
            return None

    def search_nominatim_nearby(self, lat: float, lon: float) -> Optional[str]:
        """Use reverse geocoding to find nearby place name."""
        try:
            params = {
                'lat': lat,
                'lon': lon,
                'format': 'json',
                'zoom': 18,  # Building level
                'addressdetails': 1
            }
            response = self.session.get(NOMINATIM_REVERSE_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Check if it's a named place
            name = data.get('name')
            if name and not self._is_generic_name(name):
                return name

            # Check address details for building/amenity name
            address = data.get('address', {})
            for key in ['hospital', 'clinic', 'healthcare', 'building', 'amenity']:
                if key in address and not self._is_generic_name(address[key]):
                    return address[key]

            return None

        except Exception as e:
            print(f"    Reverse geocode error: {e}")
            return None

    def _is_generic_name(self, name: str) -> bool:
        """Check if a name is too generic to be useful."""
        if not name:
            return True
        generic = ['building', 'office', 'suite', 'floor', 'room', 'unit']
        return name.lower() in generic or len(name) < 3

    def construct_provider_name(self, clinic: Dict) -> str:
        """Construct a facility name from provider info as fallback."""
        first = clinic.get('first_name', '').strip()
        last = clinic.get('last_name', '').strip()
        specialty = clinic.get('specialty', '').strip()

        if last:
            # Common patterns for medical practices
            if specialty and 'pulmon' in specialty.lower():
                return f"{first} {last}, MD - Pulmonology" if first else f"Dr. {last} - Pulmonology"
            elif specialty:
                short_spec = specialty.split(',')[0].strip()[:30]
                return f"{first} {last}, MD" if first else f"Dr. {last}"
            else:
                return f"{first} {last}, MD" if first else f"Dr. {last}"
        return None

    def update_clinic_name(self, clinic_id: int, clinic_name: str, source: str = 'OpenStreetMap'):
        """Update the clinic name in the database."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE clinics
            SET clinic_name = %s,
                source_name = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (clinic_name, source, clinic_id))
        self.conn.commit()
        cur.close()

    def enrich_single_clinic(self, clinic: Dict) -> bool:
        """Enrich a single clinic with facility name."""
        clinic_id = clinic['id']
        address = f"{clinic['street_address']}, {clinic['city']}, {clinic['state']} {clinic['zip']}"

        facility_name = None
        source = None

        # Step 1: Geocode the address
        geo = self.geocode_address(address)

        if geo:
            time.sleep(REQUEST_DELAY)  # Rate limit

            # Step 2: Search Overpass for healthcare facilities
            facility_name = self.search_overpass_healthcare(geo['lat'], geo['lon'])
            if facility_name:
                source = 'OpenStreetMap (Overpass)'
            else:
                time.sleep(REQUEST_DELAY)
                # Step 3: Try reverse geocoding
                facility_name = self.search_nominatim_nearby(geo['lat'], geo['lon'])
                if facility_name:
                    source = 'OpenStreetMap (Nominatim)'

        # Step 4: Fallback to provider name
        if not facility_name:
            facility_name = self.construct_provider_name(clinic)
            if facility_name:
                source = 'Provider Name'

        if facility_name:
            self.update_clinic_name(clinic_id, facility_name, source)
            print(f"    Found: {facility_name} ({source})")
            return True
        else:
            print(f"    No facility found")
            return False

    def enrich_batch(self, limit: Optional[int] = None, dry_run: bool = False):
        """Enrich a batch of clinics with facility names."""
        clinics = self.get_clinics_without_names(limit)
        total = len(clinics)

        print(f"\n{'=' * 60}")
        print(f"CLINIC NAME ENRICHMENT (OpenStreetMap - Free)")
        print(f"{'=' * 60}")
        print(f"Clinics to process: {total}")
        print(f"Rate limit: ~{REQUEST_DELAY}s between requests")
        if dry_run:
            print("DRY RUN - No changes will be made")
        print(f"{'=' * 60}\n")

        if dry_run:
            for c in clinics[:5]:
                address = f"{c['street_address']}, {c['city']}, {c['state']} {c['zip']}"
                print(f"  Would search: {address}")
            if total > 5:
                print(f"  ... and {total - 5} more")
            return

        success = 0
        failed = 0

        for i, clinic in enumerate(clinics, 1):
            address = f"{clinic['street_address']}, {clinic['city']}, {clinic['state']}"
            print(f"\n[{i}/{total}] {address[:50]}...")

            try:
                if self.enrich_single_clinic(clinic):
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"    ERROR: {e}")
                failed += 1

            # Rate limiting between records
            time.sleep(REQUEST_DELAY)

        print(f"\n{'=' * 60}")
        print(f"ENRICHMENT COMPLETE")
        print(f"{'=' * 60}")
        print(f"Found facility names: {success}")
        print(f"No match (kept empty): {failed}")
        print(f"Total processed: {success + failed}")

    def get_stats(self):
        """Get clinic name enrichment statistics."""
        cur = self.conn.cursor()

        cur.execute("SELECT COUNT(*) FROM clinics")
        total_clinics = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM clinics WHERE clinic_name IS NOT NULL AND clinic_name != ''")
        with_names = cur.fetchone()[0]

        cur.execute("SELECT source_name, COUNT(*) FROM clinics WHERE clinic_name IS NOT NULL GROUP BY source_name")
        sources = dict(cur.fetchall())

        cur.close()

        print(f"\n{'=' * 60}")
        print("CLINIC NAME STATISTICS")
        print(f"{'=' * 60}")
        print(f"Total clinics: {total_clinics}")
        print(f"With facility names: {with_names}")
        print(f"Without names: {total_clinics - with_names}")
        if total_clinics > 0:
            print(f"Coverage: {with_names/total_clinics*100:.1f}%")
        if sources:
            print(f"\nBy source:")
            for src, count in sources.items():
                print(f"  {src}: {count}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Clinic Name Enrichment Tool (Free - OpenStreetMap)')
    parser.add_argument('--limit', type=int, help='Limit number of clinics to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--test', type=int, default=0, help='Test mode: process N clinics')

    args = parser.parse_args()

    enricher = ClinicNameEnricher()

    try:
        if args.stats:
            enricher.get_stats()
        elif args.test > 0:
            print(f"TEST MODE: Processing {args.test} clinics")
            enricher.enrich_batch(limit=args.test)
            enricher.get_stats()
        elif args.dry_run:
            enricher.enrich_batch(limit=args.limit, dry_run=True)
        else:
            enricher.enrich_batch(limit=args.limit)
            enricher.get_stats()
    finally:
        enricher.close()


if __name__ == "__main__":
    main()
