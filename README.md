# ESG Revenue Screener

An automated pipeline that screens UK-listed companies against ESG criteria by extracting revenue streams and business activities from their annual reports.

Given a company's Companies House registration number (CRN), the system fetches the latest annual accounts, stores the PDF in Google Drive, extracts business segments with an LLM (with an OCR fallback for scanned filings), persists the results in PostgreSQL, and syncs them to Airtable for review. A companion MCP server exposes the database read-only to AI assistants such as ChatGPT.

## Repository layout

```
.
├── database/
│   ├── schema.sql                      # PostgreSQL schema (companies, revenue_streams, esg_criteria, revenue_criteria_results)
│   ├── companies.csv                   # Seed list of ~27 companies to screen (name, sector, CRN, filing URL)
│   ├── esg_criteria.csv                # Seed list of 16 ESG screening criteria with thresholds
│   └── database_schema_draw_sql.png    # ER diagram of the schema
├── documentation/
│   ├── Project Proposal_ ESG Revenue Screener.pdf
│   ├── ESG Extraction Tool Specification.md   # Input/output/error contracts for each sub-workflow
│   ├── esg_revenue_screener_to_be.bpmn        # To-be process model (open with bpmn.io / Camunda Modeler)
│   ├── ticket_framework.md                    # Template for writing issues
│   ├── pull_request_framework.md              # Template for PR descriptions
│   └── requirements.txt                       # Python deps for optional analysis / dashboard work
└── n8n-workflows/                      # Exportable n8n workflow JSON (import these into n8n)
    ├── esg-main-workflow.json
    ├── esg-business-activities-extraction.json
    ├── esg-text-based-LLM-processing-subworkflow.json
    ├── esg-OCR-processing-subworkflow.json
    ├── esg-company-extraction-error-handler.json
    ├── esg-mcp-access.json
    └── esg-mcp-setup.json
```

## How it works

```
POST /webhook/screen-company  { company_crn, company_name }
        │
        ▼
esg-main-workflow
  1. Normalise CRN (zero-pad to 8 digits)
  2. Look up company in Postgres `companies`
  3. Query Companies House filing history (category=accounts)
  4. Download latest accounts PDF → upload/update in Google Drive
  5. Insert/update the `companies` row
  6. ── calls ──▶ esg-business-activities-extraction
  │                 ├─ fetch PDF from Drive, extract native text
  │                 ├─ usable text (≥ 500 chars)?
  │                 │     yes → esg-text-based-LLM-processing-subworkflow (Gemini)
  │                 │     no  → esg-OCR-processing-subworkflow (PDF.co + OpenRouter vision model)
  │                 └─ write `revenue_streams` rows to Postgres
  7. Sync `companies` + `revenue_streams` to Airtable (base "ESGenius")
  8. ── calls ──▶ esg-label-classifier (classifies streams against `esg_criteria`)

Any failure ──▶ esg-company-extraction-error-handler
                  marks `companies.extraction_status` as failed and posts to Slack
```

Detailed input/output schemas and error paths for each sub-workflow are in [documentation/ESG Extraction Tool Specification.md](documentation/ESG%20Extraction%20Tool%20Specification.md).

### Database

Four tables, defined in [database/schema.sql](database/schema.sql):

| Table | Purpose |
| --- | --- |
| `companies` | One row per screened company: CRN, sector, financial year, filing URL, Drive file/folder IDs, extraction status |
| `revenue_streams` | Business segments extracted from a company's report (name, description, activities, evidence, source page) |
| `esg_criteria` | Screening rules (e.g. "Fossil fuels", threshold 10 %, `max`) |
| `revenue_criteria_results` | Result of evaluating a revenue stream against a criterion, with justification and page reference |

### MCP server (database access for AI assistants)

`esg-mcp-access.json` exposes an n8n MCP trigger at `/mcp/postgres-mcp` with three read-only tools: `list_tables`, `get_table_schema`, and `execute_select_query`. `esg-mcp-setup.json` is the equivalent logic as a plain sub-workflow (routed on an `action` field) for use from other n8n workflows.

## Setup

### Prerequisites

