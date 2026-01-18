#!/usr/bin/env python3
"""
Step 1: Download CMS Medicare DME data for HCPCS code E0483
Uses pagination to handle slow API responses
"""

import requests
import json
import time
from datetime import datetime

API_URL = "https://data.cms.gov/data-api/v1/dataset/86b4807a-d63a-44be-bfdf-ffd398d5e623/data"
HCPCS_CODE = "E0483"
OUTPUT_FILE = "cms_e0483_data.json"
PAGE_SIZE = 25  # Small page size for reliability
MAX_RECORDS = 2000  # Safety limit

def download_page(offset, size):
    """Download a single page of data."""
    params = {
        "filter[HCPCS_CD]": HCPCS_CODE,
        "size": size,
        "offset": offset
    }

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json'
    })

    response = session.get(API_URL, params=params, timeout=300)
    response.raise_for_status()
    return response.json()

def download_all_data():
    """Download all records using pagination."""

    print(f"Downloading CMS data for HCPCS code: {HCPCS_CODE}")
    print(f"Using page size: {PAGE_SIZE}")
    print("-" * 50)

    all_records = []
    offset = 0

    while offset < MAX_RECORDS:
        try:
            print(f"Fetching records {offset} to {offset + PAGE_SIZE}...")
            page_data = download_page(offset, PAGE_SIZE)

            if not page_data:
                print("No more records found.")
                break

            all_records.extend(page_data)
            print(f"  Retrieved {len(page_data)} records (total: {len(all_records)})")

            # If we got fewer records than page size, we've reached the end
            if len(page_data) < PAGE_SIZE:
                print("Reached end of data.")
                break

            offset += PAGE_SIZE

            # Rate limiting - be nice to the API
            time.sleep(2)

        except requests.exceptions.Timeout:
            print(f"  Timeout at offset {offset}, retrying after delay...")
            time.sleep(10)
            continue
        except requests.exceptions.RequestException as e:
            print(f"  Error: {e}")
            if all_records:
                print("  Saving partial data...")
                break
            else:
                raise

    if not all_records:
        print("ERROR: No records downloaded")
        return None

    # Process and save
    unique_npis = set(record.get("Rfrg_NPI") for record in all_records)

    output = {
        "metadata": {
            "download_date": datetime.now().isoformat(),
            "hcpcs_code": HCPCS_CODE,
            "hcpcs_description": all_records[0].get("HCPCS_Desc", "N/A"),
            "total_records": len(all_records),
            "unique_npis": len(unique_npis),
            "source_url": API_URL
        },
        "data": all_records
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'=' * 50}")
    print("DOWNLOAD COMPLETE")
    print(f"{'=' * 50}")
    print(f"Total Records: {len(all_records)}")
    print(f"Unique NPIs: {len(unique_npis)}")
    print(f"Saved to: {OUTPUT_FILE}")

    # Show state distribution
    states = {}
    for record in all_records:
        state = record.get("Rfrg_Prvdr_State_Abrvtn", "Unknown")
        states[state] = states.get(state, 0) + 1

    print(f"\nStates represented: {len(states)}")
    print("\nTop states by provider count:")
    for state, count in sorted(states.items(), key=lambda x: -x[1])[:10]:
        print(f"  {state}: {count}")

    return output

if __name__ == "__main__":
    download_all_data()
