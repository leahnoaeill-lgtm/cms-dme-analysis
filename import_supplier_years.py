#!/usr/bin/env python3
"""Import supplier data for multiple years from CMS CSV files."""

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import csv
import io
import time
import sys

DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

# CSV URLs for each year (from CMS data-viewer endpoints)
CSV_URLS = {
    2014: "https://data.cms.gov/sites/default/files/2025-11/b60bc67d-2b90-47de-b31e-4e19be887d50/mup_dme_ry25_p05_v20_dy14_suphpr.csv",
    2015: "https://data.cms.gov/sites/default/files/2025-11/db640642-95f5-4258-a767-7d04fd1b0294/mup_dme_ry25_p05_v20_dy15_suphpr.csv",
    2016: "https://data.cms.gov/sites/default/files/2025-11/619da36a-956e-4d4a-90c0-ee1126acc925/mup_dme_ry25_p05_v20_dy16_suphpr.csv",
    2017: "https://data.cms.gov/sites/default/files/2025-11/b7635e3b-9260-41e5-b85f-58fcaad518a8/mup_dme_ry25_p05_v20_dy17_suphpr.csv",
    2018: "https://data.cms.gov/sites/default/files/2025-11/fbc67c84-4475-47d5-b2fb-a7b8d164fcf7/mup_dme_ry25_p05_v20_dy18_suphpr.csv",
    2019: "https://data.cms.gov/sites/default/files/2025-11/52254d8e-d851-46ad-8248-39fc86388267/mup_dme_ry25_p05_v20_dy19_suphpr.csv",
    2020: "https://data.cms.gov/sites/default/files/2025-11/40afca01-d1d8-4ac3-9607-4f3bba8d4182/mup_dme_ry25_p05_v20_dy20_suphpr.csv",
    2021: "https://data.cms.gov/sites/default/files/2025-11/6179521b-f3fd-4ea9-bdff-a1cae37466e0/mup_dme_ry25_p05_v20_dy21_suphpr.csv",
    2022: "https://data.cms.gov/sites/default/files/2025-11/9a07a963-19eb-480c-8052-ba1a24cf489d/mup_dme_ry25_p05_v20_dy22_suphpr.csv",
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

def download_csv(year, url):
    """Download CSV file for a specific year."""
    print(f"  Downloading CSV for {year}...", end='', flush=True)

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 CMS-Analysis-Tool/1.0',
        'Accept': 'text/csv'
    })

    try:
        response = session.get(url, timeout=300)
        response.raise_for_status()
        print(f" done ({len(response.content):,} bytes)")
        return response.text
    except Exception as e:
        print(f" Error: {e}")
        return None

def parse_and_filter_csv(csv_text, hcpcs_codes):
    """Parse CSV and filter for specific HCPCS codes."""
    records = {code: [] for code in hcpcs_codes}

    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        hcpcs = row.get('HCPCS_Cd', '')
        if hcpcs in hcpcs_codes:
            records[hcpcs].append(row)

    return records

