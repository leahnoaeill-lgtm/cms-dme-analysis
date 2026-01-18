#!/usr/bin/env python3
"""
Step 1: Download CMS Medicare DME data for HCPCS code E0483
High-frequency chest wall oscillation system (respiratory therapy equipment)
"""

import requests
import json
from datetime import datetime

API_URL = "https://data.cms.gov/data-api/v1/dataset/86b4807a-d63a-44be-bfdf-ffd398d5e623/data"
HCPCS_CODE = "E0483"
OUTPUT_FILE = "cms_e0483_data.json"

def download_cms_data():
    """Download all records for the specified HCPCS code."""

    print(f"Downloading CMS data for HCPCS code: {HCPCS_CODE}")
    print(f"API URL: {API_URL}")
    print("-" * 50)

    # Fetch data with filter - using size=2000 to ensure we get all records
    params = {
        "filter[HCPCS_CD]": HCPCS_CODE,
        "size": 2000  # More than enough for expected ~100 records
    }

    try:
        # Use longer timeout and retry logic for slow API
        max_retries = 3
        data = None

        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1} of {max_retries}...")
                response = requests.get(API_URL, params=params, timeout=180)
                response.raise_for_status()
                data = response.json()
                break
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    print(f"Timeout, retrying...")
                else:
                    raise

        if data is None:
            print("ERROR: Failed to retrieve data after retries")
            return None

        print(f"Records downloaded: {len(data)}")

        if len(data) == 0:
            print("WARNING: No records found for this HCPCS code")
            return None

        # Extract unique NPIs
        unique_npis = set(record.get("Rfrg_NPI") for record in data)
        print(f"Unique NPIs (providers): {len(unique_npis)}")

        # Show sample of fields
        if data:
            print("\nFields available in data:")
            for key in sorted(data[0].keys()):
                print(f"  - {key}")

        # Add metadata
        output = {
            "metadata": {
                "download_date": datetime.now().isoformat(),
                "hcpcs_code": HCPCS_CODE,
                "hcpcs_description": data[0].get("HCPCS_Desc", "N/A") if data else "N/A",
                "total_records": len(data),
                "unique_npis": len(unique_npis),
                "source_url": API_URL
            },
            "data": data
        }

        # Save to file
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\nData saved to: {OUTPUT_FILE}")
        print("\n" + "=" * 50)
        print("DOWNLOAD COMPLETE")
        print("=" * 50)

        # Show summary statistics
        print("\nSummary Statistics:")
        print(f"  Total Records: {len(data)}")
        print(f"  Unique Providers (NPIs): {len(unique_npis)}")

        # Count by state
        states = {}
        for record in data:
            state = record.get("Rfrg_Prvdr_State_Abrvtn", "Unknown")
            states[state] = states.get(state, 0) + 1

        print(f"  States represented: {len(states)}")
        print("\n  Top 10 states by provider count:")
        for state, count in sorted(states.items(), key=lambda x: -x[1])[:10]:
            print(f"    {state}: {count}")

        return output

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to download data: {e}")
        return None

if __name__ == "__main__":
    download_cms_data()
