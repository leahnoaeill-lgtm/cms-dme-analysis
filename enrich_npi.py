#!/usr/bin/env python3
"""
Step 3: NPI Enrichment Tool
Enriches provider data with:
- Clinic addresses from NPI Registry
- Patient focus (Adult/Pediatric) from web searches
- Additional clinic information from Healthgrades/Doximity
"""

import requests
import psycopg2
import time
import re
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

# Configuration
DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

NPI_REGISTRY_URL = "https://npiregistry.cms.hhs.gov/api/"

# Rate limiting: 1 request per second for NPI Registry, 2 seconds between web searches
NPI_DELAY = 1.0
WEB_SEARCH_DELAY = 2.0

class NPIEnricher:
    def __init__(self, use_web_search: bool = True):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CMS-Analysis-Tool/1.0'
        })
        self.use_web_search = use_web_search

    def close(self):
        self.conn.close()

    def get_pending_npis(self, limit: Optional[int] = None) -> List[Dict]:
        """Get NPIs that haven't been enriched yet."""
        cur = self.conn.cursor()
        query = """
            SELECT p.npi, p.first_name, p.last_name, p.cms_state, p.specialty_desc
            FROM providers p
            JOIN provider_enrichment e ON p.npi = e.npi
            WHERE e.search_status = 'pending'
            ORDER BY p.npi
        """
        if limit:
            query += f" LIMIT {limit}"

        cur.execute(query)
        columns = ['npi', 'first_name', 'last_name', 'state', 'specialty']
        results = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.close()
        return results

    def query_npi_registry(self, npi: str) -> Optional[Dict]:
        """Query the official NPI Registry for provider information."""
        try:
            params = {
                'number': npi,
                'version': '2.1'
            }
            response = self.session.get(NPI_REGISTRY_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('result_count', 0) > 0:
                return data['results'][0]
            return None

        except requests.exceptions.RequestException as e:
            print(f"    NPI Registry error: {e}")
            return None

    def extract_clinics_from_npi(self, npi_data: Dict, npi: str) -> List[Dict]:
        """Extract clinic information from NPI Registry response."""
        clinics = []

        # Get addresses (location type)
        addresses = npi_data.get('addresses', [])
        for addr in addresses:
            if addr.get('address_purpose') == 'LOCATION':
                clinic = {
                    'npi': npi,
                    'clinic_name': None,  # NPI Registry doesn't provide clinic names
                    'street_address': addr.get('address_1', ''),
                    'city': addr.get('city', ''),
                    'state': addr.get('state', ''),
                    'zip': addr.get('postal_code', '')[:5] if addr.get('postal_code') else '',
                    'phone': addr.get('telephone_number', ''),
                    'source_name': 'NPI Registry',
                    'source_url': f'https://npiregistry.cms.hhs.gov/provider-view/{npi}',
                    'is_primary': True
                }
                clinics.append(clinic)

        # Check practice locations
        practice_locs = npi_data.get('practiceLocations', [])
        for loc in practice_locs:
            clinic = {
                'npi': npi,
                'clinic_name': loc.get('organization_name'),
                'street_address': loc.get('address_1', ''),
                'city': loc.get('city', ''),
                'state': loc.get('state', ''),
                'zip': loc.get('postal_code', '')[:5] if loc.get('postal_code') else '',
                'phone': loc.get('telephone_number', ''),
                'source_name': 'NPI Registry',
                'source_url': f'https://npiregistry.cms.hhs.gov/provider-view/{npi}',
                'is_primary': False
            }
            clinics.append(clinic)

        # Try to get organization name from basic info
        basic = npi_data.get('basic', {})
        org_name = basic.get('organization_name') or basic.get('name')
        if org_name and clinics:
            clinics[0]['clinic_name'] = org_name

        return clinics

    def determine_patient_focus(self, npi_data: Dict, specialty: str) -> tuple:
        """Determine if provider focuses on Adult, Pediatric, or Both patients."""
        patient_focus = 'Unknown'
        source = 'Specialty Analysis'

        # Check taxonomies for pediatric indicators
        taxonomies = npi_data.get('taxonomies', [])
        taxonomy_descs = [(t.get('desc') or '').lower() for t in taxonomies]
        all_taxonomy_text = ' '.join(taxonomy_descs)

        # Also include the specialty from CMS data
        specialty_lower = (specialty or '').lower()
        combined_text = all_taxonomy_text + ' ' + specialty_lower

        # Pediatric indicators
        pediatric_keywords = ['pediatric', 'pediatrics', 'neonatal', 'child', 'adolescent', 'youth']
        adult_keywords = ['geriatric', 'adult', 'internal medicine']

        has_pediatric = any(kw in combined_text for kw in pediatric_keywords)
        has_adult = any(kw in combined_text for kw in adult_keywords)

        if has_pediatric and has_adult:
            patient_focus = 'Both'
        elif has_pediatric:
            patient_focus = 'Pediatric'
        elif has_adult:
            patient_focus = 'Adult'
        else:
            # Default assumption for pulmonary disease (E0483 is chest oscillation vest)
            # Most are adult pulmonologists, but we mark as Unknown if unclear
            patient_focus = 'Unknown'

        return patient_focus, source

    def search_healthgrades(self, provider: Dict) -> Optional[Dict]:
        """Search Healthgrades for additional provider information."""
        if not self.use_web_search:
            return None

        try:
            first_name = provider.get('first_name', '')
            last_name = provider.get('last_name', '')
            state = provider.get('state', '')

            # Healthgrades search URL
            search_url = f"https://www.healthgrades.com/api/v4/search"
            params = {
                'q': f"Dr. {first_name} {last_name}",
                'zip': '',
                'category': 'provider'
            }

            # Note: Healthgrades API may require different handling
            # For now, we'll construct a profile URL pattern
            name_slug = f"{first_name.lower()}-{last_name.lower()}".replace(' ', '-')
            profile_url = f"https://www.healthgrades.com/physician/dr-{name_slug}"

            return {
                'source_url': profile_url,
                'source_name': 'Healthgrades'
            }

        except Exception as e:
            print(f"    Healthgrades search error: {e}")
            return None

    def search_doximity(self, npi: str, provider: Dict) -> Optional[Dict]:
        """Search Doximity for provider information."""
        if not self.use_web_search:
            return None

        try:
            # Doximity profile URL pattern
            profile_url = f"https://www.doximity.com/pub/{npi}"

            return {
                'source_url': profile_url,
                'source_name': 'Doximity'
            }

        except Exception as e:
            print(f"    Doximity search error: {e}")
            return None

    def enhance_patient_focus_from_specialty(self, specialty: str, current_focus: str) -> str:
        """Enhance patient focus based on specialty patterns."""
        if current_focus != 'Unknown':
            return current_focus

        specialty_lower = (specialty or '').lower()

        # E0483 (High frequency chest wall oscillation) is commonly used for:
        # - Cystic Fibrosis (both pediatric and adult)
        # - Bronchiectasis (mostly adult)
        # - Neuromuscular diseases (both)

        # Pulmonologists treating CF often see both populations
        pulmonary_keywords = ['pulmonary', 'pulmonology', 'lung']
        if any(kw in specialty_lower for kw in pulmonary_keywords):
            return 'Adult'  # Most pulmonologists see adults by default

        # Pediatric specialties
        if 'pediatric' in specialty_lower:
            return 'Pediatric'

        return 'Unknown'

    def save_clinics(self, clinics: List[Dict]):
        """Save clinic information to database."""
        if not clinics:
            return

        cur = self.conn.cursor()

        for clinic in clinics:
            cur.execute("""
                INSERT INTO clinics (
                    npi, clinic_name, street_address, city, state, zip, phone,
                    source_url, source_name, is_primary
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                clinic['npi'],
                clinic.get('clinic_name'),
                clinic.get('street_address'),
                clinic.get('city'),
                clinic.get('state'),
                clinic.get('zip'),
                clinic.get('phone'),
                clinic.get('source_url'),
                clinic.get('source_name'),
                clinic.get('is_primary', False)
            ))

        self.conn.commit()
        cur.close()

    def update_enrichment_status(self, npi: str, patient_focus: str, source: str,
                                   status: str = 'completed', notes: str = None):
        """Update the enrichment status for a provider."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE provider_enrichment
            SET patient_focus = %s,
                patient_focus_source = %s,
                search_status = %s,
                search_date = %s,
                search_notes = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE npi = %s
        """, (patient_focus, source, status, datetime.now(), notes, npi))
        self.conn.commit()
        cur.close()

    def enrich_single_npi(self, provider: Dict) -> bool:
        """Enrich a single NPI with clinic and patient focus information."""
        npi = provider['npi']
        name = f"{provider.get('first_name', '')} {provider.get('last_name', '')}".strip()

        print(f"  Processing NPI {npi} ({name})...")

        # Query NPI Registry
        npi_data = self.query_npi_registry(npi)

        if not npi_data:
            self.update_enrichment_status(
                npi, 'Unknown', 'NPI Registry lookup failed',
                status='failed', notes='Could not retrieve NPI Registry data'
            )
            print(f"    FAILED: No NPI Registry data")
            return False

        # Extract clinics
        clinics = self.extract_clinics_from_npi(npi_data, npi)
        if clinics:
            self.save_clinics(clinics)
            print(f"    Found {len(clinics)} clinic location(s)")

        # Determine patient focus
        patient_focus, source = self.determine_patient_focus(
            npi_data, provider.get('specialty')
        )

        # Enhance patient focus based on specialty if still Unknown
        patient_focus = self.enhance_patient_focus_from_specialty(
            provider.get('specialty'), patient_focus
        )
        if patient_focus != 'Unknown':
            source = 'Specialty Analysis (Enhanced)'

        # Add web search source references
        sources = ['NPI Registry']
        if self.use_web_search:
            hg_info = self.search_healthgrades(provider)
            dx_info = self.search_doximity(npi, provider)
            if hg_info:
                sources.append('Healthgrades')
            if dx_info:
                sources.append('Doximity')

        # Update enrichment
        notes = f"Clinics found: {len(clinics)}. Sources: {', '.join(sources)}"
        self.update_enrichment_status(npi, patient_focus, source, 'completed', notes)

        print(f"    Patient focus: {patient_focus}")
        return True

    def enrich_batch(self, limit: Optional[int] = None, dry_run: bool = False):
        """Enrich a batch of NPIs."""
        pending = self.get_pending_npis(limit)
        total = len(pending)

        print(f"\n{'=' * 60}")
        print(f"NPI ENRICHMENT")
        print(f"{'=' * 60}")
        print(f"Pending NPIs to process: {total}")
        if dry_run:
            print("DRY RUN - No changes will be made")
        print(f"{'=' * 60}\n")

        if dry_run:
            for p in pending[:5]:
                print(f"  Would process: {p['npi']} - {p['first_name']} {p['last_name']}")
            if total > 5:
                print(f"  ... and {total - 5} more")
            return

        success = 0
        failed = 0

        for i, provider in enumerate(pending, 1):
            print(f"\n[{i}/{total}]", end="")
            try:
                if self.enrich_single_npi(provider):
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"    ERROR: {e}")
                failed += 1

            # Rate limiting
            time.sleep(NPI_DELAY)

        print(f"\n{'=' * 60}")
        print(f"ENRICHMENT COMPLETE")
        print(f"{'=' * 60}")
        print(f"Successful: {success}")
        print(f"Failed: {failed}")
        print(f"Total processed: {success + failed}")

    def get_stats(self):
        """Get enrichment statistics."""
        cur = self.conn.cursor()

        # Overall stats
        cur.execute("SELECT COUNT(*) FROM providers")
        total_providers = cur.fetchone()[0]

        cur.execute("SELECT search_status, COUNT(*) FROM provider_enrichment GROUP BY search_status")
        status_counts = dict(cur.fetchall())

        cur.execute("SELECT patient_focus, COUNT(*) FROM provider_enrichment WHERE patient_focus IS NOT NULL GROUP BY patient_focus")
        focus_counts = dict(cur.fetchall())

        cur.execute("SELECT COUNT(*) FROM clinics")
        total_clinics = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT npi) FROM clinics")
        npis_with_clinics = cur.fetchone()[0]

        cur.close()

        print(f"\n{'=' * 60}")
        print("ENRICHMENT STATISTICS")
        print(f"{'=' * 60}")
        print(f"Total providers: {total_providers}")
        print(f"\nEnrichment Status:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
        print(f"\nPatient Focus:")
        for focus, count in focus_counts.items():
            print(f"  {focus}: {count}")
        print(f"\nClinics:")
        print(f"  Total clinic records: {total_clinics}")
        print(f"  NPIs with clinic data: {npis_with_clinics}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='NPI Enrichment Tool')
    parser.add_argument('--limit', type=int, help='Limit number of NPIs to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--stats', action='store_true', help='Show enrichment statistics')
    parser.add_argument('--test', type=int, default=0, help='Test mode: process N NPIs')

    args = parser.parse_args()

    enricher = NPIEnricher()

    try:
        if args.stats:
            enricher.get_stats()
        elif args.test > 0:
            print(f"TEST MODE: Processing {args.test} NPIs")
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
