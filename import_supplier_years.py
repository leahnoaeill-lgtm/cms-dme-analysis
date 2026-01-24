#!/usr/bin/env python3
"""Import supplier data for multiple years from CMS API."""

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import time
import sys

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

def download_supplier_data(year, uuid, hcpcs_code):
    """Download supplier data for a specific year and HCPCS code."""
    api_url = f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"
    all_records = []
    offset = 0
    page_size = 100
    max_records = 5000

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 CMS-Analysis-Tool/1.0',
        'Accept': 'application/json'
    })

    print(f"  Downloading {hcpcs_code} for {year}...", end='', flush=True)

    while offset < max_records:
        params = {
            "filter[HCPCS_Cd]": hcpcs_code,
            "size": page_size,
            "offset": offset
        }

        try:
            response = session.get(api_url, params=params, timeout=180)
            response.raise_for_status()
            page_data = response.json()
        except Exception as e:
            print(f" Error: {e}")
            return all_records

        if not page_data:
            break

        all_records.extend(page_data)
        print(f".", end='', flush=True)

        if len(page_data) < page_size:
            break

        offset += page_size
        time.sleep(0.5)

    print(f" {len(all_records)} records")
    return all_records

def load_supplier_records(records, year, hcpcs_code, conn):
    """Load supplier records into the database."""
    if not records:
        return 0, 0, []

    cur = conn.cursor()
    new_suppliers = 0
    yearly_records = 0
    processed_npis = []

    for record in records:
        npi = record.get('Suplr_NPI')
        if not npi:
            continue

        processed_npis.append(npi)

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

    conn.commit()
    cur.close()

    return new_suppliers, yearly_records, processed_npis

def main():
    # Years to import (skip 2023 as it's already loaded)
    years_to_import = [2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]
    hcpcs_codes = ['E0483', 'E0482']

    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    # Get UUIDs
    cur.execute("SELECT data_year, dataset_uuid FROM supplier_dataset_versions WHERE data_year = ANY(%s)", (years_to_import,))
    uuid_map = {row['data_year']: row['dataset_uuid'] for row in cur.fetchall()}
    cur.close()

    print(f"Importing supplier data for years: {years_to_import}")
    print(f"HCPCS codes: {hcpcs_codes}")
    print(f"Found UUIDs for {len(uuid_map)} years")
    print()

    total_new_suppliers = 0
    total_records = 0

    for year in years_to_import:
        if year not in uuid_map:
            print(f"[{year}] No UUID found, skipping")
            continue

        uuid = uuid_map[year]
        print(f"[{year}] UUID: {uuid}")

        for hcpcs_code in hcpcs_codes:
            records = download_supplier_data(year, uuid, hcpcs_code)
            if records:
                new_suppliers, yearly_records, _ = load_supplier_records(records, year, hcpcs_code, conn)
                total_new_suppliers += new_suppliers
                total_records += yearly_records
                print(f"    Loaded: {new_suppliers} new suppliers, {yearly_records} yearly records")
            else:
                print(f"    No records found")

            time.sleep(1)  # Rate limiting between API calls

        print()

    conn.close()

    print("=" * 50)
    print(f"Import complete!")
    print(f"Total new suppliers: {total_new_suppliers}")
    print(f"Total yearly records: {total_records}")

if __name__ == '__main__':
    main()