def load_supplier_records(records, year, hcpcs_code, conn):
    """Load supplier records into the database."""
    if not records:
        return 0, 0

    cur = conn.cursor()
    new_suppliers = 0
    yearly_records = 0

    for record in records:
        npi = record.get('Suplr_NPI')
        if not npi:
            continue

        try:
            cur.execute("""
                INSERT INTO suppliers (
                    npi, last_name, first_name, middle_initial, credentials, entity_code,
                    street1, street2, city, state, state_fips, zip, country,
                    ruca_code, ruca_cat, ruca_desc,
                    specialty_code, specialty_desc, specialty_source
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (npi) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                RETURNING (xmax = 0) as inserted
            """, (
                npi,
                record.get('Suplr_Prvdr_Last_Name_Org'),
                record.get('Suplr_Prvdr_First_Name'),
                record.get('Suplr_Prvdr_MI'),
                record.get('Suplr_Prvdr_Crdntls'),
                record.get('Suplr_Prvdr_Ent_Cd'),
                record.get('Suplr_Prvdr_St1'),
                record.get('Suplr_Prvdr_St2'),
                record.get('Suplr_Prvdr_City'),
                record.get('Suplr_Prvdr_State_Abrvtn'),
                record.get('Suplr_Prvdr_State_FIPS'),
                record.get('Suplr_Prvdr_Zip5'),
                record.get('Suplr_Prvdr_Cntry'),
                record.get('Suplr_Prvdr_RUCA'),
                record.get('Suplr_Prvdr_RUCA_Cat'),
                record.get('Suplr_Prvdr_RUCA_Desc'),
                record.get('Suplr_Prvdr_Spclty_Cd'),
                record.get('Suplr_Prvdr_Spclty_Desc'),
                record.get('Suplr_Prvdr_Spclty_Srce'),
            ))

            result = cur.fetchone()
            if result and result['inserted']:
                new_suppliers += 1
        except Exception as e:
            print(f"\n    Error inserting supplier {npi}: {e}")
            conn.rollback()
            continue

        try:
            cur.execute("""
                INSERT INTO supplier_yearly_data (
                    npi, data_year, hcpcs_code, hcpcs_desc,
                    rbcs_level, rbcs_id, rbcs_desc, rental_indicator,
                    total_beneficiaries, total_claims, total_services,
                    avg_submitted_charge, avg_medicare_allowed, avg_medicare_payment, avg_medicare_standardized
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (npi, data_year, hcpcs_code) DO UPDATE SET
                    total_claims = EXCLUDED.total_claims,
                    total_beneficiaries = EXCLUDED.total_beneficiaries,
                    total_services = EXCLUDED.total_services,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                npi, year, hcpcs_code,
                record.get('HCPCS_Desc'),
                record.get('RBCS_Lvl'),
                record.get('RBCS_Id'),
                record.get('RBCS_Desc'),
                record.get('Suplr_Rentl_Ind'),
                safe_int(record.get('Tot_Suplr_Benes')),
                safe_int(record.get('Tot_Suplr_Clms')),
                safe_int(record.get('Tot_Suplr_Srvcs')),
                safe_float(record.get('Avg_Suplr_Sbmtd_Chrg')),
                safe_float(record.get('Avg_Suplr_Mdcr_Alowd_Amt')),
                safe_float(record.get('Avg_Suplr_Mdcr_Pymt_Amt')),
                safe_float(record.get('Avg_Suplr_Mdcr_Stdzd_Amt')),
            ))
            if cur.rowcount > 0:
                yearly_records += 1
        except Exception as e:
            print(f"\n    Error inserting yearly data for {npi}: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()

    return new_suppliers, yearly_records

def main():
    years_to_import = [2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]
    hcpcs_codes = ['E0483', 'E0482']

    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

    print(f"Importing supplier data for years: {years_to_import}")
    print(f"HCPCS codes: {hcpcs_codes}")
    print()

    total_new_suppliers = 0
    total_records = 0

    for year in years_to_import:
        if year not in CSV_URLS:
            print(f"[{year}] No CSV URL configured, skipping")
            continue

        print(f"[{year}]")

        csv_text = download_csv(year, CSV_URLS[year])
        if not csv_text:
            print(f"  Failed to download CSV, skipping")
            continue

        records_by_code = parse_and_filter_csv(csv_text, hcpcs_codes)

        for hcpcs_code in hcpcs_codes:
            records = records_by_code[hcpcs_code]
            if records:
                new_suppliers, yearly_records = load_supplier_records(records, year, hcpcs_code, conn)
                total_new_suppliers += new_suppliers
                total_records += yearly_records

                # Calculate totals for verification
                total_claims = sum(safe_int(r.get('Tot_Suplr_Clms')) or 0 for r in records)
                total_benes = sum(safe_int(r.get('Tot_Suplr_Benes')) or 0 for r in records)
                print(f"  {hcpcs_code}: {len(records)} suppliers, {total_claims:,} claims, {total_benes:,} beneficiaries")
            else:
                print(f"  {hcpcs_code}: No records found")

        print()

    conn.close()

    print("=" * 50)
    print(f"Import complete!")
    print(f"Total new suppliers: {total_new_suppliers}")
    print(f"Total yearly records: {total_records}")

if __name__ == '__main__':
    main()
