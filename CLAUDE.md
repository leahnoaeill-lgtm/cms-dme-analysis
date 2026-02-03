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
├── templates/provider_map.html # Heatmap/marker map view
├── schema.sql                # PostgreSQL schema
├── load_data.py              # Initial data loader
├── download_all_years.py     # Multi-year downloader (2014-2022)
├── enrich_npi.py             # NPI enrichment (clinic info, patient focus)
├── enrich_clinic_names.py    # Clinic name lookup via OpenStreetMap
├── enrich_conditions.py      # Condition specialty enrichment via web search
└── cms_e0483_*.json          # Downloaded data files
```

## Database Tables

- `providers` - Master provider records (NPI, name, address, specialty)
- `provider_yearly_data` - Yearly billing data (claims, beneficiaries, services, payments)
- `provider_enrichment` - Enrichment status, patient focus (Adult/Pediatric/Both)
- `clinics` - Clinic locations per provider
- `condition_types` - Condition specialties (ALS, MD, SCI, SMA, Bronchiectasis, COPD, CF, Other)
- `provider_conditions` - Many-to-many: provider conditions treated

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

### 5. Enrich Provider Conditions
```bash
python3 enrich_conditions.py --stats             # Check status
python3 enrich_conditions.py --limit 10          # Test on 10 providers
python3 enrich_conditions.py > conditions_log.txt 2>&1 &
```
Conditions: ALS, Muscular Dystrophy, Spinal Cord Injury, SMA, Bronchiectasis, COPD, Cystic Fibrosis, Other

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard |
| `GET /map` | Provider heatmap/marker map |
| `GET /api/providers` | Search (params: npi, name, state, patient_focus, condition, year, page) |
| `GET /api/states` | Available states |
| `GET /api/years` | Available years |
| `GET /api/conditions` | Available condition types |
| `GET /api/aggregates?year=` | Aggregate stats by year |
| `GET /api/export` | Export to Excel (.xlsx) |
| `GET /provider/<npi>` | Provider detail |
| `GET /api/provider/<npi>/conditions` | Get provider's conditions |
| `PUT /api/provider/<npi>/conditions` | Update provider's conditions |

## Dashboard Features

- **Year Filter**: Top filter for viewing data by year
- **Aggregates**: Providers, Clinics, Claims, Beneficiaries, Avg Claims
- **Table**: Sortable columns (NPI, Name, Specialty, Focus, Conditions, Claims, Beneficiaries, Location)
- **Search**: NPI, Name, State, Patient Focus, Condition filters
- **Editable Fields**: Patient Focus and Conditions can be updated inline
- **Export**: Download as Excel with clinic info and conditions
- **Charts**: Patient Focus, Top States, Top Specialties
- **Map View**: Heatmap or markers with filters (State, Focus, Beneficiaries, Condition)

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

## Docker Deployment (AWS)

### Quick Start with Docker
```bash
# 1. Copy environment file and set password
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD

# 2. Build and start containers
docker-compose up -d

# 3. Check status
docker-compose ps
docker-compose logs -f dashboard
```

Dashboard: **http://localhost:5001**

### Export Data from Local Mac
```bash
# Export current database
./scripts/export_data.sh

# This creates: data_export/cms_analysis_YYYYMMDD_HHMMSS.sql.gz
```

### Import Data to AWS
```bash
# Copy export file to AWS server, then:
./scripts/import_data.sh data_export/cms_analysis_*.sql.gz
```

### AWS EC2 Setup
```bash
# Install Docker on Amazon Linux 2
sudo yum update -y
sudo yum install -y docker
sudo service docker start
sudo usermod -a -G docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Clone repo and start
git clone https://github.com/leahnoaeill-lgtm/cms-dme-analysis.git
cd cms-dme-analysis
git checkout CMS_Dashboard_Heatmap
cp .env.example .env
# Edit .env with secure password
docker-compose up -d
```

### Docker Commands
```bash
# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Stop and remove data
docker-compose down -v

# Rebuild after code changes
docker-compose build --no-cache
docker-compose up -d
```

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | postgres123 | Database password |
| `DB_HOST` | db | Database host (container name) |
| `DB_PORT` | 5432 | Database port |
| `DB_NAME` | cms_analysis | Database name |
| `DB_USER` | postgres | Database user |

## Notes

- Dashboard uses port 5001 (port 5000 reserved by macOS AirPlay)
- NPI Registry: 1 req/sec rate limit
- OpenStreetMap: Free, no API key, 1 req/sec rate limit
- Docker uses gunicorn with 4 workers for production
