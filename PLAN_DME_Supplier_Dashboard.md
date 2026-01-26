# Plan: DME Supplier Dashboard with Tabbed Interface

## Overview
Add a DME Supplier dashboard alongside the existing Provider dashboard, accessible via tabs. The Supplier dashboard will mirror the Provider dashboard layout but display supplier-specific data from the CMS DME Supplier dataset.

## Data Source Analysis

**Provider Dashboard (Existing):**
- Dataset: Medicare DME by Referring Provider and Service
- Key: NPI of referring provider + HCPCS code
- Focus: Which providers are referring patients for specific DME equipment

**Supplier Dashboard (New):**
- Dataset: Medicare DME by Supplier ([API Docs](https://data.cms.gov/provider-summary-by-type-of-service/medicare-durable-medical-equipment-devices-supplies/medicare-durable-medical-equipment-devices-supplies-by-supplier))
- API: `https://data.cms.gov/data-api/v1/dataset/{UUID}/data`
- Key: NPI of supplier (the company/entity providing the equipment)
- Focus: Which suppliers are providing DME equipment and their billing metrics
- Additional data: Beneficiary demographics, clinical conditions, category breakdowns

**Key Differences:**
| Aspect | Provider | Supplier |
|--------|----------|----------|
| NPI Field | `Rfrg_NPI` | `Suplr_NPI` |
| Name Fields | `Rfrg_Prvdr_First_Name`, `Rfrg_Prvdr_Last_Name_Org` | `Suplr_Prvdr_First_Name`, `Suplr_Prvdr_Last_Name_Org` |
| HCPCS Filter | Yes (per HCPCS code) | No (aggregate across all codes) |
| Has Demographics | No | Yes (age, gender, race) |
| Has Conditions | No | Yes (chronic conditions %) |

## Implementation Plan

### Phase 1: Database Schema Updates

**New Tables:**
```sql
-- Suppliers master table
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL UNIQUE,
    last_name VARCHAR(255),
    first_name VARCHAR(255),
    credentials VARCHAR(50),
    entity_code VARCHAR(10),
    street1 VARCHAR(255),
    street2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    zip VARCHAR(10),
    country VARCHAR(10),
    specialty_desc VARCHAR(255),
    ruca_code VARCHAR(10),
    ruca_desc TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Supplier yearly data
CREATE TABLE supplier_yearly_data (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL REFERENCES suppliers(npi),
    data_year INTEGER NOT NULL,
    -- Aggregate metrics
    total_hcpcs_codes INTEGER,
    total_beneficiaries INTEGER,
    total_claims INTEGER,
    total_services INTEGER,
    submitted_charges DECIMAL(14,2),
    medicare_allowed DECIMAL(14,2),
    medicare_payment DECIMAL(14,2),
    medicare_standardized DECIMAL(14,2),
    -- DME category
    dme_hcpcs_codes INTEGER,
    dme_beneficiaries INTEGER,
    dme_claims INTEGER,
    dme_services INTEGER,
    dme_payment DECIMAL(14,2),
    -- POS category
    pos_hcpcs_codes INTEGER,
    pos_beneficiaries INTEGER,
    pos_claims INTEGER,
    pos_services INTEGER,
    pos_payment DECIMAL(14,2),
    -- Drug category
    drug_hcpcs_codes INTEGER,
    drug_beneficiaries INTEGER,
    drug_claims INTEGER,
    drug_services INTEGER,
    drug_payment DECIMAL(14,2),
    -- Demographics
    bene_avg_age DECIMAL(5,2),
    bene_female_pct DECIMAL(5,2),
    bene_male_pct DECIMAL(5,2),
    bene_avg_risk_score DECIMAL(5,2),
    CONSTRAINT supplier_yearly_unique UNIQUE (npi, data_year)
);

-- Supplier dataset versions
CREATE TABLE supplier_dataset_versions (
    id SERIAL PRIMARY KEY,
    data_year INTEGER NOT NULL UNIQUE,
    dataset_uuid VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    last_refreshed TIMESTAMP,
    record_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Phase 2: Backend API Updates (dashboard.py)

**New Endpoints:**
- `GET /api/suppliers` - Search suppliers with filters (npi, name, state, year)
- `GET /api/supplier/<npi>` - Supplier detail page
- `GET /api/supplier/states` - Available states for suppliers
- `GET /api/supplier/years` - Available years for suppliers
- `GET /api/supplier/aggregates` - Aggregate stats
- `GET /api/supplier/export` - Excel export
- `GET /api/admin/supplier/versions` - Supplier dataset versions
- `POST /api/admin/supplier/refresh` - Refresh supplier data

**Shared/Modified:**
- Admin jobs table can be reused (add job_type='supplier_refresh')

### Phase 3: Frontend Updates (dashboard.html)

**Tab Navigation:**
```html
<div class="tab-container">
    <button class="tab active" data-tab="provider">Providers</button>
    <button class="tab" data-tab="supplier">Suppliers</button>
</div>
```

**Provider Tab (Existing):**
- Keep all existing functionality
- Wrap in `<div id="provider-content" class="tab-content active">`

**Supplier Tab (New):**
- Mirror the Provider layout
- Stats cards: Total Suppliers, Total Claims, Total Beneficiaries, Avg Risk Score
- Charts: Top States, Entity Type Distribution (Individual vs Org)
- Search: NPI, Name, State, Year filters
- Table: NPI, Name, Specialty, Claims, Beneficiaries, Medicare Payment, Location
- Detail page with demographics and category breakdowns

### Phase 4: Admin Menu Updates

**Refresh Modal Changes:**
- Add tab or dropdown to select "Provider" or "Supplier" data type
- Show appropriate dataset versions based on selection
- Trigger correct refresh job type

### Phase 5: Data Discovery

**Required:** Discover dataset UUIDs for each year (2014-2023)
- The UUID `a2d56d3f-3531-4315-9d87-e29986516b41` appears to be for one specific year
- Need to find UUIDs for other years from CMS website

## File Changes Summary

| File | Changes |
|------|---------|
| `schema.sql` | Add suppliers, supplier_yearly_data, supplier_dataset_versions tables |
| `dashboard.py` | Add supplier API endpoints, refresh logic |
| `templates/dashboard.html` | Add tabs, supplier content section, supplier modals |
| `templates/supplier_detail.html` | New file for supplier detail page |

## Estimated Work Items

1. Database schema creation and migration
2. Backend: Supplier data models and API endpoints
3. Backend: Supplier refresh/download logic
4. Frontend: Tab navigation system
5. Frontend: Supplier dashboard content (stats, charts, table)
6. Frontend: Supplier search and filters
7. Frontend: Admin menu updates for supplier refresh
8. New template: Supplier detail page
9. Testing and refinement

## Questions to Clarify

1. **Enrichment for suppliers?** - Should we enrich suppliers with NPI Registry data like we do for providers?
2. **Dataset UUIDs** - Do you have the UUIDs for each year, or should I attempt to discover them?
3. **Priority metrics** - Which supplier metrics are most important to display prominently?
4. **Demographics display** - Should we show beneficiary demographics charts on the supplier dashboard?
