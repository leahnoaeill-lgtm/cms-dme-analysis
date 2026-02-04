# Session Handover: E0469 Payer Policy Analysis

## Project Overview

Building a comprehensive spreadsheet of US insurance payers with **explicit E0469 policies** - payers that specifically mention HCPCS code E0469 in their published policy documents.

## HCPCS Code E0469

- **Description**: Lung expansion airway clearance, continuous high frequency oscillation, and nebulization device
- **Effective Date**: October 1, 2024 (NEW code - only ~16 months old)
- **Related Code**: A7021 (monthly disposables for E0469)
- **Devices**: Volara, BiWaze Clear, MetaNeb (OLE therapy devices)
- **Key Finding**: Most payers consider OLE devices investigational/experimental
- **Medicare Status**: No LCD/NCD exists - Noridian confirmed "At this time there is no established coverage criteria for this HCPCS code"

## Current State

### Files

| File | Purpose |
|------|---------|
| `/Users/leahnoaeill/Downloads/MyClaude/data_export/E0469_Explicit_Payer_Policies.py` | Python script that generates the Excel spreadsheet |
| `/Users/leahnoaeill/Downloads/MyClaude/data_export/E0469_Explicit_Payer_Policies.xlsx` | Output spreadsheet with payer data |

### Spreadsheet Statistics (as of Feb 4, 2026)

- **Total Payers**: 63 with explicit E0469 policies
- **NOT COVERED** (explicit language): 4
- **Investigational/Experimental**: ~10
- **Covered with Criteria**: 16
- **Partial Coverage** (OLE unproven, HFCWO may be covered): 20
- **Case-by-Case** (No LCD): 4
- **Case Review - Prior Auth Needed**: 2
- **Prior Auth Required** (various): 7

### Payer Data Structure

```python
{
    "name": "Payer Name",
    "type": "Commercial/BCBS/Medicaid/Medicare MAC/etc",
    "coverage": "Covered/Not Covered/Investigational/Partial/Case-by-Case",
    "prior_auth": "Yes/No/N/A",
    "investigational": "Yes/No/Not Specified",
    "not_med_necessary": "Yes/No/Not Specified",
    "date": "Policy effective date",
    "policy_num": "Policy number/ID",
    "notes": "Details about E0469 coverage",
    "source": "URL to policy document"
}
```

### Color Coding in Spreadsheet

- **Green**: Covered with criteria
- **Yellow**: Partial coverage or investigational status noted
- **Red**: Not covered or investigational/experimental
- **Blue**: Case-by-case review (no LCD)

## Payers Currently Included (50 Total)

### Medicare/CMS (4)
- CMS DMEPOS Fee Schedule
- Noridian Medicare (JA DME)
- Noridian Medicare (JD DME)
- CGS Medicare (JB DME)

### Commercial Plans (10)
- UnitedHealthcare Commercial
- UnitedHealthcare Individual Exchange
- UMR (UHC TPA)
- Surest (UHC)
- UnitedHealthcare Oxford
- Cigna
- Humana Commercial
- Humana Medicare Advantage
- Aetna
- Kaiser Permanente WA (Non-Medicare)

### BCBS Plans (12)
- Blue Cross Blue Shield Florida
- Premera Blue Cross
- Blue Cross NC
- BCBS Kansas
- BCBS Massachusetts
- Excellus BCBS (NY)
- Anthem Blue Cross Connecticut
- Kaiser Permanente WA (Medicare)
- BCBS Rhode Island (Not medically necessary for Commercial)
- Wellmark BCBS (Iowa/South Dakota) (Investigational)
- **Blue Cross Blue Shield of Michigan** (NEW - Investigational, per DIFS external review case)

### Medicaid Programs (16)
- Minnesota MHCP (NOT COVERED)
- California Medi-Cal (Covered with limits - 1 per 5 years)
- Humana Medicaid (NOT COVERED)
- UHC Community Plan - Multiple states:
  - New Jersey, Louisiana, North Carolina, Pennsylvania
  - Tennessee, Kentucky, Texas, Arizona
  - Michigan, Ohio, Virginia, Wisconsin

### Regional Plans (8)
- Medica (NOT COVERED - Investigational)
- HealthPartners (NOT COVERED - Investigational)
- Geisinger Health Plan
- Univera Healthcare (NY)
- Health Plan of Nevada
- Sierra Health and Life
- Rocky Mountain Health Plans
- EmblemHealth (NY)
- **Moda Health (Oregon/Alaska)** (NEW - Covered with Prior Auth)

### Reference
- BiWaze Clear Reimbursement Guide (ABM) - Manufacturer reference

## Key Findings

