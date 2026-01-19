#!/usr/bin/env python3
"""
Download CMS DME data for HCPCS codes (E0483, E0482) for all years (2014-2023)
Supports --hcpcs argument to specify which code to download.
"""

import requests
import json
import time
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import argparse

# Dataset UUIDs for each year
DATASET_VERSIONS = {
    2014: "b834498f-158e-4152-9d63-13c946118033",
    2015: "af043480-65c0-436c-bd1b-3e45300a34a7",
    2016: "862a02e8-e97b-41d0-a5d3-8f314db03d62",
    2017: "f3d2da82-4383-4c9a-b559-fb94c7d8ddfc",
    2018: "55290cc6-c6e9-41e3-9896-dc8c4a35daf7",
    2019: "eb0019f6-791d-4065-ae4e-4761d2f6c9f2",
    2020: "323df359-ceac-4525-a350-e2cd9eb128fe",
    2021: "46ae675c-bc81-40ca-aa79-64da1c1ec9d9",
    2022: "0dd53b4b-67ba-48c7-b8fa-fecbdfc83b70",
    2023: "86b4807a-d63a-44be-bfdf-ffd398d5e623",
}

# HCPCS code descriptions
HCPCS_CODES = {
    "E0483": "High Frequency Chest Wall Oscillation System",
    "E0482": "Cough Stimulating Device",
}

API_BASE = "https://data.cms.gov/data-api/v1/dataset"
PAGE_SIZE = 25

DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

def safe_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def safe_float(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def download_year_data(year, uuid, hcpcs_code):
    """Download all records for a specific HCPCS code and year."""
    print(f"\n{'='*60}")
    print(f"Downloading data for HCPCS {hcpcs_code}, year {year}")
    print(f"Dataset UUID: {uuid}")
    print(f"{'='*60}")

    api_url = f"{API_BASE}/{uuid}/data"
    all_records = []
    offset = 0
    max_records = 5000  # Safety limit per year

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CMS-Analysis-Tool/1.0',
        'Accept': 'application/json'
    })

    while offset < max_records:
        params = {
            "filter[HCPCS_CD]": hcpcs_code,
            "size": PAGE_SIZE,
            "offset": offset
        }

        try:
            print(f"  Fetching records {offset} to {offset + PAGE_SIZE}...", end=" ", flush=True)
            response = session.get(api_url, params=params, timeout=180)
            response.raise_for_status()
            page_data = response.json()

            if not page_data:
                print("No more records.")
                break

            all_records.extend(page_data)
            print(f"Got {len(page_data)} (total: {len(all_records)})")

            if len(page_data) < PAGE_SIZE:
                print("  Reached end of data.")
                break

            offset += PAGE_SIZE
            time.sleep(1)  # Rate limiting

        except requests.exceptions.Timeout:
            print(f"Timeout, retrying...")
            time.sleep(5)
            continue
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            if all_records:
                print("  Saving partial data...")
                break
            else:
                return None

    print(f"  Total records for {year}: {len(all_records)}")
    return all_records

