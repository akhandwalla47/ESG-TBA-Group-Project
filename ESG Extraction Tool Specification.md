# **ESG Extraction Tool Specification**

This document provides the tool specifications for the subworkflows comprising the ESG business activity extraction pipeline. Each specification defines the required input schema, the output structure, and expected error paths.

## **1\. File Retrieval & Preparation (file-retrieval-prep)**

**Description:**  
Retrieves the company's stored annual report PDF from Google Drive using its database reference. Converts the PDF into a format suitable for text extraction and evaluates whether sufficient native readable text is available for standard LLM processing, or if OCR processing is required.

### **Input Schema**

`{`  
  `"company_id": {`  
    `"type": "number",`  
    `"description": "The unique internal identifier for the company in the Postgres database."`  
  `}`  
`}`

### **Output Schema**

`{`  
  `"company_id": "number",`  
  `"company_name": "string",`  
  `"company_crn": "string",`  
  `"filing_id": "number | null",`  
  `"financial_year": "string",`  
  `"filing_doc_url": "string (URL to Google Drive PDF)",`  
  `"extracted_text": "string (Extracted native text from the PDF)",`  
  `"text": "string (Alias for extracted_text)",`  
  `"usable_text": "boolean (True if extracted text length >= 500 characters)"`  
`}`

### **Error Paths**

> * **Database Error:** Triggered if company\_id does not exist in the Postgres database.  
> * **File Retrieval Error:** Triggered if the filing\_doc\_url is broken, missing, or Google Drive API permissions are invalid.  
> * **Extraction Failure:** Triggers if PDF to Base64 conversion fails.

## **2\. Text-Based LLM Processing (esg-text-based-LLM-processing-subworkflow)**

**Description:**  
Sends readable native PDF text to the Gemini language model. It identifies reported revenue streams, business segments, and underlying business activities. Extracts descriptions, financial figures, and supporting evidence based on strict ESG screening guidelines.

### **Input Schema**

`{`  
  `"_firstItem": {`  
    `"type": "object",`  
    `"description": "Original trigger payload containing basic company context.",`  
    `"properties": {`  
      `"company_id": { "type": "number" },`  
      `"company_name": { "type": "string" },`  
      `"company_crn": { "type": "string" }`  
    `}`  
  `},`  
  `"Retrieve_File_Location__firstItem": {`  
    `"type": "object",`  
    `"description": "Database payload containing filing context.",`  
    `"properties": {`  
      `"filing_id": { "type": "number | null" },`  
      `"financial_year": { "type": "string" }`  
    `}`  
  `},`  
  `"extracted_text": {`  
    `"type": "string",`  
    `"description": "The native text extracted from the annual report PDF."`  
  `}`  
`}`

### **Output Schema**

Outputs a valid JSON matching the LangChain Structured Output Parser schema, formatted roughly as:

`{`  
  `"company_name": "string",`  
  `"reporting_year": "string",`  
  `"business_segments": [`  
    `{`  
      `"stream_name": "string",`  
      `"display_name": "string",`  
      `"business_description": "string | null",`  
      `"business_activities": "string | null",`  
      `"supporting_evidence": "string | null",`  
      `"source_page": "string | null"`  
    `}`  
  `],`  
  `"disclosure_gaps": ["string"]`  
`}`

### **Error Paths**

> * **Empty Input:** Throws No usable PDF text was supplied. if extracted\_text is empty or only whitespace.  
> * **LLM Refusal / Timeout:** Triggers if Gemini fails to respond or refuses the prompt.  
> * **Parser Failure:** Triggers if the Gemini output cannot be coerced into the requested structured JSON format.

## **3\. OCR Processing (esg-OCR-processing-subworkflow)**

**Description:**  
Triggered when native PDF text is unusable (e.g., scanned images). It extracts the first 5 pages to identify the Table of Contents via Gemini. It calculates relevant section boundaries, splits the relevant pages via PDF.co, merges them, and uses an OpenRouter vision/multimodal model to extract the structured business segment data from the visual PDF pages.

### **Input Schema**

`{`  
  `"filing_doc_url": {`  
    `"type": "string",`  
    `"description": "URL to the original PDF in Google Drive."`  
  `},`  
  `"Retrieve_stored_PDF_filing_doc_url": {`  
    `"type": "string",`  
    `"description": "Alias for filing_doc_url."`  
  `},`  
  `"_firstItem": {`  
    `"type": "object",`  
    `"description": "Original trigger payload (company_id, company_name, company_crn)."`  
  `},`  
  `"Retrieve_File_Location__firstItem": {`  
    `"type": "object",`  
    `"description": "Database payload (filing_id, financial_year)."`  
  `}`  
`}`

### **Output Schema**

`{`  
  `"company_id": "number",`  
  `"company_name": "string",`  
  `"company_crn": "string",`  
  `"filing_id": "number | null",`  
  `"reporting_year": "string",`  
  `"extraction_method": "string (e.g. 'business_segment_extraction')",`  
  `"business_segments": [`  
    `{`  
      `"stream_name": "string",`  
      `"display_name": "string",`  
      `"business_description": "string | null",`  
      `"business_activities": "string | null",`  
      `"supporting_evidence": "string | null",`  
      `"source_page": "string | null"`  
    `}`  
  `],`  
  `"disclosure_gaps": ["string"]`  
`}`

### **Error Paths**

> * **PDF.co API Failure:** Fails if the file is too large, protected, or the API key is invalid during splitting/merging.  
> * **TOC Not Found:** Throws No valid contents-page entries found. or No relevant business sections were identified by Gemini or the fallback keyword filter.  
> * **Invalid Page Ranges:** Throws No physical PDF pages were selected for extraction. if boundary logic fails.  
> * **Extraction Failure:** Triggers if the multimodal model fails to output valid JSON or misses the business\_segments array.