1. **No Medicare LCD/NCD**: CMS has no specific coverage determination - claims reviewed case-by-case
2. **Most Consider OLE Investigational**: Volara, BiWaze Clear devices largely considered experimental
3. **UHC Most Comprehensive**: UnitedHealthcare explicitly lists E0469 across all product lines
4. **New Code Challenge**: E0469 effective 10/1/2024 - many payers haven't published explicit policies yet
5. **HFCWO vs OLE**: Many payers cover HFCWO (E0483) for CF/bronchiectasis but NOT OLE devices (E0469)
6. **Anthem Removed E0469**: Anthem's policy revision (05/08/2025) explicitly removed E0469 from coverage
7. **State Medicaids Lag**: Most state Medicaid programs haven't published explicit E0469 policies yet

## Coverage Terminology Distinctions

**Important**: These terms have different meanings for coverage determination:

| Term | Meaning | Appeal Potential |
|------|---------|------------------|
| **NOT COVERED** | Categorical exclusion from benefits | Low - explicit exclusion |
| **Investigational/Experimental** | Insufficient evidence for coverage | Medium - may change with new evidence |
| **Not Medically Necessary** | Does not meet medical necessity criteria | Higher - case-by-case review possible |
| **Case Review - Prior Auth Needed** | Requires prior authorization review | Higher - individual case determination |

When reviewing policies, use the exact language from the policy document rather than interpreting as "NOT COVERED"

## Payers Searched But No Explicit E0469 Found

### BCBS Plans
- BCBS Texas
- BCBS Illinois
- BCBS Tennessee
- BCBS Arkansas
- BCBS Idaho
- BCBS Montana
- Horizon BCBS NJ
- Empire BCBS
- Independence Blue Cross
- Carefirst BCBS (MD/DC/VA)

### Commercial/Regional
- Oscar Health
- Bright Health
- Clover Health
- First Health
- ConnectiCare
- Sentara Health Plans
- Highmark (PA) - policy covers E0483 but not E0469
- Harvard Pilgrim / Tufts / Point32Health
- Medical Mutual (OH)
- Priority Health
- SelectHealth
- Blue Shield California
- Anthem California

### Medicaid MCOs
- Molina Healthcare
- Centene / WellCare
- Amerigroup / Elevance - CG-DME-43 covers E0483, not E0469
- Superior Health Plan (TX)

### State Medicaid Programs (Fee-for-Service)
- Pennsylvania DHS
- Ohio ODM
- Michigan MDHHS
- North Carolina (NCTracks)
- Virginia DMAS
- New Jersey FamilyCare
- Arizona AHCCCS
- Washington Apple Health
- Kentucky DMS
- Louisiana LDH
- Indiana FSSA
- Connecticut DSS/HUSKY
- Nevada DHCFP
- Maryland
- Wisconsin ForwardHealth
- South Carolina SCDHHS
- Oregon OHP
- Illinois HFS
- Georgia DCH
- Texas HHSC
- Florida AHCA

### Federal
- Tricare
- VA

### Workers' Compensation
- Federal OWCP
- State WC programs (NY, CA, TX)

## Why So Few State Medicaid Policies Found

1. **Code is very new** - Only effective 10/1/2024 (~16 months)
2. **Fee schedules in PDF/Excel** - Not web-indexed or searchable
3. **No established Medicare LCD** - States often follow Medicare guidance
4. **Claims reviewed case-by-case** - No formal policy published
5. **MCOs handle coverage** - Most Medicaid members in managed care, not FFS

## How to Continue

### To Add More Payers

1. Search for payers with explicit E0469 mentions:
   ```
   "E0469" [payer name] policy
   "E0469" "A7021" [payer name]
   "E0469" Medicaid [state] policy
   "E0469" "oscillation lung expansion" policy
   "E0469" "investigational" OR "not covered" payer
   ```

2. Edit the Python file to add new payer entries to `payer_data` list

3. Run the script to regenerate the spreadsheet:
   ```bash
   cd /Users/leahnoaeill/Downloads/MyClaude
   python3 data_export/E0469_Explicit_Payer_Policies.py
   ```

### Suggested Search Targets

- Additional Medicare Advantage plans with prior auth lists
- Remaining BCBS state plans (check medical policy portals directly)
- Large employer self-funded plans
- State employee health plans

## Useful Policy URLs Found