def load_records_to_db(records, year, hcpcs_code):
    """Load records into the database."""
    if not records:
        return 0, 0

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    new_providers = 0
    yearly_records = 0

    for record in records:
        npi = record.get('Rfrg_NPI')
        if not npi:
            continue

        # Insert or update provider (master record)
        cur.execute("""
            INSERT INTO providers (
                npi, last_name, first_name, middle_initial, credentials, entity_code,
                cms_street1, cms_street2, cms_city, cms_state, cms_zip, cms_country,
                specialty_code, specialty_desc, specialty_source,
                ruca_code, ruca_category, ruca_desc,
                hcpcs_code, hcpcs_desc,
                rbcs_level, rbcs_id, rbcs_desc,
                supplier_rental_ind,
                total_suppliers, total_claims, total_services, total_beneficiaries,
                avg_submitted_charge, avg_medicare_allowed, avg_medicare_payment, avg_medicare_standardized,
                data_year
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s
            )
            ON CONFLICT (npi) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            RETURNING (xmax = 0) as inserted
        """, (
            npi,
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
            year,
        ))

        result = cur.fetchone()
        if result and result[0]:
            new_providers += 1

        # Insert yearly billing data with HCPCS code
        cur.execute("""
            INSERT INTO provider_yearly_data (
                npi, data_year, hcpcs_code,
                total_suppliers, total_claims, total_services, total_beneficiaries,
                avg_submitted_charge, avg_medicare_allowed, avg_medicare_payment, avg_medicare_standardized,
                supplier_rental_ind
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (npi, data_year, hcpcs_code) DO NOTHING
        """, (
            npi,
            year,
            hcpcs_code,
            safe_int(record.get('Tot_Suplrs')),
            safe_int(record.get('Tot_Suplr_Clms')),
            safe_int(record.get('Tot_Suplr_Srvcs')),
            safe_int(record.get('Tot_Suplr_Benes')),
            safe_float(record.get('Avg_Suplr_Sbmtd_Chrg')),
            safe_float(record.get('Avg_Suplr_Mdcr_Alowd_Amt')),
            safe_float(record.get('Avg_Suplr_Mdcr_Pymt_Amt')),
            safe_float(record.get('Avg_Suplr_Mdcr_Stdzd_Amt')),
            record.get('Suplr_Rentl_Ind'),
        ))
        if cur.rowcount > 0:
            yearly_records += 1

    conn.commit()

    # Create enrichment records for new NPIs
    cur.execute("""
        INSERT INTO provider_enrichment (npi, search_status)
        SELECT npi, 'pending' FROM providers
        WHERE npi NOT IN (SELECT npi FROM provider_enrichment)
        ON CONFLICT (npi) DO NOTHING
    """)
    conn.commit()

    cur.close()
    conn.close()

    return new_providers, yearly_records

def main():
    parser = argparse.ArgumentParser(description='Download CMS DME data for specified HCPCS codes')
    parser.add_argument('--hcpcs', type=str, default='E0483', choices=list(HCPCS_CODES.keys()),
                        help='HCPCS code to download (default: E0483)')
    parser.add_argument('--year', type=int, help='Download only a specific year (optional)')
    args = parser.parse_args()

    hcpcs_code = args.hcpcs
    hcpcs_desc = HCPCS_CODES.get(hcpcs_code, "Unknown")

    print("="*60)
    print("CMS DME DATA DOWNLOAD")
    print(f"HCPCS Code: {hcpcs_code} - {hcpcs_desc}")
    print(f"Years: {min(DATASET_VERSIONS.keys())}-{max(DATASET_VERSIONS.keys())}")
    print("="*60)

    total_records = 0
    total_new_providers = 0
    total_yearly = 0

    years_to_download = [args.year] if args.year else sorted(DATASET_VERSIONS.keys())

    for year in years_to_download:
        if year not in DATASET_VERSIONS:
            print(f"Year {year} not available. Skipping.")
            continue

        uuid = DATASET_VERSIONS[year]
        records = download_year_data(year, uuid, hcpcs_code)

        if records:
            # Save to JSON file
            filename = f"cms_{hcpcs_code.lower()}_{year}.json"
            with open(filename, 'w') as f:
                json.dump({
                    "year": year,
                    "hcpcs_code": hcpcs_code,
                    "total_records": len(records),
                    "download_date": datetime.now().isoformat(),
                    "data": records
                }, f, indent=2)
            print(f"  Saved to {filename}")

            # Load to database
            new_providers, yearly_records = load_records_to_db(records, year, hcpcs_code)
            print(f"  New providers: {new_providers}, Yearly records: {yearly_records}")

            total_records += len(records)
            total_new_providers += new_providers
            total_yearly += yearly_records

        time.sleep(2)  # Pause between years

    print("\n" + "="*60)
    print("DOWNLOAD COMPLETE")
    print("="*60)
    print(f"Total records downloaded: {total_records}")
    print(f"Total new providers: {total_new_providers}")
    print(f"Total yearly records: {total_yearly}")

    # Show final stats
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(DISTINCT npi) FROM providers")
    print(f"\nUnique providers in database: {cur.fetchone()[0]}")

    cur.execute("SELECT hcpcs_code, data_year, COUNT(*) FROM provider_yearly_data GROUP BY hcpcs_code, data_year ORDER BY hcpcs_code, data_year")
    print("\nRecords by HCPCS code and year:")
    for row in cur.fetchall():
        print(f"  {row[0]} - {row[1]}: {row[2]}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
