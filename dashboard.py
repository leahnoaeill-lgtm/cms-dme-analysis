#!/usr/bin/env python3
"""
CMS DME Analysis Dashboard
Web-based interface for browsing and analyzing provider data
"""

from flask import Flask, render_template, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

DB_CONFIG = {
    "dbname": "cms_analysis",
    "user": "postgres",
    "host": "localhost",
    "port": 5432
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

    return render_template('dashboard.html', aggregates=aggregates, available_years=available_years)

@app.route('/api/aggregates')
def get_aggregates():
    """API endpoint for aggregates with optional year filter."""
    conn = get_db_connection()
    cur = conn.cursor()

    year = request.args.get('year', '').strip()

    aggregates = {}

    if year and year != 'all':
        year = int(year)
        # Year-specific aggregates from yearly data
        cur.execute("""
            SELECT COUNT(DISTINCT npi) as count FROM provider_yearly_data WHERE data_year = %s
        """, [year])
        aggregates['total_providers'] = cur.fetchone()['count']

        cur.execute("""
            SELECT SUM(total_claims) as total FROM provider_yearly_data WHERE data_year = %s
        """, [year])
        aggregates['total_claims'] = cur.fetchone()['total'] or 0

        cur.execute("""
            SELECT AVG(total_claims) as avg FROM provider_yearly_data
            WHERE data_year = %s AND total_claims IS NOT NULL
        """, [year])
        avg_claims = cur.fetchone()['avg']
        aggregates['avg_claims'] = round(float(avg_claims), 1) if avg_claims else 0

        # Top states by claims for selected year
        cur.execute("""
            SELECT p.cms_state, COALESCE(SUM(y.total_claims), 0) as total_claims
            FROM provider_yearly_data y
            JOIN providers p ON y.npi = p.npi
            WHERE y.data_year = %s
            GROUP BY p.cms_state
            ORDER BY total_claims DESC
            LIMIT 10
        """, [year])
        aggregates['top_states'] = [dict(row) for row in cur.fetchall()]

    else:
        # All years combined
        cur.execute("SELECT COUNT(*) as count FROM providers")
        aggregates['total_providers'] = cur.fetchone()['count']

        cur.execute("SELECT SUM(total_claims) as total FROM provider_yearly_data")
        aggregates['total_claims'] = cur.fetchone()['total'] or 0

        cur.execute("SELECT AVG(total_claims) as avg FROM provider_yearly_data WHERE total_claims IS NOT NULL")
        avg_claims = cur.fetchone()['avg']
        aggregates['avg_claims'] = round(float(avg_claims), 1) if avg_claims else 0

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

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Use yearly data if year is specified
    if year and year != 'all':
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
                y.data_year,
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
                NULL as data_year,
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
            SELECT data_year, total_claims, total_services
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