| Payer | Policy URL |
|-------|------------|
| Medica | https://partner.medica.com/-/media/documents/provider/coverage-policies/volara-oscillation-and-lung-expansion-cp.pdf |
| HealthPartners | https://www.healthpartners.com/ucm/groups/public/@hp/@public/@cc/documents/documents/aentry_045636.pdf |
| BCBS Florida | https://mcgs.bcbsfl.com/MCG?mcgId=09-E0000-28 |
| Premera | https://www.premera.com/medicalpolicies-individual/1.01.539.pdf |
| Blue Cross NC | https://www.bluecrossnc.com/providers/policies-guidelines-codes/commercial/home-health-dme/updates/oscillatory-devices-for-treatment-of-respiratory-conditions |
| Kaiser WA | https://wa-provider.kaiserpermanente.org/static/pdf/hosting/clinical/criteria/pdf/hfcwo.pdf |
| Moda Health | https://www.modahealth.com/-/media/modahealth/shared/provider/prior-authorization/pre-auth-list-commercial.pdf |
| Wellmark BCBS | https://digital-assets.wellmark.com/adobe/assets/urn:aaid:aem:8aa2f47a-61ff-4beb-9f1b-219c24adb04e/original/as/Airway-Clearance-Devices.pdf |
| BCBS RI | https://www.bcbsri.com/providers/update/additional-hcpcs-level-ii-code-changes-and-modifier-changes-4 |
| BCBS Michigan | https://www.michigan.gov/difs/-/media/Project/Websites/difs/PRIRA/2024/September/BCBSM_227614.pdf |

## User's Original Request

> "yes keep searching and ensure the spreadsheet only has payers with policies who have only E0469 included with explicit E0469 policies"

The user wants ONLY payers that explicitly mention E0469 in their published policies - no inferred or assumed coverage.

## PDF Extraction Script

A Python script was created to enable Claude to read PDFs directly via Bash, solving the limitation where compressed PDFs returned garbled binary data through WebFetch.

### Files Created

| File | Purpose |
|------|---------|
| `/Users/leahnoaeill/Downloads/MyClaude/mcp_pdf_server/pdf_extractor.py` | Script that extracts text from PDF URLs |
| `/Users/leahnoaeill/Downloads/MyClaude/mcp_pdf_server/requirements.txt` | Python dependencies (PyMuPDF) |

### Setup (Already Completed)

```bash
# Install PyMuPDF (already done)
pip3 install PyMuPDF
```

### Usage

Claude can call this script via Bash to read PDFs:

```bash
# Search for a specific term (most useful for policy searches)
python3 /Users/leahnoaeill/Downloads/MyClaude/mcp_pdf_server/pdf_extractor.py search "<PDF_URL>" "E0469"

# Extract all text from a PDF
python3 /Users/leahnoaeill/Downloads/MyClaude/mcp_pdf_server/pdf_extractor.py extract "<PDF_URL>"

# Extract only first N pages
python3 /Users/leahnoaeill/Downloads/MyClaude/mcp_pdf_server/pdf_extractor.py extract "<PDF_URL>" 5
```

### Tested & Working

Successfully tested on:
- BCBS Vermont Investigational Services PDF - Found E0469 in 2 locations
- Capital Blue Cross Experimental/Investigational PDF - Found E0469 in respiratory codes section

### Limitations

- Cannot access login-protected PDFs
- Scanned image PDFs without OCR text layer will return empty
- Very large PDFs may timeout

## Commands

```bash
# Regenerate spreadsheet
cd /Users/leahnoaeill/Downloads/MyClaude
python3 data_export/E0469_Explicit_Payer_Policies.py

# View current payer count
grep -c '"name":' data_export/E0469_Explicit_Payer_Policies.py
```

## Session History

- **Feb 4, 2026 (Initial)**: Created spreadsheet with 46 payers
- **Feb 4, 2026 (Update 1)**: Added 3 new payers (Moda Health, BCBS RI, Wellmark BCBS) - now 49 total
  - Extensive searches of state Medicaid programs yielded no additional explicit E0469 policies
  - Most state Medicaids have fee schedules in PDF format, not web-indexed
  - Confirmed Anthem removed E0469 from their policy (05/08/2025 revision)
- **Feb 4, 2026 (Update 2)**: Added 1 new payer - now 50 total
  - Added **Blue Cross Blue Shield of Michigan** - Michigan DIFS external review case (Sept 2024) explicitly determined Volara/E0469 is experimental/investigational and NOT COVERED
  - Searched many additional payers: UPMC, MVP Health Care, Capital Blue Cross, Regence BCBS, Quartz Health, Point32Health, AmeriHealth Caritas, Magellan Health - no explicit E0469 policies found
  - Confirmed Anthem CG-DME-43 policy does NOT include E0469 (only E0483)
  - BCBS Vermont may have E0469 as investigational but PDF not readable for verification
  - **Added new sheet "Searched - No E0469 Found"** with 65+ payers that were searched but had no explicit E0469 policy
