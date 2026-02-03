#!/usr/bin/env python3
"""
Enrich provider conditions by searching physician directories and websites.
Looks for conditions treated with High Frequency Chest Wall Oscillation (E0483).
"""

import psycopg2
import psycopg2.extras
import requests
import time
import re
import argparse
from urllib.parse import quote_plus

# Database configuration
DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

# Condition keywords mapping - more comprehensive
CONDITION_KEYWORDS = {
    'ALS': [
        'als', 'amyotrophic lateral sclerosis', 'lou gehrig', 'motor neuron disease',
        'als clinic', 'als center', 'als program', 'mnd'
    ],
    'MD': [
        'muscular dystrophy', 'duchenne', 'becker dystrophy', 'myotonic dystrophy',
        'facioscapulohumeral', 'limb-girdle', 'neuromuscular disease', 'neuromuscular disorder',
        'mda clinic', 'muscular dystrophy association'
    ],
    'SCI': [
        'spinal cord injury', 'spinal cord injuries', 'paralysis', 'paraplegia',
        'quadriplegia', 'tetraplegia', 'spinal injury', 'sci clinic', 'sci center',
        'rehabilitation medicine', 'physiatry'
    ],
    'SMA': [
        'spinal muscular atrophy', 'sma type', 'sma1', 'sma2', 'sma3', 'sma4',
        'sma clinic', 'sma program'
    ],
    'BRONCH': [
        'bronchiectasis', 'bronchial dilation', 'chronic bronchial', 'non-cf bronchiectasis',
        'primary ciliary dyskinesia', 'pcd', 'kartagener'
    ],
    'COPD': [
        'copd', 'chronic obstructive pulmonary', 'emphysema', 'chronic bronchitis',
        'copd clinic', 'copd program', 'pulmonary rehabilitation'
    ],
    'CF': [
        'cystic fibrosis', 'cf patient', 'cf clinic', 'cf center', 'cf foundation',
        'cf care', 'cystic fibrosis foundation', 'cff accredited'
    ]
}

# Specialty-based condition inference
SPECIALTY_CONDITION_MAP = {
    # Pediatric specialties often treat CF, SMA, MD
    'pediatric pulmonology': ['CF', 'SMA', 'MD'],
    'pediatric pulmonary': ['CF', 'SMA', 'MD'],
    'pediatric respiratory': ['CF', 'SMA', 'MD'],
    'pediatric critical care': ['CF', 'SMA', 'MD'],
    'neonatal': ['CF', 'SMA'],
    'pediatric neurology': ['SMA', 'MD', 'ALS'],

    # Adult pulmonology
    'pulmonology': ['COPD', 'BRONCH', 'CF'],
    'pulmonary disease': ['COPD', 'BRONCH', 'CF'],
    'pulmonary medicine': ['COPD', 'BRONCH', 'CF'],
    'respiratory': ['COPD', 'BRONCH'],
    'critical care': ['COPD', 'BRONCH'],

    # Neurology
    'neurology': ['ALS', 'MD', 'SMA'],
    'neuromuscular': ['ALS', 'MD', 'SMA'],

    # Rehabilitation
    'physical medicine': ['SCI', 'ALS', 'MD'],
    'rehabilitation': ['SCI', 'ALS', 'MD'],
    'physiatry': ['SCI'],
}

# Headers for web requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

