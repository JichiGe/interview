# Data Cleaning and Normalization Approach

This document outlines the systematic approach taken to clean, normalize, and enrich the `inventory_raw.csv` dataset. The process is implemented in the `run.py` script, which serves as the single entry point for the entire pipeline.

## 1. Initial Setup and Framework

The first step was to establish a robust and extensible framework. The logic from the provided `run_ipv4_validation.py` example was consolidated into `run.py`. This creates a single, unified script that processes the raw inventory row by row, which is more efficient and easier to manage than a multi-script chain.

The script is designed around a central `process_row` function, which will be incrementally enhanced with validation and normalization logic for each data field.

## 2. Deterministic Validation and Normalization

A rule-based approach is applied first to handle clear-cut cleaning tasks.

### a. IP Address
- **Validation:** Check if the IP string conforms to a valid IPv4 format (four octets, values 0-255).
- **Normalization:** Trim whitespace and normalize octets (e.g., `010` becomes `10`).
- **Enrichment:** Derive `ip_version` and a default `/24` `subnet_cidr` for private IP ranges.
- **Anomalies:** Flag invalid formats, incorrect part counts, or out-of-range values.

### b. MAC Address (To be implemented)
- **Validation:** Check for common MAC address formats.
- **Normalization:** Convert all valid MAC addresses to a single canonical format (e.g., `AA:BB:CC:DD:EE:FF`).

### c. Hostname and FQDN (To be implemented)
- **Validation:** Ensure hostnames contain valid characters.
- **Enrichment:** Check for consistency between `hostname` and `fqdn`, and generate a `reverse_ptr` record from the IP address.

### d. Owner (To be implemented)
- **Parsing:** Use regular expressions to extract `owner_email` and `owner_team` from the free-text `owner` field.

### e. Site (To be implemented)
- **Normalization:** Standardize site names by converting to a consistent case and mapping known aliases to a canonical name.

## 3. AI-Powered Enrichment (To be implemented)

For fields where deterministic rules are insufficient, an LLM will be used.

- **Device Type Classification:** For rows with a missing or ambiguous `device_type`, the LLM will be prompted with the available data for that row (e.g., hostname, notes) to infer a likely device type and a confidence score.
- **Complex Owner Parsing:** If the owner field doesn't match simple patterns, the LLM may be used to parse it.

All prompts, rationale, and iterations will be logged in `prompts.md`.

## 4. Anomaly and Output Generation

- **Anomalies:** Throughout the process, any identified issues are collected into a list. This list is then written to `anomalies.json`, detailing the row, field, issue, and original value.
- **Cleaned Data:** The processed data for all rows is written to `inventory_clean.csv`, adhering to the target schema.