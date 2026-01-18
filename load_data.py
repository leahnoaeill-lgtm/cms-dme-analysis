#!/usr/bin/env python3
"""
Step 2: Load CMS data into PostgreSQL database
"""

import json
import psycopg2
from psycopg2.extras import execute_values

INPUT_FILE = "cms_e0483_data.json"
DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

def safe_int(value):
    """Convert to int, handling empty strings and None."""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def safe_float(value):
    """Convert to float, handling empty strings and None."""
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def load_data():
    """Load CMS data from JSON into PostgreSQL."""

    print("Loading CMS data into PostgreSQL...")
    print("-" * 50)

    # Load JSON data
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)

    records = data['data']
    print(f"Records to load: {len(records)}")

    # Connect to database
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Prepare data for insertion
    provider_rows = []
    for record in records:
        row = (
            record.get('Rfrg_NPI'),
            record.get('Rfrg_Prvdr_Last_Name_Org'),
            record.get('Rfrg_Prvdr_First_Name'),
            record.get('Rfrg_Prvdr_MI'),
            record.get('Rfrg_Prvdr_Crdntls'),
            record.get('Rfrg_Prvdr_Ent_Cd'),
            record.get('Rfrg_Prvdr_St1'),
            record.get('Rfrg_Prvdr_St2'),
            record.get('Rfrg_Prvdr_City'),
            record.get('Rfrg_Prvdr_State_Abrvtn'),
            record.get('Rfrg_Prvdr_Zip5'),
            record.get('Rfrg_Prvdr_Cntry'),
            record.get('Rfrg_Prvdr_Spclty_Cd'),
            record.get('Rfrg_Prvdr_Spclty_Desc'),
            record.get('Rfrg_Prvdr_Spclty_Srce'),
            record.get('Rfrg_Prvdr_RUCA'),
            record.get('Rfrg_Prvdr_RUCA_Cat'),
            record.get('Rfrg_Prvdr_RUCA_Desc'),
            record.get('HCPCS_CD'),
            record.get('HCPCS_Desc'),
            record.get('RBCS_Lvl'),
            record.get('RBCS_Id'),
            record.get('RBCS_Desc'),
            record.get('Suplr_Rentl_Ind'),
            safe_int(record.get('Tot_Suplrs')),
            safe_int(record.get('Tot_Suplr_Clms')),
            safe_int(record.get('Tot_Suplr_Srvcs')),
            safe_int(record.get('Tot_Suplr_Benes')),
            safe_float(record.get('Avg_Suplr_Sbmtd_Chrg')),
            safe_float(record.get('Avg_Suplr_Mdcr_Alowd_Amt')),
            safe_float(record.get('Avg_Suplr_Mdcr_Pymt_Amt')),
            safe_float(record.get('Avg_Suplr_Mdcr_Stdzd_Amt')),
        )
        provider_rows.append(row)

    # Insert data
    insert_sql = """
        INSERT INTO providers (
            npi, last_name, first_name, middle_initial, credentials, entity_code,
            cms_street1, cms_street2, cms_city, cms_state, cms_zip, cms_country,
            specialty_code, specialty_desc, specialty_source,
            ruca_code, ruca_category, ruca_desc,
            hcpcs_code, hcpcs_desc,
            rbcs_level, rbcs_id, rbcs_desc,
            supplier_rental_ind,
            total_suppliers, total_claims, total_services, total_beneficiaries,
            avg_submitted_charge, avg_medicare_allowed, avg_medicare_payment, avg_medicare_standardized
        ) VALUES %s
        ON CONFLICT (npi) DO UPDATE SET
            last_name = EXCLUDED.last_name,
            first_name = EXCLUDED.first_name,
            updated_at = CURRENT_TIMESTAMP
    """

    execute_values(cur, insert_sql, provider_rows)
    conn.commit()

    # Also create enrichment placeholder records
    cur.execute("""
        INSERT INTO provider_enrichment (npi, search_status)
        SELECT npi, 'pending' FROM providers
        ON CONFLICT (npi) DO NOTHING
    """)
    conn.commit()

    # Verify load
    cur.execute("SELECT COUNT(*) FROM providers")
    provider_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM provider_enrichment")
    enrichment_count = cur.fetchone()[0]

    print(f"\nData loaded successfully!")
    print(f"  Providers: {provider_count}")
    print(f"  Enrichment records: {enrichment_count}")

    # Show sample
    print("\nSample provider:")
    cur.execute("""
        SELECT npi, first_name, last_name, credentials, cms_city, cms_state, specialty_desc
        FROM providers LIMIT 1
    """)
    row = cur.fetchone()
    print(f"  NPI: {row[0]}")
    print(f"  Name: {row[1]} {row[2]}, {row[3]}")
    print(f"  Location: {row[4]}, {row[5]}")
    print(f"  Specialty: {row[6]}")

    # Stats by state
    print("\nTop 5 states by provider count:")
    cur.execute("""
        SELECT cms_state, COUNT(*) as cnt
        FROM providers
        GROUP BY cms_state
        ORDER BY cnt DESC
        LIMIT 5
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.close()
    conn.close()

    print("\n" + "=" * 50)
    print("STEP 2 COMPLETE: Data loaded into PostgreSQL")
    print("=" * 50)

if __name__ == "__main__":
    load_data()
