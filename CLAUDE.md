# CMS DME Analysis Tool

Analysis tool for CMS Medicare DME data (HCPCS code E0483 - High Frequency Chest Wall Oscillation System).

## Technology Stack

- **Database**: PostgreSQL (via Postgres.app on macOS)
- **Backend**: Python 3.9+, Flask, openpyxl
- **Data Source**: CMS Data API (data.cms.gov)
- **Enrichment**: NPI Registry API, OpenStreetMap (Nominatim + Overpass)

## Project Structure

```
MyClaude/
├── dashboard.py              # Flask web app (port 5001)
├── templates/dashboard.html  # Main dashboard with search, filters, charts
├── schema.sql                # PostgreSQL schema
├── load_data.py              # Initial data loader
├── download_all_years.py     # Multi-year downloader (2014-2022)
├── enrich_npi.py             # NPI enrichment (clinic info, patient focus)
├── enrich_clinic_names.py    # Clinic name lookup via OpenStreetMap
└── cms_e0483_*.json          # Downloaded data files
```

## Database Tables

- `providers` - Master provider records (NPI, name, address, specialty)
- `provider_yearly_data` - Yearly billing data (claims, beneficiaries, services, payments)
- `provider_enrichment` - Enrichment status, patient focus (Adult/Pediatric/Both)
- `clinics` - Clinic locations per provider

## Quick Start

### 1. Start PostgreSQL
Open **Postgres.app** (blue elephant). Ensure server running on port 5432.

### 2. Start Dashboard
```bash
cd /Users/leahnoaeill/Downloads/MyClaude
python3 dashboard.py
```
Dashboard: **http://localhost:5001**

### 3. Run Enrichment (if needed)
```bash
python3 enrich_npi.py --stats                    # Check status
python3 enrich_npi.py > enrichment_log.txt 2>&1 &
```

### 4. Enrich Clinic Names
```bash
python3 enrich_clinic_names.py --stats           # Check status
python3 enrich_clinic_names.py > clinic_names_log.txt 2>&1 &
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard |
| `GET /api/providers` | Search (params: npi, name, state, patient_focus, year, page) |
| `GET /api/states` | Available states |
| `GET /api/years` | Available years |
| `GET /api/aggregates?year=` | Aggregate stats by year |
| `GET /api/export` | Export to Excel (.xlsx) |
| `GET /provider/<npi>` | Provider detail |

## Dashboard Features

- **Year Filter**: Top filter for viewing data by year
- **Aggregates**: Providers, Clinics, Claims, Beneficiaries, Avg Claims
- **Table**: Sortable columns (NPI, Name, Specialty, Focus, Claims, Beneficiaries, Location)
- **Search**: NPI, Name, State, Patient Focus filters
- **Export**: Download as Excel with clinic info
- **Charts**: Patient Focus, Top States, Top Specialties

## Data Fields (from CMS)

| Field | CMS Source | Description |
|-------|------------|-------------|
| `total_claims` | `Tot_Suplr_Clms` | Total supplier claims |
| `total_beneficiaries` | `Tot_Suplr_Benes` | Beneficiaries served |
| `total_services` | `Tot_Suplr_Srvcs` | Services provided |

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
# Database stats
/Applications/Postgres.app/Contents/Versions/latest/bin/psql -U postgres -d cms_analysis \
  -c "SELECT data_year, COUNT(*) FROM provider_yearly_data GROUP BY data_year ORDER BY data_year;"

# Enrichment progress
/Applications/Postgres.app/Contents/Versions/latest/bin/psql -U postgres -d cms_analysis \
  -c "SELECT search_status, COUNT(*) FROM provider_enrichment GROUP BY search_status;"

# Kill dashboard
lsof -ti:5001 | xargs kill -9
```

## Clinic Name Enrichment

Uses free OpenStreetMap APIs:
1. **Nominatim** - Geocodes address to coordinates
2. **Overpass** - Finds nearby healthcare facilities
3. **Fallback** - Uses provider name if no facility found

## Notes

- Dashboard uses port 5001 (port 5000 reserved by macOS AirPlay)
- NPI Registry: 1 req/sec rate limit
- OpenStreetMap: Free, no API key, 1 req/sec rate limit