def get_db_connection():
    """Get database connection."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def search_healthgrades(name, city, state):
    """Search Healthgrades for provider profile."""
    # Format name for URL
    name_parts = name.lower().split()
    if len(name_parts) >= 2:
        search_name = f"{name_parts[0]}-{name_parts[-1]}"
    else:
        search_name = name.lower().replace(' ', '-')

    # Try Healthgrades search
    url = f"https://www.healthgrades.com/search?what={quote_plus(name)}&where={quote_plus(f'{city}, {state}')}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text.lower()
    except Exception as e:
        pass

    return ""

def search_webmd(name, state):
    """Search WebMD physician directory."""
    url = f"https://doctor.webmd.com/results?so=&ln={quote_plus(name)}&state={state}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text.lower()
    except Exception as e:
        pass

    return ""

def search_google_scholar(name):
    """Search Google Scholar for published research (indicates specialty)."""
    conditions_query = "cystic fibrosis OR ALS OR muscular dystrophy OR COPD OR bronchiectasis"
    url = f"https://scholar.google.com/scholar?q={quote_plus(name)}+{quote_plus(conditions_query)}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text.lower()
    except Exception as e:
        pass

    return ""

def search_npi_registry(npi):
    """Search NPI Registry for detailed taxonomy info."""
    url = f"https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('result_count', 0) > 0:
                result = data['results'][0]

                # Get all taxonomy descriptions
                taxonomies = result.get('taxonomies', [])
                taxonomy_text = ' '.join([
                    f"{t.get('desc', '')} {t.get('license', '')}"
                    for t in taxonomies
                ]).lower()

                # Get practice address info
                addresses = result.get('addresses', [])
                address_text = ' '.join([
                    f"{a.get('organization_name', '')} {a.get('address_1', '')}"
                    for a in addresses
                ]).lower()

                return taxonomy_text + ' ' + address_text
    except Exception as e:
        pass

    return ""

def search_duckduckgo_targeted(name, city, state, condition_focus=None):
    """
    Targeted DuckDuckGo search for specific conditions.
    """
    if condition_focus:
        query = f'"{name}" {city} {state} {condition_focus} clinic center treatment'
    else:
        query = f'"{name}" {city} {state} pulmonologist respiratory cystic fibrosis COPD ALS'

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text.lower()
    except Exception as e:
        pass

    return ""

def infer_from_specialty(specialty_desc):
    """Infer likely conditions from provider's medical specialty."""
    if not specialty_desc:
        return []

    specialty_lower = specialty_desc.lower()
    inferred = []

    for specialty_pattern, conditions in SPECIALTY_CONDITION_MAP.items():
        if specialty_pattern in specialty_lower:
            for cond in conditions:
                if cond not in inferred:
                    inferred.append(cond)

    return inferred

def detect_conditions(text, require_context=False):
    """
    Detect conditions mentioned in the text.
    If require_context=True, only count if near treatment-related words.
    """
    if not text:
        return []

    text = text.lower()
    found_conditions = []

    # Context words that indicate the provider actually treats this condition
    context_words = [
        'treats', 'treating', 'specializes', 'specializing', 'specialist',
        'expertise', 'focus', 'patients', 'clinic', 'center', 'program',
        'care', 'therapy', 'treatment', 'diagnosis', 'experience'
    ]

    for condition_code, keywords in CONDITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                if require_context:
                    # Check if keyword appears near context words (within 100 chars)
                    keyword_pos = text.find(keyword)
                    context_window = text[max(0, keyword_pos-100):keyword_pos+len(keyword)+100]
                    has_context = any(ctx in context_window for ctx in context_words)
                    if has_context and condition_code not in found_conditions:
                        found_conditions.append(condition_code)
                else:
                    if condition_code not in found_conditions:
                        found_conditions.append(condition_code)
                break

    return found_conditions

def get_condition_ids(cur, condition_codes):
    """Get condition IDs from codes."""
    if not condition_codes:
        return []

    placeholders = ','.join(['%s'] * len(condition_codes))
    cur.execute(f"""
        SELECT id, code FROM condition_types WHERE code IN ({placeholders})
    """, condition_codes)

    return [row['id'] for row in cur.fetchall()]