- **n8n** (cloud or self-hosted, v1.x) with the LangChain nodes and the community **PDF.co** node (`n8n-nodes-pdfco`) installed
- **PostgreSQL** 13+
- Accounts / API keys for:
  - [Companies House API](https://developer.company-information.service.gov.uk/) (HTTP Basic auth — key as username, blank password)
  - Google Drive (OAuth2)
  - Google Gemini (Google PaLM/Gemini API credential in n8n)
  - OpenAI and/or OpenRouter (bearer token) — used by the OCR sub-workflow
  - [PDF.co](https://pdf.co/) — PDF splitting/merging for the OCR path
  - Airtable (OAuth2) with a base named **ESGenius** containing `companies` and `revenue_streams` tables
  - Slack (OAuth2) with a channel for failure alerts

### 1. Clone the repo

```bash
git clone https://github.com/akhandwalla47/ESG-TBA-Group-Project.git
cd ESG-TBA-Group-Project
```

### 2. Create the database

```bash
createdb esg_screener
psql -d esg_screener -f database/schema.sql
```

Seed the criteria and company lists:

```sql
\copy esg_criteria(criteria_id, criteria_name, criteria_description, threshold, screening_type, created_at)
  FROM 'database/esg_criteria.csv' WITH (FORMAT csv, HEADER true);
```

`companies.csv` is a curated input list (it includes helper columns like `check?` and `note`), so companies are normally inserted by the main workflow rather than bulk-loaded. If you want to pre-load them, map `company_name`, `sector`, `company_crn` and `filing_doc_url` and supply values for the remaining `NOT NULL` columns.

> **Note:** the final statement in `schema.sql` (`ALTER COLUMN stream_revenue DROP NOT NULL`) references a column that is not defined in the file and will error on a fresh database. Everything before it runs cleanly; the error can be ignored.

### 3. Import the n8n workflows

In n8n go to **Workflows → Import from File** and import every JSON file in `n8n-workflows/`. Import the sub-workflows first so the parent workflows can resolve them:

1. `esg-text-based-LLM-processing-subworkflow.json`
2. `esg-OCR-processing-subworkflow.json`
3. `esg-business-activities-extraction.json`
4. `esg-company-extraction-error-handler.json`
5. `esg-main-workflow.json`
6. `esg-mcp-setup.json` and `esg-mcp-access.json` (optional, for MCP access)

### 4. Configure credentials

The exported workflows reference credentials by name (e.g. `Postgres account 7`, `Google Drive account 2`, `OpenRouter Key`). After importing, open each workflow and re-select your own credentials on every node that shows a credential warning:

| Credential type | Used in |
| --- | --- |
| Postgres | main, extraction, error-handler, MCP workflows |
| Google Drive OAuth2 | main, extraction |
| HTTP Basic Auth (Companies House) | main |
| Airtable OAuth2 | main |
| Google Gemini / PaLM API | text-based LLM sub-workflow |
| OpenAI API, HTTP Bearer (OpenRouter), PDF.co API | OCR sub-workflow |
| Slack OAuth2 | error handler |

### 5. Wire up the workflow references

- In `esg-business-activities-extraction`, the two **Execute Workflow** nodes point at the text-based and OCR sub-workflows by ID. Re-select them from the dropdown after import.
- In `esg-main-workflow`, re-select `esg-business-activities-extraction` and `esg-label-classifier` in the **Execute Workflow** nodes. The label-classifier workflow is not yet in this repository; disable that node if you do not have it.
- In the **Google Drive** nodes, choose the Drive folder where annual reports should be stored (originally "ESG Revenue Screener").
- In the **Slack** node of the error handler, pick your alerts channel.
- Under **Settings** of `esg-main-workflow` and `esg-business-activities-extraction`, set **Error workflow** to `esg-company-extraction-error-handler`.

### 6. Activate and test

Activate `esg-main-workflow`, then trigger a screening run:

```bash
curl -X POST "https://<your-n8n-host>/webhook/screen-company" \
  -H "Content-Type: application/json" \
  -d '{"company_crn": "02723534", "company_name": "AstraZeneca PLC", "criteria_id": "CRI-001"}'
```

The CRN is zero-padded automatically, so `2723534` and `02723534` are equivalent. On success the `companies` and `revenue_streams` tables are populated and mirrored to Airtable; on failure a message is posted to Slack and `companies.extraction_error` is set.

### Optional: Python environment

[documentation/requirements.txt](documentation/requirements.txt) lists dependencies (`psycopg2-binary`, `streamlit`, `pandas`, `plotly`) for ad-hoc analysis or a dashboard against the database. There is no Python application code in the repo yet; set up an environment if you plan to add some:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r documentation/requirements.txt
```

## Contributing

- Create a branch per issue, named `<issue-number>-<short-description>` (e.g. `61-create-mcp-workflows`).
- Write issues using [documentation/ticket_framework.md](documentation/ticket_framework.md).
- Open pull requests using [documentation/pull_request_framework.md](documentation/pull_request_framework.md) and link the issue(s) they close.
- When changing an n8n workflow, re-export it from n8n and commit the updated JSON under `n8n-workflows/`. Do not commit credentials — n8n exports reference credentials by name/ID only.
- Keep `database/schema.sql` in sync with any schema changes and update the ER diagram.
