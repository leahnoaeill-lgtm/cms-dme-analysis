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