def enrich_provider(cur, provider, use_other_default=True):
    """
    Enrich a single provider with condition information.
    Uses multiple sources and specialty inference.
    """
    npi = provider['npi']
    name = f"{provider.get('first_name', '')} {provider.get('last_name', '')}".strip()
    city = provider.get('cms_city', '')
    state = provider.get('cms_state', '')
    specialty = provider.get('specialty_desc', '')

    print(f"  Searching for {name} (NPI: {npi}, {specialty or 'No specialty'})...")

    all_conditions = []
    all_text = ""

    # 1. Infer from existing specialty
    inferred = infer_from_specialty(specialty)
    if inferred:
        print(f"    Inferred from specialty: {', '.join(inferred)}")
        all_conditions.extend(inferred)

    # 2. Search NPI Registry for detailed taxonomy (trusted source, no context needed)
    print(f"    Checking NPI Registry...")
    npi_text = search_npi_registry(npi)
    all_text += " " + npi_text
    npi_conditions = detect_conditions(npi_text, require_context=False)
    if npi_conditions:
        print(f"    From NPI Registry: {', '.join(npi_conditions)}")
        all_conditions.extend(npi_conditions)
    time.sleep(0.5)

    # 3. Search Healthgrades (require context to avoid false positives)
    print(f"    Checking Healthgrades...")
    hg_text = search_healthgrades(name, city, state)
    all_text += " " + hg_text
    hg_conditions = detect_conditions(hg_text, require_context=True)
    if hg_conditions:
        print(f"    From Healthgrades: {', '.join(hg_conditions)}")
        all_conditions.extend(hg_conditions)
    time.sleep(1)

    # 4. Search WebMD (require context to avoid false positives)
    print(f"    Checking WebMD...")
    webmd_text = search_webmd(name, state)
    all_text += " " + webmd_text
    webmd_conditions = detect_conditions(webmd_text, require_context=True)
    if webmd_conditions:
        print(f"    From WebMD: {', '.join(webmd_conditions)}")
        all_conditions.extend(webmd_conditions)
    time.sleep(1)

    # 5. Targeted web search if still no specific conditions (require context)
    if not all_conditions or all_conditions == inferred:
        print(f"    Running targeted web search...")
        web_text = search_duckduckgo_targeted(name, city, state)
        all_text += " " + web_text
        web_conditions = detect_conditions(web_text, require_context=True)
        if web_conditions:
            print(f"    From web search: {', '.join(web_conditions)}")
            all_conditions.extend(web_conditions)
        time.sleep(1)

    # Deduplicate conditions
    unique_conditions = list(dict.fromkeys(all_conditions))

    if unique_conditions:
        print(f"    FINAL: {', '.join(unique_conditions)}")
    elif use_other_default:
        print(f"    No conditions found, defaulting to 'Other'")
        unique_conditions = ['OTHER']
    else:
        print(f"    No conditions found")
        return ([], True)

    # Get condition IDs and update database
    condition_ids = get_condition_ids(cur, unique_conditions)

    if condition_ids:
        # Delete existing conditions
        cur.execute("DELETE FROM provider_conditions WHERE npi = %s", (npi,))

        # Insert new conditions
        for cid in condition_ids:
            cur.execute("""
                INSERT INTO provider_conditions (npi, condition_id)
                VALUES (%s, %s)
                ON CONFLICT (npi, condition_id) DO NOTHING
            """, (npi, cid))

    return (unique_conditions, True)

def get_providers_to_enrich(cur, limit=None, state_filter=None, reset=False):
    """Get providers that don't have conditions assigned yet."""
    if reset:
        # Get all providers (for re-enrichment)
        where_clauses = ["1=1"]
    else:
        where_clauses = ["""
            p.npi NOT IN (SELECT DISTINCT npi FROM provider_conditions)
        """]
    params = []

    if state_filter:
        where_clauses.append("p.cms_state = %s")
        params.append(state_filter.upper())

    where_sql = " AND ".join(where_clauses)

    query = f"""
        SELECT p.npi, p.first_name, p.last_name, p.cms_city, p.cms_state,
               p.specialty_desc
        FROM providers p
        WHERE {where_sql}
        ORDER BY p.total_claims DESC NULLS LAST
    """

    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query, params)
    return cur.fetchall()

