# CMS DME Analysis Tool

Analysis tool for CMS Medicare DME data (HCPCS code E0483 - High Frequency Chest Wall Oscillation System).

## Technology Stack

- **Database**: PostgreSQL (via Postgres.app on macOS)
- **Backend**: Python 3.9+, Flask
- **Data Source**: CMS Data API (data.cms.gov)
- **Enrichment**: NPI Registry API, OpenStreetMap (Nominatim + Overpass)

## Project Structure

```
MyClaude/
├── CLAUDE.md                 # This file
├── dashboard.py              # Flask web application (port 5001)
├── templates/
│   ├── dashboard.html        # Main dashboard with search, filters, aggregates
│   └── provider_detail.html  # Individual provider detail page
├── schema.sql                # PostgreSQL database schema
├── load_data.py              # Initial data loader for 2023 data
├── download_all_years.py     # Multi-year data downloader (2014-2022)
├── enrich_npi.py             # NPI enrichment tool (clinic info, patient focus)
├── enrich_clinic_names.py    # Clinic name lookup via Google Places API
└── cms_e0483_*.json          # Downloaded JSON data files by year
```

## Database Schema

**Tables:**
- `providers` - Master provider records (NPI, name, address, specialty)
- `provider_yearly_data` - Year-over-year billing data (claims, services, payments)
- `provider_enrichment` - Enrichment status and patient focus (Adult/Pediatric/Both)
- `clinics` - Clinic locations per provider (multiple per NPI)

## Key Scripts

| Script | Purpose |
|--------|---------|
| `dashboard.py` | Flask web server with search, filtering, aggregates |
| `enrich_npi.py` | Queries NPI Registry for clinic addresses and patient focus |
| `enrich_clinic_names.py` | Looks up facility names via Google Places API |
| `download_all_years.py` | Downloads E0483 data for years 2014-2022 from CMS API |
| `load_data.py` | Loads JSON data into PostgreSQL |

## Starting the Project

### 1. Start PostgreSQL

Open **Postgres.app** from Applications (blue elephant icon). Ensure server is running on port 5432.

### 2. Verify Database Access

```bash
/Applications/Postgres.app/Contents/Versions/latest/bin/psql -h localhost -p 5432 -U postgres -d cms_analysis
```

### 3. Start the Dashboard

```bash
cd /Users/leahnoaeill/Downloads/MyClaude
python3 dashboard.py
```

Dashboard runs at: **http://localhost:5001**

### 4. Run Enrichment (if needed)

```bash
python3 enrich_npi.py > enrichment_log.txt 2>&1 &
```

### 5. Download Additional Years (if needed)

```bash
python3 download_all_years.py > download_all_years_log.txt 2>&1 &
```

### 6. Enrich Clinic Names (free - OpenStreetMap)

```bash
python3 enrich_clinic_names.py --test 5  # Test first
python3 enrich_clinic_names.py > clinic_names_log.txt 2>&1 &
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard page |
| `GET /api/providers` | Search providers (params: npi, name, state, patient_focus, year, page) |
| `GET /api/states` | List of available states |
| `GET /api/years` | List of available data years |
| `GET /api/aggregates?year=` | Aggregate stats filtered by year |
| `GET /provider/<npi>` | Provider detail page |

## Database Connection

```python
DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}
```

## Common Commands

```bash
# Check database stats
/Applications/Postgres.app/Contents/Versions/latest/bin/psql -h localhost -U postgres -d cms_analysis \
  -c "SELECT data_year, COUNT(*) FROM provider_yearly_data GROUP BY data_year ORDER BY data_year;"

# Check enrichment progress
/Applications/Postgres.app/Contents/Versions/latest/bin/psql -h localhost -U postgres -d cms_analysis \
  -c "SELECT search_status, COUNT(*) FROM provider_enrichment GROUP BY search_status;"

# Kill process on port 5001
lsof -ti:5001 | xargs kill -9
```

## Notes

- Port 5000 is used by macOS AirPlay; dashboard uses port 5001
- NPI Registry API rate limit: 1 request/second
- CMS API pagination: 25 records per request with 1s delay
- OpenStreetMap APIs: Free, no key required, 1 req/sec rate limit
