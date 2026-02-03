-- CMS DME Analysis Database Schema

-- Main providers table (from CMS data)
CREATE TABLE IF NOT EXISTS providers (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL UNIQUE,

    -- Provider name
    last_name VARCHAR(255),
    first_name VARCHAR(255),
    middle_initial VARCHAR(10),
    credentials VARCHAR(50),
    entity_code VARCHAR(10),

    -- CMS Address (from original data)
    cms_street1 VARCHAR(255),
    cms_street2 VARCHAR(255),
    cms_city VARCHAR(100),
    cms_state VARCHAR(2),
    cms_zip VARCHAR(10),
    cms_country VARCHAR(10),

    -- Provider specialty
    specialty_code VARCHAR(10),
    specialty_desc VARCHAR(255),
    specialty_source VARCHAR(50),

    -- Rural/Urban classification
    ruca_code VARCHAR(10),
    ruca_category VARCHAR(50),
    ruca_desc TEXT,

    -- HCPCS info
    hcpcs_code VARCHAR(10),
    hcpcs_desc TEXT,

    -- Billing category
    rbcs_level VARCHAR(100),
    rbcs_id VARCHAR(20),
    rbcs_desc VARCHAR(255),

    -- Rental indicator
    supplier_rental_ind VARCHAR(1),

    -- Metrics
    total_suppliers INTEGER,
    total_claims INTEGER,
    total_services INTEGER,
    total_beneficiaries INTEGER,

    -- Financial averages
    avg_submitted_charge DECIMAL(12,2),
    avg_medicare_allowed DECIMAL(12,2),
    avg_medicare_payment DECIMAL(12,2),
    avg_medicare_standardized DECIMAL(12,2),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Provider enrichment table (from web searches)
CREATE TABLE IF NOT EXISTS provider_enrichment (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL UNIQUE REFERENCES providers(npi),

    -- Patient focus (from research)
    patient_focus VARCHAR(50),  -- 'Adult', 'Pediatric', 'Both', 'Unknown'
    patient_focus_source VARCHAR(255),  -- URL or source of information

    -- Search metadata
    search_status VARCHAR(20) DEFAULT 'pending',  -- pending, completed, failed
    search_date TIMESTAMP,
    search_notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Clinics table (multiple clinics per provider)
CREATE TABLE IF NOT EXISTS clinics (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL REFERENCES providers(npi),

    -- Clinic information (from research)
    clinic_name VARCHAR(255),
    street_address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    zip VARCHAR(10),
    phone VARCHAR(20),

    -- Source information
    source_url VARCHAR(500),
    source_name VARCHAR(100),  -- e.g., 'NPI Registry', 'Healthgrades', 'Doximity'

    -- Is this the primary practice?
    is_primary BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Provider yearly data table (per year/HCPCS code billing data)
CREATE TABLE IF NOT EXISTS provider_yearly_data (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL REFERENCES providers(npi),
    data_year INTEGER NOT NULL,
    hcpcs_code VARCHAR(10) NOT NULL,

    -- Billing metrics
    total_suppliers INTEGER,
    total_claims INTEGER,
    total_services INTEGER,
    total_beneficiaries INTEGER,

    -- Financial averages
    avg_submitted_charge DECIMAL(12,2),
    avg_medicare_allowed DECIMAL(12,2),
    avg_medicare_payment DECIMAL(12,2),
    avg_medicare_standardized DECIMAL(12,2),

    -- Rental indicator
    supplier_rental_ind VARCHAR(1),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint on npi + year + hcpcs_code
    CONSTRAINT provider_yearly_data_npi_year_hcpcs_key UNIQUE (npi, data_year, hcpcs_code)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_providers_state ON providers(cms_state);
CREATE INDEX IF NOT EXISTS idx_providers_specialty ON providers(specialty_code);
CREATE INDEX IF NOT EXISTS idx_clinics_npi ON clinics(npi);
CREATE INDEX IF NOT EXISTS idx_clinics_state ON clinics(state);
CREATE INDEX IF NOT EXISTS idx_enrichment_status ON provider_enrichment(search_status);
CREATE INDEX IF NOT EXISTS idx_yearly_data_npi ON provider_yearly_data(npi);
CREATE INDEX IF NOT EXISTS idx_yearly_data_year ON provider_yearly_data(data_year);
CREATE INDEX IF NOT EXISTS idx_yearly_data_hcpcs ON provider_yearly_data(hcpcs_code);

-- View for full provider info with enrichment
CREATE OR REPLACE VIEW provider_full_view AS
SELECT
    p.*,
    e.patient_focus,
    e.search_status,
    e.search_date,
    (SELECT COUNT(*) FROM clinics c WHERE c.npi = p.npi) as clinic_count
FROM providers p
LEFT JOIN provider_enrichment e ON p.npi = e.npi;

-- Dataset versions table (for dynamic year/UUID management)
CREATE TABLE IF NOT EXISTS dataset_versions (
    id SERIAL PRIMARY KEY,
    data_year INTEGER NOT NULL UNIQUE,
    dataset_uuid VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    last_refreshed TIMESTAMP,
    record_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Admin job tracking table
CREATE TABLE IF NOT EXISTS admin_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,  -- 'refresh' or 'enrich'
    status VARCHAR(20) DEFAULT 'pending',  -- pending, running, completed, failed
    parameters JSONB,
    progress INTEGER DEFAULT 0,
    total_items INTEGER,
    result_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert known dataset versions
INSERT INTO dataset_versions (data_year, dataset_uuid, description) VALUES
    (2014, 'b834498f-158e-4152-9d63-13c946118033', 'CMS DME 2014'),
    (2015, 'af043480-65c0-436c-bd1b-3e45300a34a7', 'CMS DME 2015'),
    (2016, '862a02e8-e97b-41d0-a5d3-8f314db03d62', 'CMS DME 2016'),
    (2017, 'f3d2da82-4383-4c9a-b559-fb94c7d8ddfc', 'CMS DME 2017'),
    (2018, '55290cc6-c6e9-41e3-9896-dc8c4a35daf7', 'CMS DME 2018'),
    (2019, 'eb0019f6-791d-4065-ae4e-4761d2f6c9f2', 'CMS DME 2019'),
    (2020, '323df359-ceac-4525-a350-e2cd9eb128fe', 'CMS DME 2020'),
    (2021, '46ae675c-bc81-40ca-aa79-64da1c1ec9d9', 'CMS DME 2021'),
    (2022, '0dd53b4b-67ba-48c7-b8fa-fecbdfc83b70', 'CMS DME 2022'),
    (2023, '86b4807a-d63a-44be-bfdf-ffd398d5e623', 'CMS DME 2023')
ON CONFLICT (data_year) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_admin_jobs_status ON admin_jobs(status);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_year ON dataset_versions(data_year);

-- ============== SUPPLIER TABLES ==============

-- Suppliers master table
CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL UNIQUE,
    last_name VARCHAR(255),
    first_name VARCHAR(255),
    middle_initial VARCHAR(10),
    credentials VARCHAR(50),
    entity_code VARCHAR(10),
    street1 VARCHAR(255),
    street2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    state_fips VARCHAR(5),
    zip VARCHAR(10),
    country VARCHAR(10),
    ruca_code VARCHAR(10),
    ruca_cat VARCHAR(10),
    ruca_desc TEXT,
    specialty_code VARCHAR(10),
    specialty_desc VARCHAR(255),
    specialty_source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Supplier yearly data (per HCPCS code)
CREATE TABLE IF NOT EXISTS supplier_yearly_data (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL REFERENCES suppliers(npi),
    data_year INTEGER NOT NULL,
    hcpcs_code VARCHAR(10) NOT NULL,
    hcpcs_desc TEXT,
    rbcs_level VARCHAR(100),
    rbcs_id VARCHAR(20),
    rbcs_desc VARCHAR(255),
    rental_indicator VARCHAR(1),
    total_beneficiaries INTEGER,
    total_claims INTEGER,
    total_services INTEGER,
    avg_submitted_charge DECIMAL(12,2),
    avg_medicare_allowed DECIMAL(12,2),
    avg_medicare_payment DECIMAL(12,2),
    avg_medicare_standardized DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT supplier_yearly_unique UNIQUE (npi, data_year, hcpcs_code)
);

-- Supplier enrichment table
CREATE TABLE IF NOT EXISTS supplier_enrichment (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL UNIQUE REFERENCES suppliers(npi),
    business_name VARCHAR(255),
    search_status VARCHAR(20) DEFAULT 'pending',
    search_date TIMESTAMP,
    search_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Supplier dataset versions
CREATE TABLE IF NOT EXISTS supplier_dataset_versions (
    id SERIAL PRIMARY KEY,
    data_year INTEGER NOT NULL UNIQUE,
    dataset_uuid VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    last_refreshed TIMESTAMP,
    record_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert known supplier dataset version (2023)
INSERT INTO supplier_dataset_versions (data_year, dataset_uuid, description) VALUES
    (2023, '1746a83e-bb65-4300-8e02-21edbab77c6b', 'CMS DME Supplier 2023')
ON CONFLICT (data_year) DO NOTHING;

-- Indexes for supplier tables
CREATE INDEX IF NOT EXISTS idx_suppliers_state ON suppliers(state);
CREATE INDEX IF NOT EXISTS idx_suppliers_specialty ON suppliers(specialty_code);
CREATE INDEX IF NOT EXISTS idx_supplier_yearly_npi ON supplier_yearly_data(npi);
CREATE INDEX IF NOT EXISTS idx_supplier_yearly_year ON supplier_yearly_data(data_year);
CREATE INDEX IF NOT EXISTS idx_supplier_yearly_hcpcs ON supplier_yearly_data(hcpcs_code);
CREATE INDEX IF NOT EXISTS idx_supplier_enrichment_status ON supplier_enrichment(search_status);

-- ============== CONDITION TYPES ==============

-- Condition types lookup table (diseases/conditions providers treat)
CREATE TABLE IF NOT EXISTS condition_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Junction table: provider <-> conditions (many-to-many)
CREATE TABLE IF NOT EXISTS provider_conditions (
    id SERIAL PRIMARY KEY,
    npi VARCHAR(10) NOT NULL REFERENCES providers(npi),
    condition_id INTEGER NOT NULL REFERENCES condition_types(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT provider_conditions_unique UNIQUE(npi, condition_id)
);

-- Indexes for condition tables
CREATE INDEX IF NOT EXISTS idx_provider_conditions_npi ON provider_conditions(npi);
CREATE INDEX IF NOT EXISTS idx_provider_conditions_condition ON provider_conditions(condition_id);

-- Seed condition types
INSERT INTO condition_types (code, name, display_order) VALUES
    ('ALS', 'ALS', 1),
    ('MD', 'Muscular Dystrophy', 2),
    ('SCI', 'Spinal Cord Injury', 3),
    ('SMA', 'SMA', 4),
    ('BRONCH', 'Bronchiectasis', 5),
    ('COPD', 'COPD', 6),
    ('CF', 'Cystic Fibrosis', 7),
    ('OTHER', 'Other', 8)
ON CONFLICT (code) DO NOTHING;
