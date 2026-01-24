#!/usr/bin/env python3
"""
CMS DME Analysis Dashboard
Web-based interface for browsing and analyzing provider data
"""

from flask import Flask, render_template, request, jsonify, Response
import psycopg2
from psycopg2.extras import RealDictCursor
from openpyxl import Workbook
from io import BytesIO
import requests
import json
import time
import threading
from datetime import datetime

app = Flask(__name__)

# Background job tracking
active_jobs = {}

DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
}

# HCPCS code descriptions
HCPCS_CODES = {
    "E0483": "High Frequency Chest Wall Oscillation System",
    "E0482": "Cough Stimulating Device",
}

def get_db_connection():
    """Get a database connection."""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

@app.route('/')
def dashboard():
    """Main dashboard page."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get available years
    cur.execute("""
        SELECT DISTINCT data_year FROM provider_yearly_data
        WHERE data_year IS NOT NULL
        ORDER BY data_year DESC
    """)
    available_years = [row['data_year'] for row in cur.fetchall()]

    # Get available HCPCS codes from database
    cur.execute("""
        SELECT DISTINCT hcpcs_code FROM provider_yearly_data
        WHERE hcpcs_code IS NOT NULL
        ORDER BY hcpcs_code
    """)
    available_hcpcs = [row['hcpcs_code'] for row in cur.fetchall()]

    # Get aggregates (all years combined for initial view)
    aggregates = {}

    # Total providers
    cur.execute("SELECT COUNT(*) as count FROM providers")
    aggregates['total_providers'] = cur.fetchone()['count']

    # Total clinics
    cur.execute("SELECT COUNT(*) as count FROM clinics")
    aggregates['total_clinics'] = cur.fetchone()['count']

    # Enrichment status
    cur.execute("""
        SELECT search_status, COUNT(*) as count
        FROM provider_enrichment
        GROUP BY search_status
    """)
    aggregates['enrichment_status'] = {row['search_status']: row['count'] for row in cur.fetchall()}

    # Patient focus distribution
    cur.execute("""
        SELECT COALESCE(patient_focus, 'Pending') as focus, COUNT(*) as count
        FROM provider_enrichment
        GROUP BY patient_focus
        ORDER BY count DESC
    """)
    aggregates['patient_focus'] = [dict(row) for row in cur.fetchall()]

    # Top states by claims
    cur.execute("""
        SELECT p.cms_state, COALESCE(SUM(y.total_claims), 0) as total_claims
        FROM providers p
        LEFT JOIN provider_yearly_data y ON p.npi = y.npi
        GROUP BY p.cms_state
        ORDER BY total_claims DESC
        LIMIT 10
    """)
    aggregates['top_states'] = [dict(row) for row in cur.fetchall()]

    # Top specialties
    cur.execute("""
        SELECT specialty_desc, COUNT(*) as count
        FROM providers
        WHERE specialty_desc IS NOT NULL
        GROUP BY specialty_desc
        ORDER BY count DESC
        LIMIT 10
    """)
    aggregates['top_specialties'] = [dict(row) for row in cur.fetchall()]

    # Total claims sum (from yearly data)
    cur.execute("SELECT SUM(total_claims) as total FROM provider_yearly_data")
    aggregates['total_claims'] = cur.fetchone()['total'] or 0

    # Total beneficiaries sum (from yearly data)
    cur.execute("SELECT SUM(total_beneficiaries) as total FROM provider_yearly_data")
    aggregates['total_beneficiaries'] = cur.fetchone()['total'] or 0

    # Average claims per provider
    cur.execute("SELECT AVG(total_claims) as avg FROM provider_yearly_data WHERE total_claims IS NOT NULL")
    avg_claims = cur.fetchone()['avg']
    aggregates['avg_claims'] = round(float(avg_claims), 1) if avg_claims else 0

    # Years data summary
    cur.execute("""
        SELECT data_year, COUNT(*) as providers, SUM(total_claims) as claims
        FROM provider_yearly_data
        GROUP BY data_year
        ORDER BY data_year
    """)
    aggregates['yearly_summary'] = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('dashboard.html', aggregates=aggregates, available_years=available_years,
                           available_hcpcs=available_hcpcs, hcpcs_descriptions=HCPCS_CODES)

@app.route('/api/hcpcs_codes')
def get_hcpcs_codes():
    """Get list of available HCPCS codes with descriptions."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT hcpcs_code
        FROM provider_yearly_data
        WHERE hcpcs_code IS NOT NULL
        ORDER BY hcpcs_code
    """)
    codes = [row['hcpcs_code'] for row in cur.fetchall()]
    cur.close()
    conn.close()
    # Return codes with descriptions
    result = [{"code": code, "description": HCPCS_CODES.get(code, "Unknown")} for code in codes]
    return jsonify(result)

@app.route('/api/aggregates')
def get_aggregates():
    """API endpoint for aggregates with optional year and HCPCS code filter."""
    conn = get_db_connection()
    cur = conn.cursor()

    year = request.args.get('year', '').strip()
    hcpcs_code = request.args.get('hcpcs_code', '').strip()

    aggregates = {}

    # Build WHERE clause for HCPCS filter
    hcpcs_filter = ""
    hcpcs_params = []
    if hcpcs_code and hcpcs_code != 'all':
        hcpcs_filter = " AND hcpcs_code = %s"
        hcpcs_params = [hcpcs_code]

    if year and year != 'all':
        year = int(year)
        # Year-specific aggregates from yearly data
        cur.execute(f"""
            SELECT COUNT(DISTINCT npi) as count FROM provider_yearly_data WHERE data_year = %s{hcpcs_filter}
        """, [year] + hcpcs_params)
        aggregates['total_providers'] = cur.fetchone()['count']

        cur.execute(f"""
            SELECT SUM(total_claims) as total FROM provider_yearly_data WHERE data_year = %s{hcpcs_filter}
        """, [year] + hcpcs_params)
        aggregates['total_claims'] = cur.fetchone()['total'] or 0

        cur.execute(f"""
            SELECT SUM(total_beneficiaries) as total FROM provider_yearly_data WHERE data_year = %s{hcpcs_filter}
        """, [year] + hcpcs_params)
        aggregates['total_beneficiaries'] = cur.fetchone()['total'] or 0

        cur.execute(f"""
            SELECT AVG(total_claims) as avg FROM provider_yearly_data
            WHERE data_year = %s AND total_claims IS NOT NULL{hcpcs_filter}
        """, [year] + hcpcs_params)
        avg_claims = cur.fetchone()['avg']
        aggregates['avg_claims'] = round(float(avg_claims), 1) if avg_claims else 0

        # Top states by claims for selected year
        cur.execute(f"""
            SELECT p.cms_state, COALESCE(SUM(y.total_claims), 0) as total_claims
            FROM provider_yearly_data y
            JOIN providers p ON y.npi = p.npi
            WHERE y.data_year = %s{hcpcs_filter.replace('hcpcs_code', 'y.hcpcs_code')}
            GROUP BY p.cms_state
            ORDER BY total_claims DESC
            LIMIT 10
        """, [year] + hcpcs_params)
        aggregates['top_states'] = [dict(row) for row in cur.fetchall()]

    else:
        # All years combined (with optional HCPCS filter)
        if hcpcs_code and hcpcs_code != 'all':
            cur.execute("""
                SELECT COUNT(DISTINCT npi) as count FROM provider_yearly_data WHERE hcpcs_code = %s
            """, [hcpcs_code])
        else:
            cur.execute("SELECT COUNT(*) as count FROM providers")
        aggregates['total_providers'] = cur.fetchone()['count']

        base_where = "WHERE hcpcs_code = %s" if (hcpcs_code and hcpcs_code != 'all') else ""
        base_params = [hcpcs_code] if (hcpcs_code and hcpcs_code != 'all') else []

        cur.execute(f"SELECT SUM(total_claims) as total FROM provider_yearly_data {base_where}", base_params)
        aggregates['total_claims'] = cur.fetchone()['total'] or 0

        cur.execute(f"SELECT SUM(total_beneficiaries) as total FROM provider_yearly_data {base_where}", base_params)
        aggregates['total_beneficiaries'] = cur.fetchone()['total'] or 0

        where_claims = f"{base_where} AND total_claims IS NOT NULL" if base_where else "WHERE total_claims IS NOT NULL"
        cur.execute(f"SELECT AVG(total_claims) as avg FROM provider_yearly_data {where_claims}", base_params)
        avg_claims = cur.fetchone()['avg']
        aggregates['avg_claims'] = round(float(avg_claims), 1) if avg_claims else 0

        if hcpcs_code and hcpcs_code != 'all':
            cur.execute("""
                SELECT p.cms_state, COALESCE(SUM(y.total_claims), 0) as total_claims
                FROM providers p
                LEFT JOIN provider_yearly_data y ON p.npi = y.npi AND y.hcpcs_code = %s
                GROUP BY p.cms_state
                ORDER BY total_claims DESC
                LIMIT 10
            """, [hcpcs_code])
        else:
            cur.execute("""
                SELECT p.cms_state, COALESCE(SUM(y.total_claims), 0) as total_claims
                FROM providers p
                LEFT JOIN provider_yearly_data y ON p.npi = y.npi
                GROUP BY p.cms_state
                ORDER BY total_claims DESC
                LIMIT 10
            """)
        aggregates['top_states'] = [dict(row) for row in cur.fetchall()]

    # These don't change by year
    cur.execute("SELECT COUNT(*) as count FROM clinics")
    aggregates['total_clinics'] = cur.fetchone()['count']

    cur.execute("""
        SELECT search_status, COUNT(*) as count
        FROM provider_enrichment
        GROUP BY search_status
    """)
    aggregates['enrichment_status'] = {row['search_status']: row['count'] for row in cur.fetchall()}

    cur.execute("""
        SELECT COALESCE(patient_focus, 'Pending') as focus, COUNT(*) as count
        FROM provider_enrichment
        GROUP BY patient_focus
        ORDER BY count DESC
    """)
    aggregates['patient_focus'] = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return jsonify(aggregates)

@app.route('/api/years')
def get_years():
    """Get list of available years."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT data_year
        FROM provider_yearly_data
        WHERE data_year IS NOT NULL
        ORDER BY data_year DESC
    """)
    years = [row['data_year'] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(years)

@app.route('/api/providers')
def get_providers():
    """API endpoint for provider data with search and filtering."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get filter parameters
    npi = request.args.get('npi', '').strip()
    name = request.args.get('name', '').strip()
    state = request.args.get('state', '').strip()
    patient_focus = request.args.get('patient_focus', '').strip()
    year = request.args.get('year', '').strip()
    hcpcs_code = request.args.get('hcpcs_code', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    # Build query
    where_clauses = []
    params = []

    if npi:
        where_clauses.append("p.npi LIKE %s")
        params.append(f"%{npi}%")

    if name:
        where_clauses.append("(p.first_name ILIKE %s OR p.last_name ILIKE %s)")
        params.extend([f"%{name}%", f"%{name}%"])

    if state:
        where_clauses.append("p.cms_state = %s")
        params.append(state.upper())

    if patient_focus and patient_focus != 'all':
        where_clauses.append("e.patient_focus = %s")
        params.append(patient_focus)

    if year and year != 'all':
        where_clauses.append("y.data_year = %s")
        params.append(int(year))

    if hcpcs_code and hcpcs_code != 'all':
        where_clauses.append("y.hcpcs_code = %s")
        params.append(hcpcs_code)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Use yearly data if year or hcpcs_code is specified (need to join with yearly data)
    needs_yearly_join = (year and year != 'all') or (hcpcs_code and hcpcs_code != 'all')

    if needs_yearly_join:
        # Get total count
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM providers p
            JOIN provider_yearly_data y ON p.npi = y.npi
            LEFT JOIN provider_enrichment e ON p.npi = e.npi
            WHERE {where_sql}
        """
        cur.execute(count_sql, params)
        total = cur.fetchone()['count']

        # Get paginated data
        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT
                p.npi,
                p.first_name,
                p.last_name,
                p.credentials,
                p.cms_city,
                p.cms_state,
                p.specialty_desc,
                y.total_claims,
                y.total_services,
                y.total_beneficiaries,
                y.data_year,
                y.hcpcs_code,
                COALESCE(e.patient_focus, 'Pending') as patient_focus,
                e.search_status
            FROM providers p
            JOIN provider_yearly_data y ON p.npi = y.npi
            LEFT JOIN provider_enrichment e ON p.npi = e.npi
            WHERE {where_sql}
            ORDER BY y.total_claims DESC NULLS LAST, p.npi
            LIMIT %s OFFSET %s
        """
        cur.execute(data_sql, params + [per_page, offset])
    else:
        # Get total count (all years - use latest year's data for each provider)
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM providers p
            LEFT JOIN provider_enrichment e ON p.npi = e.npi
            WHERE {where_sql}
        """
        cur.execute(count_sql, params)
        total = cur.fetchone()['count']

        # Get paginated data with aggregated claims across all years
        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT
                p.npi,
                p.first_name,
                p.last_name,
                p.credentials,
                p.cms_city,
                p.cms_state,
                p.specialty_desc,
                COALESCE(SUM(y.total_claims), 0) as total_claims,
                COALESCE(SUM(y.total_services), 0) as total_services,
                COALESCE(SUM(y.total_beneficiaries), 0) as total_beneficiaries,
                NULL as data_year,
                NULL as hcpcs_code,
                COALESCE(e.patient_focus, 'Pending') as patient_focus,
                e.search_status
            FROM providers p
            LEFT JOIN provider_yearly_data y ON p.npi = y.npi
            LEFT JOIN provider_enrichment e ON p.npi = e.npi
            WHERE {where_sql}
            GROUP BY p.npi, p.first_name, p.last_name, p.credentials,
                     p.cms_city, p.cms_state, p.specialty_desc,
                     e.patient_focus, e.search_status
            ORDER BY total_claims DESC NULLS LAST, p.npi
            LIMIT %s OFFSET %s
        """
        cur.execute(data_sql, params + [per_page, offset])

    providers = [dict(row) for row in cur.fetchall()]

    # Get clinics for each provider
    for provider in providers:
        cur.execute("""
            SELECT clinic_name, street_address, city, state, zip, phone
            FROM clinics
            WHERE npi = %s
            ORDER BY is_primary DESC
        """, [provider['npi']])
        provider['clinics'] = [dict(row) for row in cur.fetchall()]

        # Get yearly data for each provider
        cur.execute("""
            SELECT data_year, total_claims, total_services, total_beneficiaries
            FROM provider_yearly_data
            WHERE npi = %s
            ORDER BY data_year DESC
        """, [provider['npi']])
        provider['yearly_data'] = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return jsonify({
        'providers': providers,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/states')
def get_states():
    """Get list of states for filter dropdown."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT cms_state
        FROM providers
        WHERE cms_state IS NOT NULL
        ORDER BY cms_state
    """)
    states = [row['cms_state'] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(states)

@app.route('/provider/<npi>')
def provider_detail(npi):
    """Provider detail page."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get provider info
    cur.execute("""
        SELECT p.*, e.patient_focus, e.search_status, e.search_date, e.search_notes
        FROM providers p
        LEFT JOIN provider_enrichment e ON p.npi = e.npi
        WHERE p.npi = %s
    """, [npi])
    provider = cur.fetchone()

    if not provider:
        return "Provider not found", 404

    # Get clinics
    cur.execute("""
        SELECT * FROM clinics WHERE npi = %s ORDER BY is_primary DESC
    """, [npi])
    clinics = [dict(row) for row in cur.fetchall()]

    # Get yearly data
    cur.execute("""
        SELECT * FROM provider_yearly_data WHERE npi = %s ORDER BY data_year DESC
    """, [npi])
    yearly_data = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('provider_detail.html', provider=dict(provider), clinics=clinics, yearly_data=yearly_data)

@app.route('/api/export')
def export_providers():
    """Export provider data to Excel."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get filter parameters (same as /api/providers)
    npi = request.args.get('npi', '').strip()
    name = request.args.get('name', '').strip()
    state = request.args.get('state', '').strip()
    patient_focus = request.args.get('patient_focus', '').strip()
    year = request.args.get('year', '').strip()
    hcpcs_code = request.args.get('hcpcs_code', '').strip()

    # Build query
    where_clauses = []
    params = []

    if npi:
        where_clauses.append("p.npi LIKE %s")
        params.append(f"%{npi}%")
    if name:
        where_clauses.append("(p.first_name ILIKE %s OR p.last_name ILIKE %s)")
        params.extend([f"%{name}%", f"%{name}%"])
    if state:
        where_clauses.append("p.cms_state = %s")
        params.append(state.upper())
    if patient_focus and patient_focus != 'all':
        where_clauses.append("e.patient_focus = %s")
        params.append(patient_focus)

    # Check if we need to filter by year or HCPCS code
    needs_yearly_filter = (year and year != 'all') or (hcpcs_code and hcpcs_code != 'all')

    if needs_yearly_filter:
        where_clauses_yearly = where_clauses.copy()
        params_yearly = params.copy()

        if year and year != 'all':
            where_clauses_yearly.append("y.data_year = %s")
            params_yearly.append(int(year))
        if hcpcs_code and hcpcs_code != 'all':
            where_clauses_yearly.append("y.hcpcs_code = %s")
            params_yearly.append(hcpcs_code)

        where_sql_yearly = " AND ".join(where_clauses_yearly) if where_clauses_yearly else "1=1"

        data_sql = f"""
            SELECT
                p.npi, p.first_name, p.last_name, p.credentials,
                p.cms_city, p.cms_state, p.specialty_desc,
                y.total_claims, y.total_services, y.total_beneficiaries, y.data_year,
                y.hcpcs_code,
                COALESCE(e.patient_focus, 'Pending') as patient_focus
            FROM providers p
            JOIN provider_yearly_data y ON p.npi = y.npi
            LEFT JOIN provider_enrichment e ON p.npi = e.npi
            WHERE {where_sql_yearly}
            ORDER BY y.total_claims DESC NULLS LAST
            LIMIT 10000
        """
        cur.execute(data_sql, params_yearly)
    else:
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        data_sql = f"""
            SELECT
                p.npi, p.first_name, p.last_name, p.credentials,
                p.cms_city, p.cms_state, p.specialty_desc,
                COALESCE(SUM(y.total_claims), 0) as total_claims,
                COALESCE(SUM(y.total_services), 0) as total_services,
                COALESCE(SUM(y.total_beneficiaries), 0) as total_beneficiaries,
                NULL as data_year,
                NULL as hcpcs_code,
                COALESCE(e.patient_focus, 'Pending') as patient_focus
            FROM providers p
            LEFT JOIN provider_yearly_data y ON p.npi = y.npi
            LEFT JOIN provider_enrichment e ON p.npi = e.npi
            WHERE {where_sql}
            GROUP BY p.npi, p.first_name, p.last_name, p.credentials,
                     p.cms_city, p.cms_state, p.specialty_desc, e.patient_focus
            ORDER BY total_claims DESC NULLS LAST
            LIMIT 10000
        """
        cur.execute(data_sql, params)

    providers = cur.fetchall()

    # Get clinics for each provider
    provider_clinics = {}
    if providers:
        npis = [p['npi'] for p in providers]
        cur.execute("""
            SELECT npi, clinic_name, street_address, city, state, zip
            FROM clinics
            WHERE npi = ANY(%s)
            ORDER BY npi, is_primary DESC
        """, [npis])
        for row in cur.fetchall():
            if row['npi'] not in provider_clinics:
                provider_clinics[row['npi']] = []
            provider_clinics[row['npi']].append(dict(row))

    cur.close()
    conn.close()

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Providers"

    # Headers
    headers = ['NPI', 'First Name', 'Last Name', 'Credentials', 'Specialty',
               'Patient Focus', 'Total Claims', 'Beneficiaries', 'City', 'State', 'Year', 'HCPCS Code',
               'Clinic Name', 'Clinic Address', 'Clinic City', 'Clinic State', 'Clinic Zip']
    ws.append(headers)

    # Style headers
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = ws.cell(row=1, column=col).font.copy(bold=True)

    # Data rows
    for p in providers:
        clinics = provider_clinics.get(p['npi'], [])
        if clinics:
            for i, clinic in enumerate(clinics):
                row = [
                    p['npi'] if i == 0 else '',
                    p['first_name'] if i == 0 else '',
                    p['last_name'] if i == 0 else '',
                    p['credentials'] if i == 0 else '',
                    p['specialty_desc'] if i == 0 else '',
                    p['patient_focus'] if i == 0 else '',
                    p['total_claims'] if i == 0 else '',
                    p['total_beneficiaries'] if i == 0 else '',
                    p['cms_city'] if i == 0 else '',
                    p['cms_state'] if i == 0 else '',
                    p['data_year'] if i == 0 else '',
                    p.get('hcpcs_code', '') if i == 0 else '',
                    clinic.get('clinic_name', ''),
                    clinic.get('street_address', ''),
                    clinic.get('city', ''),
                    clinic.get('state', ''),
                    clinic.get('zip', '')
                ]
                ws.append(row)
        else:
            row = [
                p['npi'], p['first_name'], p['last_name'], p['credentials'],
                p['specialty_desc'], p['patient_focus'], p['total_claims'],
                p['total_beneficiaries'], p['cms_city'], p['cms_state'], p['data_year'],
                p.get('hcpcs_code', ''),
                '', '', '', '', ''
            ]
            ws.append(row)

    # Adjust column widths
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    # Return as download
    year_str = year if year and year != 'all' else 'all_years'
    hcpcs_str = hcpcs_code if hcpcs_code and hcpcs_code != 'all' else 'all_codes'
    filename = f"cms_providers_{hcpcs_str}_{year_str}.xlsx"

    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# ============== SUPPLIER API ENDPOINTS ==============

# Competitor parent company IDs to exclude when toggle is enabled
# 2 = Electromed, 3 = Respiratory Technologies, 4 = Advanced Respiratory
COMPETITOR_PARENT_IDS = [2, 3, 4]

@app.route('/api/supplier/parent-companies')
def get_parent_companies():
    """Get list of parent companies with supplier counts."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pc.id, pc.name, pc.ticker, pc.headquarters_state, pc.website, pc.notes,
               COUNT(spm.supplier_npi) as supplier_count,
               COALESCE(SUM(y.total_claims), 0) as total_claims
        FROM parent_companies pc
        LEFT JOIN supplier_parent_map spm ON pc.id = spm.parent_company_id
        LEFT JOIN (SELECT npi, SUM(total_claims) as total_claims FROM supplier_yearly_data GROUP BY npi) y
            ON spm.supplier_npi = y.npi
        GROUP BY pc.id, pc.name, pc.ticker, pc.headquarters_state, pc.website, pc.notes
        ORDER BY total_claims DESC
    """)
    companies = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(companies)

@app.route('/api/supplier/parent-companies', methods=['POST'])
def update_supplier_parent():
    """Update a supplier's parent company."""
    data = request.get_json()
    supplier_npi = data.get('npi')
    parent_id = data.get('parent_company_id')

    if not supplier_npi or not parent_id:
        return jsonify({'error': 'NPI and parent_company_id required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO supplier_parent_map (supplier_npi, parent_company_id, confidence, source)
        VALUES (%s, %s, 'confirmed', 'Manual assignment')
        ON CONFLICT (supplier_npi) DO UPDATE SET
            parent_company_id = EXCLUDED.parent_company_id,
            source = 'Manual assignment'
        RETURNING *
    """, (supplier_npi, parent_id))
    result = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(result)

@app.route('/api/supplier/parent-companies/merge', methods=['POST'])
def merge_parent_companies():
    """Merge multiple parent companies into one target parent company."""
    data = request.get_json()
    target_id = data.get('target_id')
    source_ids = data.get('source_ids', [])

    if not target_id or not source_ids:
        return jsonify({'error': 'target_id and source_ids are required'}), 400

    # Remove target from sources if present
    source_ids = [sid for sid in source_ids if sid != target_id]

    if not source_ids:
        return jsonify({'error': 'No source IDs to merge'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    # Get target company name
    cur.execute("SELECT name FROM parent_companies WHERE id = %s", (target_id,))
    target = cur.fetchone()
    if not target:
        cur.close()
        conn.close()
        return jsonify({'error': 'Target parent company not found'}), 404

    # Update all supplier mappings from source companies to target
    cur.execute("""
        UPDATE supplier_parent_map
        SET parent_company_id = %s,
            source = CONCAT('Merged from parent ID ', parent_company_id::text)
        WHERE parent_company_id = ANY(%s)
    """, (target_id, source_ids))
    updated_count = cur.rowcount

    # Delete the source parent companies (keep target)
    cur.execute("DELETE FROM parent_companies WHERE id = ANY(%s)", (source_ids,))
    deleted_count = cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        'success': True,
        'target_id': target_id,
        'target_name': target['name'],
        'suppliers_updated': updated_count,
        'parents_deleted': deleted_count
    })

@app.route('/api/supplier/parent-companies/search')
def search_parent_companies():
    """Search parent companies by name for autocomplete."""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pc.id, pc.name, pc.ticker, COUNT(spm.supplier_npi) as supplier_count
        FROM parent_companies pc
        LEFT JOIN supplier_parent_map spm ON pc.id = spm.parent_company_id
        WHERE pc.name ILIKE %s
        GROUP BY pc.id, pc.name, pc.ticker
        ORDER BY supplier_count DESC
        LIMIT 20
    """, (f'%{query}%',))
    results = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(results)

@app.route('/api/supplier/parent-companies/duplicates')
def find_duplicate_parents():
    """Find potential duplicate parent companies based on similar names."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Find parent companies where names are similar (share first word or contain common substrings)
    cur.execute("""
        WITH parent_stats AS (
            SELECT pc.id, pc.name, pc.ticker,
                   COUNT(spm.supplier_npi) as supplier_count,
                   COALESCE(SUM(y.total_claims), 0) as total_claims,
                   SPLIT_PART(pc.name, ' ', 1) as first_word
            FROM parent_companies pc
            LEFT JOIN supplier_parent_map spm ON pc.id = spm.parent_company_id
            LEFT JOIN (SELECT npi, SUM(total_claims) as total_claims FROM supplier_yearly_data GROUP BY npi) y
                ON spm.supplier_npi = y.npi
            GROUP BY pc.id, pc.name, pc.ticker
        )
        SELECT first_word,
               json_agg(json_build_object(
                   'id', id,
                   'name', name,
                   'ticker', ticker,
                   'supplier_count', supplier_count,
                   'total_claims', total_claims
               ) ORDER BY total_claims DESC) as companies
        FROM parent_stats
        WHERE first_word != '' AND LENGTH(first_word) > 2
        GROUP BY first_word
        HAVING COUNT(*) > 1
        ORDER BY SUM(total_claims) DESC
        LIMIT 50
    """)
    results = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(results)

@app.route('/api/suppliers/grouped')
def get_suppliers_grouped():
    """Get supplier data aggregated by parent company."""
    conn = get_db_connection()
    cur = conn.cursor()

    year = request.args.get('year', '').strip()
    hcpcs_code = request.args.get('hcpcs_code', '').strip()
    exclude_competitors = request.args.get('exclude_competitors', '').lower() == 'true'

    # Build WHERE clause for yearly data
    where_clauses = []
    where_params = []
    having_params = []

    if year and year != 'all':
        where_clauses.append("y.data_year = %s")
        where_params.append(int(year))

    if hcpcs_code and hcpcs_code != 'all':
        where_clauses.append("y.hcpcs_code = %s")
        where_params.append(hcpcs_code)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Exclude competitors by parent company ID
    having_clause = ""
    if exclude_competitors:
        having_clause = "AND pc.id NOT IN %s"
        having_params.append(tuple(COMPETITOR_PARENT_IDS))

    query = f"""
        SELECT
            pc.id,
            pc.name,
            pc.ticker,
            COUNT(DISTINCT spm.supplier_npi) as supplier_count,
            COALESCE(SUM(y.total_claims), 0) as total_claims,
            COALESCE(SUM(y.total_beneficiaries), 0) as total_beneficiaries,
            COALESCE(SUM(y.total_services), 0) as total_services
        FROM parent_companies pc
        LEFT JOIN supplier_parent_map spm ON pc.id = spm.parent_company_id
        LEFT JOIN supplier_yearly_data y ON spm.supplier_npi = y.npi AND {where_sql}
        GROUP BY pc.id, pc.name, pc.ticker
        HAVING COALESCE(SUM(y.total_claims), 0) > 0 {having_clause}
        ORDER BY total_claims DESC
    """

    cur.execute(query, where_params + having_params)
    results = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return jsonify(results)

@app.route('/api/suppliers')
def get_suppliers():
    """API endpoint for supplier data with search and filtering."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get filter parameters
    npi = request.args.get('npi', '').strip()
    name = request.args.get('name', '').strip()
    state = request.args.get('state', '').strip()
    year = request.args.get('year', '').strip()
    hcpcs_code = request.args.get('hcpcs_code', '').strip()
    exclude_competitors = request.args.get('exclude_competitors', '').lower() == 'true'
    parent_company = request.args.get('parent_company', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    # Build query
    where_clauses = []
    params = []

    # Exclude competitors by parent company ID
    if exclude_competitors:
        where_clauses.append("spm.parent_company_id NOT IN %s")
        params.append(tuple(COMPETITOR_PARENT_IDS))

    # Filter by parent company
    if parent_company and parent_company != 'all':
        where_clauses.append("spm.parent_company_id = %s")
        params.append(int(parent_company))

    if npi:
        where_clauses.append("s.npi LIKE %s")
        params.append(f"%{npi}%")

    if name:
        where_clauses.append("(s.first_name ILIKE %s OR s.last_name ILIKE %s)")
        params.extend([f"%{name}%", f"%{name}%"])

    if state:
        where_clauses.append("s.state = %s")
        params.append(state.upper())

    if year and year != 'all':
        where_clauses.append("y.data_year = %s")
        params.append(int(year))

    if hcpcs_code and hcpcs_code != 'all':
        where_clauses.append("y.hcpcs_code = %s")
        params.append(hcpcs_code)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    needs_yearly_join = (year and year != 'all') or (hcpcs_code and hcpcs_code != 'all')

    if needs_yearly_join:
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM suppliers s
            LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
            JOIN supplier_yearly_data y ON s.npi = y.npi
            WHERE {where_sql}
        """
        cur.execute(count_sql, params)
        total = cur.fetchone()['count']

        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT
                s.npi,
                s.first_name,
                s.last_name,
                s.credentials,
                s.city,
                s.state,
                s.specialty_desc,
                s.entity_code,
                y.total_claims,
                y.total_services,
                y.total_beneficiaries,
                y.data_year,
                y.hcpcs_code,
                pc.id as parent_company_id,
                pc.name as parent_company_name
            FROM suppliers s
            LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
            LEFT JOIN parent_companies pc ON spm.parent_company_id = pc.id
            JOIN supplier_yearly_data y ON s.npi = y.npi
            WHERE {where_sql}
            ORDER BY y.total_claims DESC NULLS LAST, s.npi
            LIMIT %s OFFSET %s
        """
        cur.execute(data_sql, params + [per_page, offset])
    else:
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM suppliers s
            LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
            WHERE {where_sql}
        """
        cur.execute(count_sql, params)
        total = cur.fetchone()['count']

        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT
                s.npi,
                s.first_name,
                s.last_name,
                s.credentials,
                s.city,
                s.state,
                s.specialty_desc,
                s.entity_code,
                COALESCE(SUM(y.total_claims), 0) as total_claims,
                COALESCE(SUM(y.total_services), 0) as total_services,
                COALESCE(SUM(y.total_beneficiaries), 0) as total_beneficiaries,
                NULL as data_year,
                NULL as hcpcs_code,
                pc.id as parent_company_id,
                pc.name as parent_company_name
            FROM suppliers s
            LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
            LEFT JOIN parent_companies pc ON spm.parent_company_id = pc.id
            LEFT JOIN supplier_yearly_data y ON s.npi = y.npi
            WHERE {where_sql}
            GROUP BY s.npi, s.first_name, s.last_name, s.credentials,
                     s.city, s.state, s.specialty_desc, s.entity_code,
                     pc.id, pc.name
            ORDER BY total_claims DESC NULLS LAST, s.npi
            LIMIT %s OFFSET %s
        """
        cur.execute(data_sql, params + [per_page, offset])

    suppliers = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return jsonify({
        'suppliers': suppliers,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/supplier/states')
def get_supplier_states():
    """Get list of states for supplier filter dropdown."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT state
        FROM suppliers
        WHERE state IS NOT NULL
        ORDER BY state
    """)
    states = [row['state'] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(states)

@app.route('/api/supplier/years')
def get_supplier_years():
    """Get list of available years for suppliers."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT data_year
        FROM supplier_yearly_data
        WHERE data_year IS NOT NULL
        ORDER BY data_year DESC
    """)
    years = [row['data_year'] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(years)

@app.route('/api/supplier/aggregates')
def get_supplier_aggregates():
    """API endpoint for supplier aggregates with optional year and HCPCS code filter."""
    conn = get_db_connection()
    cur = conn.cursor()

    year = request.args.get('year', '').strip()
    hcpcs_code = request.args.get('hcpcs_code', '').strip()
    exclude_competitors = request.args.get('exclude_competitors', '').lower() == 'true'

    aggregates = {}

    # Build competitor exclusion filter (by parent company ID)
    competitor_filter = ""
    competitor_params = []
    if exclude_competitors:
        competitor_filter = " AND spm.parent_company_id NOT IN %s"
        competitor_params = [tuple(COMPETITOR_PARENT_IDS)]

    hcpcs_filter = ""
    hcpcs_params = []
    if hcpcs_code and hcpcs_code != 'all':
        hcpcs_filter = " AND y.hcpcs_code = %s"
        hcpcs_params = [hcpcs_code]

    if year and year != 'all':
        year = int(year)
        cur.execute(f"""
            SELECT COUNT(DISTINCT y.npi) as count
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE y.data_year = %s{hcpcs_filter}{competitor_filter}
        """, [year] + hcpcs_params + competitor_params)
        aggregates['total_suppliers'] = cur.fetchone()['count']

        cur.execute(f"""
            SELECT SUM(y.total_claims) as total
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE y.data_year = %s{hcpcs_filter}{competitor_filter}
        """, [year] + hcpcs_params + competitor_params)
        aggregates['total_claims'] = cur.fetchone()['total'] or 0

        cur.execute(f"""
            SELECT SUM(y.total_beneficiaries) as total
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE y.data_year = %s{hcpcs_filter}{competitor_filter}
        """, [year] + hcpcs_params + competitor_params)
        aggregates['total_beneficiaries'] = cur.fetchone()['total'] or 0

        cur.execute(f"""
            SELECT AVG(y.total_claims) as avg
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE y.data_year = %s AND y.total_claims IS NOT NULL{hcpcs_filter}{competitor_filter}
        """, [year] + hcpcs_params + competitor_params)
        avg_claims = cur.fetchone()['avg']
        aggregates['avg_claims'] = round(float(avg_claims), 1) if avg_claims else 0

        cur.execute(f"""
            SELECT s.state, COALESCE(SUM(y.total_claims), 0) as total_claims
            FROM supplier_yearly_data y
            JOIN suppliers s ON y.npi = s.npi
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE y.data_year = %s{hcpcs_filter}{competitor_filter}
            GROUP BY s.state
            ORDER BY total_claims DESC
            LIMIT 10
        """, [year] + hcpcs_params + competitor_params)
        aggregates['top_states'] = [dict(row) for row in cur.fetchall()]

    else:
        # Build base query with joins for competitor exclusion
        base_params = []

        hcpcs_condition = ""
        if hcpcs_code and hcpcs_code != 'all':
            hcpcs_condition = "AND y.hcpcs_code = %s"
            base_params.append(hcpcs_code)

        competitor_condition = ""
        if exclude_competitors:
            competitor_condition = "AND spm.parent_company_id NOT IN %s"
            base_params.append(tuple(COMPETITOR_PARENT_IDS))

        cur.execute(f"""
            SELECT COUNT(DISTINCT y.npi) as count
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE 1=1 {hcpcs_condition} {competitor_condition}
        """, base_params)
        aggregates['total_suppliers'] = cur.fetchone()['count']

        cur.execute(f"""
            SELECT SUM(y.total_claims) as total
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE 1=1 {hcpcs_condition} {competitor_condition}
        """, base_params)
        aggregates['total_claims'] = cur.fetchone()['total'] or 0

        cur.execute(f"""
            SELECT SUM(y.total_beneficiaries) as total
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE 1=1 {hcpcs_condition} {competitor_condition}
        """, base_params)
        aggregates['total_beneficiaries'] = cur.fetchone()['total'] or 0

        cur.execute(f"""
            SELECT AVG(y.total_claims) as avg
            FROM supplier_yearly_data y
            LEFT JOIN supplier_parent_map spm ON y.npi = spm.supplier_npi
            WHERE y.total_claims IS NOT NULL {hcpcs_condition} {competitor_condition}
        """, base_params)
        avg_claims = cur.fetchone()['avg']
        aggregates['avg_claims'] = round(float(avg_claims), 1) if avg_claims else 0

        # Top states query with competitor exclusion by parent company
        competitor_join_filter = "AND spm.parent_company_id NOT IN %s" if exclude_competitors else ""
        competitor_join_params = [tuple(COMPETITOR_PARENT_IDS)] if exclude_competitors else []

        if hcpcs_code and hcpcs_code != 'all':
            cur.execute(f"""
                SELECT s.state, COALESCE(SUM(y.total_claims), 0) as total_claims
                FROM suppliers s
                LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
                LEFT JOIN supplier_yearly_data y ON s.npi = y.npi AND y.hcpcs_code = %s
                WHERE 1=1 {competitor_join_filter}
                GROUP BY s.state
                ORDER BY total_claims DESC
                LIMIT 10
            """, [hcpcs_code] + competitor_join_params)
        else:
            cur.execute(f"""
                SELECT s.state, COALESCE(SUM(y.total_claims), 0) as total_claims
                FROM suppliers s
                LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
                LEFT JOIN supplier_yearly_data y ON s.npi = y.npi
                WHERE 1=1 {competitor_join_filter}
                GROUP BY s.state
                ORDER BY total_claims DESC
                LIMIT 10
            """, competitor_join_params)
        aggregates['top_states'] = [dict(row) for row in cur.fetchall()]

    # Top specialties (with competitor exclusion by parent company)
    if exclude_competitors:
        cur.execute("""
            SELECT s.specialty_desc, COUNT(*) as count
            FROM suppliers s
            LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
            WHERE s.specialty_desc IS NOT NULL AND spm.parent_company_id NOT IN %s
            GROUP BY s.specialty_desc
            ORDER BY count DESC
            LIMIT 10
        """, [tuple(COMPETITOR_PARENT_IDS)])
    else:
        cur.execute("""
            SELECT specialty_desc, COUNT(*) as count
            FROM suppliers
            WHERE specialty_desc IS NOT NULL
            GROUP BY specialty_desc
            ORDER BY count DESC
            LIMIT 10
        """)
    aggregates['top_specialties'] = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return jsonify(aggregates)

@app.route('/api/supplier/export')
def export_suppliers():
    """Export supplier data to Excel."""
    conn = get_db_connection()
    cur = conn.cursor()

    npi = request.args.get('npi', '').strip()
    name = request.args.get('name', '').strip()
    state = request.args.get('state', '').strip()
    year = request.args.get('year', '').strip()
    hcpcs_code = request.args.get('hcpcs_code', '').strip()
    exclude_competitors = request.args.get('exclude_competitors', '').lower() == 'true'
    parent_company = request.args.get('parent_company', '').strip()

    where_clauses = []
    params = []

    # Exclude competitors by parent company ID
    if exclude_competitors:
        where_clauses.append("spm.parent_company_id NOT IN %s")
        params.append(tuple(COMPETITOR_PARENT_IDS))

    # Filter by parent company
    if parent_company and parent_company != 'all':
        where_clauses.append("spm.parent_company_id = %s")
        params.append(int(parent_company))

    if npi:
        where_clauses.append("s.npi LIKE %s")
        params.append(f"%{npi}%")
    if name:
        where_clauses.append("(s.first_name ILIKE %s OR s.last_name ILIKE %s)")
        params.extend([f"%{name}%", f"%{name}%"])
    if state:
        where_clauses.append("s.state = %s")
        params.append(state.upper())

    needs_yearly_filter = (year and year != 'all') or (hcpcs_code and hcpcs_code != 'all')

    if needs_yearly_filter:
        if year and year != 'all':
            where_clauses.append("y.data_year = %s")
            params.append(int(year))
        if hcpcs_code and hcpcs_code != 'all':
            where_clauses.append("y.hcpcs_code = %s")
            params.append(hcpcs_code)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        data_sql = f"""
            SELECT
                s.npi, s.first_name, s.last_name, s.credentials,
                s.city, s.state, s.specialty_desc, s.entity_code,
                y.total_claims, y.total_services, y.total_beneficiaries, y.data_year,
                y.hcpcs_code,
                pc.name as parent_company_name
            FROM suppliers s
            LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
            LEFT JOIN parent_companies pc ON spm.parent_company_id = pc.id
            JOIN supplier_yearly_data y ON s.npi = y.npi
            WHERE {where_sql}
            ORDER BY y.total_claims DESC NULLS LAST
            LIMIT 10000
        """
        cur.execute(data_sql, params)
    else:
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        data_sql = f"""
            SELECT
                s.npi, s.first_name, s.last_name, s.credentials,
                s.city, s.state, s.specialty_desc, s.entity_code,
                COALESCE(SUM(y.total_claims), 0) as total_claims,
                COALESCE(SUM(y.total_services), 0) as total_services,
                COALESCE(SUM(y.total_beneficiaries), 0) as total_beneficiaries,
                NULL as data_year,
                NULL as hcpcs_code,
                pc.name as parent_company_name
            FROM suppliers s
            LEFT JOIN supplier_parent_map spm ON s.npi = spm.supplier_npi
            LEFT JOIN parent_companies pc ON spm.parent_company_id = pc.id
            LEFT JOIN supplier_yearly_data y ON s.npi = y.npi
            WHERE {where_sql}
            GROUP BY s.npi, s.first_name, s.last_name, s.credentials,
                     s.city, s.state, s.specialty_desc, s.entity_code, pc.name
            ORDER BY total_claims DESC NULLS LAST
            LIMIT 10000
        """
        cur.execute(data_sql, params)

    suppliers = cur.fetchall()
    cur.close()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Suppliers"

    headers = ['NPI', 'First Name', 'Last Name', 'Credentials', 'Specialty', 'Entity Type',
               'Total Claims', 'Beneficiaries', 'City', 'State', 'Year', 'HCPCS Code', 'Parent Company']
    ws.append(headers)

    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = ws.cell(row=1, column=col).font.copy(bold=True)

    for s in suppliers:
        entity_type = 'Organization' if s['entity_code'] == 'O' else 'Individual' if s['entity_code'] == 'I' else s['entity_code']
        row = [
            s['npi'], s['first_name'], s['last_name'], s['credentials'],
            s['specialty_desc'], entity_type, s['total_claims'],
            s['total_beneficiaries'], s['city'], s['state'], s['data_year'],
            s.get('hcpcs_code', ''), s.get('parent_company_name', '')
        ]
        ws.append(row)

    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    year_str = year if year and year != 'all' else 'all_years'
    hcpcs_str = hcpcs_code if hcpcs_code and hcpcs_code != 'all' else 'all_codes'
    filename = f"cms_suppliers_{hcpcs_str}_{year_str}.xlsx"

    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# ============== PARENT COMPANY DETAIL PAGE ==============

@app.route('/parent/<int:parent_id>')
def parent_detail(parent_id):
    """Parent company detail page showing all suppliers under it."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get parent company info
    cur.execute("""
        SELECT id, name, ticker, headquarters_state, website, notes
        FROM parent_companies
        WHERE id = %s
    """, [parent_id])
    parent = cur.fetchone()

    if not parent:
        cur.close()
        conn.close()
        return "Parent company not found", 404

    # Get aggregate stats
    cur.execute("""
        SELECT
            COUNT(DISTINCT spm.supplier_npi) as supplier_count,
            COUNT(DISTINCT s.state) as state_count,
            COALESCE(SUM(y.total_claims), 0) as total_claims,
            COALESCE(SUM(y.total_beneficiaries), 0) as total_beneficiaries,
            COALESCE(SUM(y.total_services), 0) as total_services,
            COALESCE(AVG(y.avg_medicare_payment), 0) as avg_payment
        FROM supplier_parent_map spm
        JOIN suppliers s ON spm.supplier_npi = s.npi
        LEFT JOIN supplier_yearly_data y ON s.npi = y.npi
        WHERE spm.parent_company_id = %s
    """, [parent_id])
    stats = dict(cur.fetchone())

    # Get all suppliers under this parent with full demographic info
    cur.execute("""
        SELECT
            s.npi,
            s.last_name,
            s.first_name,
            s.credentials,
            s.entity_code,
            s.street1,
            s.street2,
            s.city,
            s.state,
            s.zip,
            s.ruca_desc,
            s.specialty_desc,
            COALESCE(SUM(y.total_claims), 0) as total_claims,
            COALESCE(SUM(y.total_beneficiaries), 0) as total_beneficiaries,
            COALESCE(SUM(y.total_services), 0) as total_services,
            COALESCE(AVG(y.avg_medicare_payment), 0) as avg_payment,
            COALESCE(AVG(y.avg_submitted_charge), 0) as avg_charge
        FROM supplier_parent_map spm
        JOIN suppliers s ON spm.supplier_npi = s.npi
        LEFT JOIN supplier_yearly_data y ON s.npi = y.npi
        WHERE spm.parent_company_id = %s
        GROUP BY s.npi, s.last_name, s.first_name, s.credentials, s.entity_code,
                 s.street1, s.street2, s.city, s.state, s.zip, s.ruca_desc, s.specialty_desc
        ORDER BY total_claims DESC
    """, [parent_id])
    suppliers = [dict(row) for row in cur.fetchall()]

    # Get states breakdown
    cur.execute("""
        SELECT s.state, COUNT(*) as count, COALESCE(SUM(y.total_claims), 0) as claims
        FROM supplier_parent_map spm
        JOIN suppliers s ON spm.supplier_npi = s.npi
        LEFT JOIN supplier_yearly_data y ON s.npi = y.npi
        WHERE spm.parent_company_id = %s
        GROUP BY s.state
        ORDER BY claims DESC
    """, [parent_id])
    states = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('parent_detail.html',
                         parent=dict(parent),
                         stats=stats,
                         suppliers=suppliers,
                         states=states)

# ============== ADMIN API ENDPOINTS ==============

@app.route('/api/admin/versions')
def get_dataset_versions():
    """Get all known dataset versions."""
    conn = get_db_connection()
    cur = conn.cursor()

    # First check if the table exists, create if not
    cur.execute("""
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
        )
    """)
    conn.commit()

    # Check if we need to seed the data
    cur.execute("SELECT COUNT(*) as count FROM dataset_versions")
    if cur.fetchone()['count'] == 0:
        # Seed with known versions
        versions = [
            (2014, 'b834498f-158e-4152-9d63-13c946118033', 'CMS DME 2014'),
            (2015, 'af043480-65c0-436c-bd1b-3e45300a34a7', 'CMS DME 2015'),
            (2016, '862a02e8-e97b-41d0-a5d3-8f314db03d62', 'CMS DME 2016'),
            (2017, 'f3d2da82-4383-4c9a-b559-fb94c7d8ddfc', 'CMS DME 2017'),
            (2018, '55290cc6-c6e9-41e3-9896-dc8c4a35daf7', 'CMS DME 2018'),
            (2019, 'eb0019f6-791d-4065-ae4e-4761d2f6c9f2', 'CMS DME 2019'),
            (2020, '323df359-ceac-4525-a350-e2cd9eb128fe', 'CMS DME 2020'),
            (2021, '46ae675c-bc81-40ca-aa79-64da1c1ec9d9', 'CMS DME 2021'),
            (2022, '0dd53b4b-67ba-48c7-b8fa-fecbdfc83b70', 'CMS DME 2022'),
            (2023, '86b4807a-d63a-44be-bfdf-ffd398d5e623', 'CMS DME 2023'),
        ]
        for year, uuid, desc in versions:
            cur.execute("""
                INSERT INTO dataset_versions (data_year, dataset_uuid, description)
                VALUES (%s, %s, %s) ON CONFLICT (data_year) DO NOTHING
            """, (year, uuid, desc))
        conn.commit()

    # Get all versions with their status
    cur.execute("""
        SELECT dv.*,
               (SELECT COUNT(*) FROM provider_yearly_data WHERE data_year = dv.data_year) as db_record_count
        FROM dataset_versions dv
        ORDER BY data_year DESC
    """)
    versions = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()
    return jsonify(versions)

@app.route('/api/admin/versions', methods=['POST'])
def add_dataset_version():
    """Add or update a dataset version."""
    data = request.get_json()
    year = data.get('year')
    uuid = data.get('uuid')
    description = data.get('description', f'CMS DME {year}')

    if not year or not uuid:
        return jsonify({'error': 'Year and UUID are required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO dataset_versions (data_year, dataset_uuid, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (data_year) DO UPDATE SET
            dataset_uuid = EXCLUDED.dataset_uuid,
            description = EXCLUDED.description,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """, (year, uuid, description))

    result = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()

    return jsonify(result)

@app.route('/api/admin/refresh', methods=['POST'])
def refresh_data():
    """Trigger data refresh for specified years and HCPCS codes."""
    data = request.get_json()
    years = data.get('years', [])
    hcpcs_codes = data.get('hcpcs_codes', ['E0483', 'E0482'])
    run_enrichment = data.get('enrich', False)

    if not years:
        return jsonify({'error': 'At least one year is required'}), 400

    # Create job record
    conn = get_db_connection()
    cur = conn.cursor()

    # Create admin_jobs table if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_jobs (
            id SERIAL PRIMARY KEY,
            job_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            parameters JSONB,
            progress INTEGER DEFAULT 0,
            total_items INTEGER,
            result_message TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    cur.execute("""
        INSERT INTO admin_jobs (job_type, status, parameters, total_items)
        VALUES ('refresh', 'pending', %s, %s)
        RETURNING id
    """, (json.dumps({'years': years, 'hcpcs_codes': hcpcs_codes, 'enrich': run_enrichment}), len(years) * len(hcpcs_codes)))

    job_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()

    # Start background job
    thread = threading.Thread(target=run_refresh_job, args=(job_id, years, hcpcs_codes, run_enrichment))
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id, 'status': 'started'})

def run_refresh_job(job_id, years, hcpcs_codes, run_enrichment=False):
    """Background job to refresh data."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("UPDATE admin_jobs SET status = 'running', started_at = NOW() WHERE id = %s", (job_id,))
    conn.commit()

    progress = 0
    total = len(years) * len(hcpcs_codes)
    results = []
    affected_npis = set()  # Track NPIs added/updated during refresh

    try:
        # Get dataset UUIDs
        cur.execute("SELECT data_year, dataset_uuid FROM dataset_versions WHERE data_year = ANY(%s)", (years,))
        uuid_map = {row['data_year']: row['dataset_uuid'] for row in cur.fetchall()}

        for year in years:
            if year not in uuid_map:
                results.append(f"Year {year}: No UUID found, skipped")
                continue

            uuid = uuid_map[year]

            for hcpcs_code in hcpcs_codes:
                try:
                    records = download_cms_data(year, uuid, hcpcs_code)
                    if records:
                        new_providers, yearly_records, npis = load_records_to_db(records, year, hcpcs_code, conn, return_npis=True)
                        affected_npis.update(npis)
                        results.append(f"{hcpcs_code} {year}: {len(records)} records, {new_providers} new providers")

                        # Update last_refreshed
                        cur.execute("""
                            UPDATE dataset_versions
                            SET last_refreshed = NOW(), record_count = %s
                            WHERE data_year = %s
                        """, (len(records), year))
                        conn.commit()
                    else:
                        results.append(f"{hcpcs_code} {year}: No data returned")
                except Exception as e:
                    results.append(f"{hcpcs_code} {year}: Error - {str(e)}")

                progress += 1
                cur.execute("UPDATE admin_jobs SET progress = %s WHERE id = %s", (progress, job_id))
                conn.commit()
                time.sleep(1)  # Rate limiting

        # Run enrichment on affected providers if requested
        if run_enrichment and affected_npis:
            results.append(f"\nStarting enrichment for {len(affected_npis)} providers...")
            cur.execute("UPDATE admin_jobs SET result_message = %s WHERE id = %s", ('\n'.join(results), job_id))
            conn.commit()

            enriched, failed = enrich_providers(list(affected_npis), conn, cur, job_id)
            results.append(f"Enrichment complete: {enriched} enriched, {failed} failed")

        cur.execute("""
            UPDATE admin_jobs
            SET status = 'completed', completed_at = NOW(), result_message = %s
            WHERE id = %s
        """, ('\n'.join(results), job_id))

    except Exception as e:
        cur.execute("""
            UPDATE admin_jobs
            SET status = 'failed', completed_at = NOW(), result_message = %s
            WHERE id = %s
        """, (str(e), job_id))

    conn.commit()
    cur.close()
    conn.close()

def enrich_providers(npis, conn, cur, job_id=None):
    """Enrich a specific list of providers."""
    NPI_REGISTRY_URL = "https://npiregistry.cms.hhs.gov/api/"
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 CMS-Analysis-Tool/1.0'})

    enriched = 0
    failed = 0

    for npi in npis:
        try:
            # Query NPI Registry
            response = session.get(NPI_REGISTRY_URL, params={'number': npi, 'version': '2.1'}, timeout=30)
            response.raise_for_status()
            data = response.json()

            patient_focus = 'Unknown'
            if data.get('result_count', 0) > 0:
                result = data['results'][0]

                # Extract clinic info
                addresses = result.get('addresses', [])
                for addr in addresses:
                    if addr.get('address_purpose') == 'LOCATION':
                        cur.execute("""
                            INSERT INTO clinics (npi, street_address, city, state, zip, phone, source_name, is_primary)
                            VALUES (%s, %s, %s, %s, %s, %s, 'NPI Registry', TRUE)
                            ON CONFLICT DO NOTHING
                        """, (
                            npi,
                            addr.get('address_1', ''),
                            addr.get('city', ''),
                            addr.get('state', ''),
                            addr.get('postal_code', '')[:5] if addr.get('postal_code') else '',
                            addr.get('telephone_number', ''),
                        ))

                # Determine patient focus from taxonomy
                taxonomies = result.get('taxonomies', [])
                for tax in taxonomies:
                    desc = (tax.get('desc', '') or '').lower()
                    if 'pediatric' in desc or 'child' in desc:
                        patient_focus = 'Pediatric' if patient_focus == 'Unknown' else 'Both'
                    elif 'adult' in desc or 'geriatric' in desc:
                        patient_focus = 'Adult' if patient_focus == 'Unknown' else 'Both'

            # Update enrichment status
            cur.execute("""
                UPDATE provider_enrichment
                SET search_status = 'completed', patient_focus = %s, search_date = NOW()
                WHERE npi = %s
            """, (patient_focus, npi))
            conn.commit()
            enriched += 1

        except Exception as e:
            cur.execute("""
                UPDATE provider_enrichment
                SET search_status = 'failed', search_notes = %s, search_date = NOW()
                WHERE npi = %s
            """, (str(e)[:200], npi))
            conn.commit()
            failed += 1

        time.sleep(1)  # Rate limiting

    return enriched, failed

def download_cms_data(year, uuid, hcpcs_code):
    """Download CMS data for a specific year and HCPCS code."""
    api_url = f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"
    all_records = []
    offset = 0
    page_size = 25
    max_records = 5000

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 CMS-Analysis-Tool/1.0',
        'Accept': 'application/json'
    })

    while offset < max_records:
        params = {
            "filter[HCPCS_CD]": hcpcs_code,
            "size": page_size,
            "offset": offset
        }

        response = session.get(api_url, params=params, timeout=180)
        response.raise_for_status()
        page_data = response.json()

        if not page_data:
            break

        all_records.extend(page_data)

        if len(page_data) < page_size:
            break

        offset += page_size
        time.sleep(1)

    return all_records

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

def load_records_to_db(records, year, hcpcs_code, conn, return_npis=False):
    """Load records into the database."""
    if not records:
        return (0, 0, []) if return_npis else (0, 0)

    cur = conn.cursor()
    new_providers = 0
    yearly_records = 0
    processed_npis = []

    for record in records:
        npi = record.get('Rfrg_NPI')
        if not npi:
            continue

        processed_npis.append(npi)

        # Insert or update provider
        cur.execute("""
            INSERT INTO providers (
                npi, last_name, first_name, middle_initial, credentials, entity_code,
                cms_street1, cms_street2, cms_city, cms_state, cms_zip, cms_country,
                specialty_code, specialty_desc, specialty_source,
                hcpcs_code, hcpcs_desc
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (npi) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING (xmax = 0) as inserted
        """, (
            npi,
            record.get('Rfrg_Prvdr_Last_Name_Org'),
            record.get('Rfrg_Prvdr_First_Name'),
            record.get('Rfrg_Prvdr_MI'),
            record.get('Rfrg_Prvdr_Crdntls'),
            record.get('Rfrg_Prvdr_Ent_Cd'),
            record.get('Rfrg_Prvdr_St1'),
            record.get('Rfrg_Prvdr_St2'),
            record.get('Rfrg_Prvdr_City'),
            record.get('Rfrg_Prvdr_State_Abrvtn'),
            record.get('Rfrg_Prvdr_Zip5'),
            record.get('Rfrg_Prvdr_Cntry'),
            record.get('Rfrg_Prvdr_Spclty_Cd'),
            record.get('Rfrg_Prvdr_Spclty_Desc'),
            record.get('Rfrg_Prvdr_Spclty_Srce'),
            record.get('HCPCS_CD'),
            record.get('HCPCS_Desc'),
        ))

        result = cur.fetchone()
        if result and result['inserted']:
            new_providers += 1

        # Insert yearly billing data
        cur.execute("""
            INSERT INTO provider_yearly_data (
                npi, data_year, hcpcs_code,
                total_suppliers, total_claims, total_services, total_beneficiaries,
                avg_submitted_charge, avg_medicare_allowed, avg_medicare_payment, avg_medicare_standardized,
                supplier_rental_ind
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (npi, data_year, hcpcs_code) DO UPDATE SET
                total_claims = EXCLUDED.total_claims,
                total_beneficiaries = EXCLUDED.total_beneficiaries,
                updated_at = CURRENT_TIMESTAMP
        """, (
            npi, year, hcpcs_code,
            safe_int(record.get('Tot_Suplrs')),
            safe_int(record.get('Tot_Suplr_Clms')),
            safe_int(record.get('Tot_Suplr_Srvcs')),
            safe_int(record.get('Tot_Suplr_Benes')),
            safe_float(record.get('Avg_Suplr_Sbmtd_Chrg')),
            safe_float(record.get('Avg_Suplr_Mdcr_Alowd_Amt')),
            safe_float(record.get('Avg_Suplr_Mdcr_Pymt_Amt')),
            safe_float(record.get('Avg_Suplr_Mdcr_Stdzd_Amt')),
            record.get('Suplr_Rentl_Ind'),
        ))
        if cur.rowcount > 0:
            yearly_records += 1

    conn.commit()

    # Create enrichment records for new NPIs
    cur.execute("""
        INSERT INTO provider_enrichment (npi, search_status)
        SELECT npi, 'pending' FROM providers
        WHERE npi NOT IN (SELECT npi FROM provider_enrichment)
        ON CONFLICT (npi) DO NOTHING
    """)
    conn.commit()
    cur.close()

    if return_npis:
        return new_providers, yearly_records, processed_npis
    return new_providers, yearly_records

# ============== SUPPLIER ADMIN ENDPOINTS ==============

@app.route('/api/admin/supplier/versions')
def get_supplier_versions():
    """Get all known supplier dataset versions."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
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
        )
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) as count FROM supplier_dataset_versions")
    if cur.fetchone()['count'] == 0:
        cur.execute("""
            INSERT INTO supplier_dataset_versions (data_year, dataset_uuid, description)
            VALUES (2023, '1746a83e-bb65-4300-8e02-21edbab77c6b', 'CMS DME Supplier 2023')
            ON CONFLICT (data_year) DO NOTHING
        """)
        conn.commit()

    cur.execute("""
        SELECT dv.*,
               (SELECT COUNT(*) FROM supplier_yearly_data WHERE data_year = dv.data_year) as db_record_count
        FROM supplier_dataset_versions dv
        ORDER BY data_year DESC
    """)
    versions = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()
    return jsonify(versions)

@app.route('/api/admin/supplier/versions', methods=['POST'])
def add_supplier_version():
    """Add or update a supplier dataset version."""
    data = request.get_json()
    year = data.get('year')
    uuid = data.get('uuid')
    description = data.get('description', f'CMS DME Supplier {year}')

    if not year or not uuid:
        return jsonify({'error': 'Year and UUID are required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO supplier_dataset_versions (data_year, dataset_uuid, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (data_year) DO UPDATE SET
            dataset_uuid = EXCLUDED.dataset_uuid,
            description = EXCLUDED.description,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """, (year, uuid, description))

    result = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()

    return jsonify(result)

@app.route('/api/admin/supplier/refresh', methods=['POST'])
def refresh_supplier_data():
    """Trigger supplier data refresh for specified years and HCPCS codes."""
    data = request.get_json()
    years = data.get('years', [])
    hcpcs_codes = data.get('hcpcs_codes', ['E0483', 'E0482'])
    run_enrichment = data.get('enrich', False)

    if not years:
        return jsonify({'error': 'At least one year is required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO admin_jobs (job_type, status, parameters, total_items)
        VALUES ('supplier_refresh', 'pending', %s, %s)
        RETURNING id
    """, (json.dumps({'years': years, 'hcpcs_codes': hcpcs_codes, 'enrich': run_enrichment}), len(years) * len(hcpcs_codes)))

    job_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()

    thread = threading.Thread(target=run_supplier_refresh_job, args=(job_id, years, hcpcs_codes, run_enrichment))
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id, 'status': 'started'})

def run_supplier_refresh_job(job_id, years, hcpcs_codes, run_enrichment=False):
    """Background job to refresh supplier data."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("UPDATE admin_jobs SET status = 'running', started_at = NOW() WHERE id = %s", (job_id,))
    conn.commit()

    progress = 0
    total = len(years) * len(hcpcs_codes)
    results = []
    affected_npis = set()

    try:
        cur.execute("SELECT data_year, dataset_uuid FROM supplier_dataset_versions WHERE data_year = ANY(%s)", (years,))
        uuid_map = {row['data_year']: row['dataset_uuid'] for row in cur.fetchall()}

        for year in years:
            if year not in uuid_map:
                results.append(f"Year {year}: No UUID found, skipped")
                continue

            uuid = uuid_map[year]

            for hcpcs_code in hcpcs_codes:
                try:
                    records = download_supplier_data(year, uuid, hcpcs_code)
                    if records:
                        new_suppliers, yearly_records, npis = load_supplier_records(records, year, hcpcs_code, conn)
                        affected_npis.update(npis)
                        results.append(f"{hcpcs_code} {year}: {len(records)} records, {new_suppliers} new suppliers")

                        cur.execute("""
                            UPDATE supplier_dataset_versions
                            SET last_refreshed = NOW(), record_count = %s
                            WHERE data_year = %s
                        """, (len(records), year))
                        conn.commit()
                    else:
                        results.append(f"{hcpcs_code} {year}: No data returned")
                except Exception as e:
                    results.append(f"{hcpcs_code} {year}: Error - {str(e)}")

                progress += 1
                cur.execute("UPDATE admin_jobs SET progress = %s WHERE id = %s", (progress, job_id))
                conn.commit()
                time.sleep(1)

        if run_enrichment and affected_npis:
            results.append(f"\nStarting enrichment for {len(affected_npis)} suppliers...")
            cur.execute("UPDATE admin_jobs SET result_message = %s WHERE id = %s", ('\n'.join(results), job_id))
            conn.commit()
            enriched, failed = enrich_suppliers(list(affected_npis), conn, cur)
            results.append(f"Enrichment complete: {enriched} enriched, {failed} failed")

        cur.execute("""
            UPDATE admin_jobs
            SET status = 'completed', completed_at = NOW(), result_message = %s
            WHERE id = %s
        """, ('\n'.join(results), job_id))

    except Exception as e:
        cur.execute("""
            UPDATE admin_jobs
            SET status = 'failed', completed_at = NOW(), result_message = %s
            WHERE id = %s
        """, (str(e), job_id))

    conn.commit()
    cur.close()
    conn.close()

def download_supplier_data(year, uuid, hcpcs_code):
    """Download supplier data for a specific year and HCPCS code."""
    api_url = f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"
    all_records = []
    offset = 0
    page_size = 25
    max_records = 5000

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 CMS-Analysis-Tool/1.0',
        'Accept': 'application/json'
    })

    while offset < max_records:
        params = {
            "filter[HCPCS_Cd]": hcpcs_code,
            "size": page_size,
            "offset": offset
        }

        response = session.get(api_url, params=params, timeout=180)
        response.raise_for_status()
        page_data = response.json()

        if not page_data:
            break

        all_records.extend(page_data)

        if len(page_data) < page_size:
            break

        offset += page_size
        time.sleep(1)

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

    cur.execute("""
        INSERT INTO supplier_enrichment (npi, search_status)
        SELECT npi, 'pending' FROM suppliers
        WHERE npi NOT IN (SELECT npi FROM supplier_enrichment)
        ON CONFLICT (npi) DO NOTHING
    """)
    conn.commit()
    cur.close()

    return new_suppliers, yearly_records, processed_npis

def enrich_suppliers(npis, conn, cur):
    """Enrich suppliers with NPI Registry data."""
    NPI_REGISTRY_URL = "https://npiregistry.cms.hhs.gov/api/"
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 CMS-Analysis-Tool/1.0'})

    enriched = 0
    failed = 0

    for npi in npis:
        try:
            response = session.get(NPI_REGISTRY_URL, params={'number': npi, 'version': '2.1'}, timeout=30)
            response.raise_for_status()
            data = response.json()

            business_name = None
            if data.get('result_count', 0) > 0:
                result = data['results'][0]
                basic = result.get('basic', {})
                business_name = basic.get('organization_name') or basic.get('name')

            cur.execute("""
                UPDATE supplier_enrichment
                SET search_status = 'completed', business_name = %s, search_date = NOW()
                WHERE npi = %s
            """, (business_name, npi))
            conn.commit()
            enriched += 1

        except Exception as e:
            cur.execute("""
                UPDATE supplier_enrichment
                SET search_status = 'failed', search_notes = %s, search_date = NOW()
                WHERE npi = %s
            """, (str(e)[:200], npi))
            conn.commit()
            failed += 1

        time.sleep(1)

    return enriched, failed

@app.route('/api/admin/jobs')
def get_jobs():
    """Get recent admin jobs."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM admin_jobs
        ORDER BY created_at DESC
        LIMIT 20
    """)
    jobs = [dict(row) for row in cur.fetchall()]

    # Convert datetime objects to strings
    for job in jobs:
        for key in ['started_at', 'completed_at', 'created_at']:
            if job.get(key):
                job[key] = job[key].isoformat()

    cur.close()
    conn.close()
    return jsonify(jobs)

@app.route('/api/admin/jobs/<int:job_id>')
def get_job(job_id):
    """Get a specific job status."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM admin_jobs WHERE id = %s", (job_id,))
    job = cur.fetchone()

    cur.close()
    conn.close()

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    job = dict(job)
    for key in ['started_at', 'completed_at', 'created_at']:
        if job.get(key):
            job[key] = job[key].isoformat()

    return jsonify(job)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
