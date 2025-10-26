# Approach to Data Cleaning and Validation

This document outlines the hybrid, multi-stage approach taken to clean, validate, and normalize the `inventory_raw.csv` dataset. The methodology prioritizes deterministic, rule-based processing, while leveraging a Large Language Model (LLM) as a "surgical tool" for specific, well-defined ambiguous cases. The final outputs are a professionally ordered CSV and a comprehensive, human-readable anomaly report.

## Phase 1: Deterministic Processing

The primary workhorse of this solution is the `run.py` script, which systematically processes each row of the raw data.

1.  **Initial Validation and Normalization**: For each record, the script performs a series of deterministic checks and transformations on key fields:
    *   **IP Address**: Validates both IPv4 and IPv6 formats using the `ipaddress` library. It handles common issues like leading zeros, octal-like representations, and invalid ranges. For valid IPs, it also derives the `ip_version`, a probable `/24` `subnet_cidr` for private ranges, and the `reverse_ptr` record.
    *   **MAC Address**: A regular expression validates and normalizes various MAC address formats into a canonical format (`XX:XX:XX:XX:XX:XX`).
    *   **Hostname**: Validates against RFC 1123 standards.
    *   **FQDN**: Checks for basic consistency (if the `fqdn` field starts with the `hostname` field).
    *   **Owner**: A simple regex attempts to parse an email address and a team name (enclosed in parentheses).
    *   **Site**: Normalizes the site name to a canonical format (lowercase, hyphen-separated).

2.  **First-Pass Classification**: The script attempts a preliminary classification of the `device_type` by searching for keywords (e.g., "server", "gw", "camera") within the `device_type` and `notes` fields.

3.  **Initial Anomaly Logging**: Any data that fails the initial validation (e.g., an invalid IP format) is immediately logged.

## Phase 2: LLM-Assisted Enrichment

For data fields identified as ambiguous (specifically `device_type` and `owner` strings that do not conform to simple patterns), a manual, controlled LLM process is used.

1.  **Batch Prompting**: To improve efficiency, ambiguous cases were grouped and sent to the LLM in a single batch request for each field. The prompts were carefully engineered to include:
    *   Clear context and instructions.
    *   A constrained set of valid output categories.
    *   A strict requirement for a low "temperature" (≤ 0.2) to ensure deterministic, high-quality responses.
    *   A required output format (structured JSON).

2.  **Recording and Integration**:
    *   Every batch prompt and its corresponding LLM response is meticulously logged in `prompts.md` for reproducibility and auditing.
    *   The classified/parsed data from the LLM is then hardcoded into override dictionaries (`LLM_CLASSIFICATIONS`, `LLM_OWNER_OVERRIDES`) within the `run.py` script.

## Phase 3: Finalization and Reporting

The final stage integrates all results and generates the polished outputs.

1.  **Final Execution**: The `run.py` script is run a final time. When processing a row, it now prioritizes the LLM override dictionaries before falling back to the deterministic logic.

2.  **Comprehensive Anomaly Reporting**: After all processing for a row is complete, a final check is performed. It identifies and logs anomalies for:
    *   Any critical fields that remain empty (e.g., `mac`, `fqdn`, `site`).
    *   Any `device_type` that was ultimately classified as `unknown`.
    *   Any `owner` string that could not be parsed by either the regex or the LLM.

3.  **Duplicate Value Detection**: After all rows are processed, a dedicated scan of the entire dataset is performed to find duplicate values in critical unique fields. It identifies any `ip`, `mac`, or `hostname` that appears more than once and creates a `duplicate_value` anomaly for *all* rows sharing that value.

4.  **Structured Anomaly Output**: The final `anomalies.json` is structured for maximum readability. All issues related to a single `source_row_id` are grouped together under one entry, making it easy to see a consolidated view of all problems for a specific record.

5.  **Ordered CSV Output**: The final `inventory_clean.csv` has its columns carefully reordered to a more logical and professional standard, starting with the `source_row_id` identifier and grouping related fields together.

This iterative, multi-phase approach ensures that the data is handled by reliable programmatic rules wherever possible, uses AI responsibly for targeted ambiguity resolution, and produces final artifacts that are comprehensive, well-structured, and easy for a human to review.