- **Feb 4, 2026 (Update 3)**: Continued commercial payer searches
  - Searched: Centene/WellCare/Ambetter, LifeWise/Cambia, Allina, Sanford, CareSource, BCBS Alabama, BCBS Montana, BCBS Illinois (EIU list), ConnectiCare, Blue Cross MN, AvMed, FHCP, Devoted Health, Alignment Healthcare, Clover Health, CDPHP, Fallon Health, Manatee/GuideWell, Neighborhood Health Plan
  - No new explicit E0469 policies found - most policies either cover only E0483 or have no published E0469 policy
  - Challenge: Many commercial payers have experimental/investigational code lists in PDF format that are not easily searchable/readable
  - CareSource Ohio policy covers PAP devices but E0469 not explicitly mentioned
- **Feb 4, 2026 (Update 4)**: Added 3 new payers from user's payer list review - now 53 total
  - Added **Lifewise (Washington)** - E0469 in fee schedule with fixed pricing aligned to CMS, effective 07/15/2025
  - Added **Fidelis Care (New York Medicaid)** - E0469 in DME Authorization Grid, prior auth required
  - Added **Kentucky Medicaid MSEA** - E0469 referenced in regulation 907 KAR 1:479
  - Searched 20+ additional payers from user's list - no explicit E0469 policies found for: BCBS LA, Humana PR, Indiana IHCP, BCBS ND, Providence Health Plan OR, HMSA Hawaii, Texas Children's Health Plan, Anthem WI/VA/ME/NY/GA, BCBS CA/NV, CalViva Health, iCare WI, Colorado HCPF, Select Health CO, Mississippi Medicaid, Montana Medicaid
  - **Note**: Premera Blue Cross AK uses same policy 1.01.539 as main Premera entry (already included)
- **Feb 4, 2026 (Update 5)**: User manually reviewed PDFs and found 10 additional payers - now 63 total
  - Added **Capital Blue Cross (PA)** - MP 4.002 Experimental/Investigational (eff. 02/01/2026)
  - Added **BCBS Texas** - EIU or Clinical Review, fee $9,003.78 purchase
  - Added **BCBS Illinois** - EIU Non-Reimbursable
  - Added **BCBS New Mexico** - Recommended Clinical Review (Predetermination)
  - Added **BCBS Nebraska** - MA Prior Auth (MA-X-077)
  - Added **BCBS Minnesota** - Prior Auth via Evicore
  - Added **BCBS Vermont** - Investigational (10.01.VT204, eff. 01/01/2025)
  - Added **CareSource Ohio** - Prior Auth Required (eff. 04/01/2025)
  - Added **Select Health Utah (Medicare)** - Prior Auth Required (eff. 12/22/2025)
  - Added **Select Health Idaho (Medicare)** - Prior Auth Required (eff. 12/22/2025)
  - **Key finding**: Many BCBS plans have E0469 in EIU (Experimental/Investigational/Unproven) lists but PDFs are not web-searchable
  - **Limitation identified**: Claude's WebFetch tool cannot reliably parse compressed/encoded PDFs that Google Chrome AI can read
- **Feb 4, 2026 (Update 6)**: Coverage language accuracy review - corrected entries to match actual policy language
  - **Key distinction identified**: "NOT COVERED" vs "Investigational" vs "Not Medically Necessary" are different coverage determinations
  - Changed entries using "NOT COVERED" when policy actually says "Investigational" or "Experimental"
  - Changed "Not Medically Necessary" entries to "Case Review - Prior Auth Needed" (allows for appeal/case review)
  - **Payers corrected**:
    - HealthPartners: NOT COVERED → Investigational - Experimental
    - BCBS Florida: NOT COVERED → Investigational - Experimental
    - Premera: NOT COVERED → Investigational
    - Kaiser WA (Non-Medicare): Not Medically Necessary → Case Review - Prior Auth Needed
    - BCBS RI: NOT COVERED → Case Review - Prior Auth Needed
    - Wellmark BCBS: NOT COVERED → Investigational
    - BCBS Michigan: NOT COVERED → Investigational - Experimental
    - Blue Cross NC: NOT COVERED → Investigational
    - BCBS Vermont: NOT COVERED → Investigational
    - Aetna: NOT COVERED → Investigational - Experimental
    - Humana Commercial: NOT COVERED → Investigational - Experimental
    - Humana Medicaid: NOT COVERED → Investigational - Experimental
  - **Only 4 payers explicitly say "NOT COVERED"**: Medica, Minnesota MHCP, Capital Blue Cross, BCBS Illinois