def get_stats(cur):
    """Get enrichment statistics."""
    stats = {}

    # Total providers
    cur.execute("SELECT COUNT(*) as count FROM providers")
    stats['total_providers'] = cur.fetchone()['count']

    # Providers with conditions
    cur.execute("SELECT COUNT(DISTINCT npi) as count FROM provider_conditions")
    stats['with_conditions'] = cur.fetchone()['count']

    # Providers without conditions
    stats['without_conditions'] = stats['total_providers'] - stats['with_conditions']

    # Breakdown by condition
    cur.execute("""
        SELECT ct.code, ct.name, COUNT(pc.npi) as count
        FROM condition_types ct
        LEFT JOIN provider_conditions pc ON ct.id = pc.condition_id
        GROUP BY ct.id, ct.code, ct.name
        ORDER BY ct.display_order
    """)
    stats['by_condition'] = list(cur.fetchall())

    return stats

def print_stats(stats):
    """Print enrichment statistics."""
    print("\n" + "=" * 50)
    print("CONDITION ENRICHMENT STATISTICS")
    print("=" * 50)
    print(f"Total providers:        {stats['total_providers']:,}")
    print(f"With conditions:        {stats['with_conditions']:,}")
    print(f"Without conditions:     {stats['without_conditions']:,}")

    if stats['with_conditions'] > 0:
        pct = (stats['with_conditions'] / stats['total_providers']) * 100
        print(f"Enrichment progress:    {pct:.1f}%")

    print("\nBreakdown by condition:")
    for item in stats['by_condition']:
        print(f"  {item['name']:20} {item['count']:,}")
    print("=" * 50)

def reset_conditions(cur):
    """Reset all provider conditions."""
    cur.execute("DELETE FROM provider_conditions")
    print("Cleared all provider conditions.")

def main():
    parser = argparse.ArgumentParser(description='Enrich provider conditions from multiple sources')
    parser.add_argument('--limit', type=int, help='Limit number of providers to process')
    parser.add_argument('--state', type=str, help='Filter by state (e.g., CA, TX)')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    parser.add_argument('--reset', action='store_true', help='Clear existing conditions and re-enrich')
    parser.add_argument('--no-default', action='store_true',
                        help="Don't default to 'Other' when no conditions found")
    args = parser.parse_args()

    conn = get_db_connection()
    cur = conn.cursor()

    if args.stats:
        stats = get_stats(cur)
        print_stats(stats)
        cur.close()
        conn.close()
        return

    if args.reset:
        reset_conditions(cur)
        conn.commit()

    # Get providers to enrich
    providers = get_providers_to_enrich(cur, args.limit, args.state, args.reset)

    if not providers:
        print("All providers have been enriched with conditions!")
        stats = get_stats(cur)
        print_stats(stats)
        cur.close()
        conn.close()
        return

    print(f"\nFound {len(providers)} providers to enrich")
    print("-" * 50)

    enriched = 0
    conditions_found = 0

    try:
        for i, provider in enumerate(providers, 1):
            print(f"\n[{i}/{len(providers)}]")
            conditions, searched = enrich_provider(
                cur, provider,
                use_other_default=not args.no_default
            )

            if searched:
                enriched += 1
            if conditions:
                conditions_found += 1

            # Commit every 10 providers
            if i % 10 == 0:
                conn.commit()
                print(f"\n  [Committed {i} providers]")

        # Final commit
        conn.commit()

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving progress...")
        conn.commit()

    print(f"\n\nEnrichment complete!")
    print(f"  Providers processed: {enriched}")
    print(f"  Conditions assigned: {conditions_found}")

    # Show final stats
    stats = get_stats(cur)
    print_stats(stats)

    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
