# [FEATURE / TASK]: <Short, Descriptive Title>

> **Priority:** Low | Medium | High | Critical  
> **Estimated Effort:** 1pt / 2pts / 3pts / 5pts / 8pts  

---

## 1. Context & Business Value (Why it is needed)
*Explain the background problem, the user impact, or why the system requires this change.*

- **Problem Statement:** What problem does this solve? What breaks or is missing without it?
- **User / Business Value:** Why is this important to the end user, data accuracy, or compliance (e.g., ESG screener accuracy, audit trail requirements)?

---

## 2. Functional Description (What it should do)
*Provide a concise description of expected behavior and functional scope.*

- **Summary of Functionality:** Briefly describe what this module/function/workflow step should do.
- **Workflow / Steps:**
  1. Step 1 (e.g., receives payload / triggers webhook).
  2. Step 2 (e.g., calls external API, parses document, or executes logic).
  3. Step 3 (e.g., validates output against constraints and persists result).
- **Out of Scope:** Explicitly state what should **not** be handled in this ticket to prevent scope creep.

---

## 3. Data Contract: Input & Output Variables

### 3.1 Input Variables
*Specify exact variable names, data types, whether they are optional/required, and why they are needed.*

| Variable Name | Type | Required? | Description & Rationale |
| :--- | :--- | :---: | :--- |
| `company_id` | `string` | **Yes** | The unique identifier (e.g., Companies House ID like `00000000`). Needed to locate company filings deterministically. |
| `filing_year` | `integer` | **Yes** | 4-digit fiscal year (e.g., `2024`). Needed so we target the exact annual report rather than older filings. |
| `raw_document_url` | `string (URI)` | **No** | Direct link or S3/GCS path to downloaded PDF. Optional; falls back to live download if omitted. |
| `validation_strictness` | `enum['lenient', 'strict']` | **No** (default: `'strict'`) | Controls whether mathematical rounding discrepancies throw an error or trigger a review flag. |

### 3.2 Output Variables
*Specify the exact structure and keys that this unit of work must return upon execution.*

| Variable Name | Type | Required? | Description & Rationale |
| :--- | :--- | :---: | :--- |
| `status` | `enum['SUCCESS', 'FLAGGED', 'FAILED']` | **Yes** | Overall run status so downstream orchestrators (e.g., n8n) can branch workflows cleanly. |
| `total_revenue` | `number` (or `null`) | **Yes** | Extracted top-level revenue figure. Needed to perform mathematical reconciliation with segments. |
| `revenue_breakdown` | `array[object]` | **Yes** | Array of extracted line items. Essential for ESG taxonomy screening. Each object contains: <br> - `segment_name` (`string`)<br> - `amount` (`number`)<br> - `currency` (`string`)<br> - `source_citation` (`string` or `{ page: int, passage: string }`) |
| `reconciliation_variance` | `number` | **Yes** | Calculated difference: $\sum(\text{segments}) - \text{total\_revenue}$. Needed to flag data discrepancies for human review. |
| `error_log` | `array[string]` | **No** | Captured execution or parsing warnings when status is `'FLAGGED'` or `'FAILED'`. |

---

## 4. Edge Cases, Failures & Boundary Conditions
*Detail what can go wrong and how the system should react without crashing or hallucinating.*

- [ ] **Missing Data:** If the source report lacks broken-down numbers, do not guess or interpolate. Return `status: "FLAGGED"` with `error_log: ["Segment breakdown not reported in filing"]`.
- [ ] **Rate Limiting / Timeouts:** If upstream services (e.g., Companies House API or LLM endpoint) return 429/504, implement an exponential backoff retry (maximum 3 attempts).
- [ ] **Scanned/Unreadable PDFs:** Explicitly catch OCR or document parsing failures and mark for manual ingestion.

---

## 5. Security, Dependencies & Configuration
- **External Dependencies / APIs:** (e.g., Companies House REST API, OpenAI / Claude API, Vector Store)
- **Environment Variables / Secrets:**
  - `COMPANIES_HOUSE_API_KEY`
  - `LLM_API_KEY`
- **Config Dependencies:** (e.g., `config/esg_taxonomy.json` containing current exclusion rules)

---

## 6. Definition of Done (Acceptance Criteria)
*A checklist to verify the ticket is complete before opening a pull request.*

- [ ] Function/Service handles all defined input parameters and validates input types.
- [ ] Returns payloads strictly matching the defined output variable contract.
- [ ] Unit tests written covering happy paths and edge cases (minimum 80% test coverage).
- [ ] Tested locally or in staging with at least 2 real-world inputs (e.g., two sample filings).
- [ ] Code passes linter, formatting checks, and security scans without warnings.
- [ ] Documentation or README updated if new environment variables were introduced.