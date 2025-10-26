# Approach to Data Cleaning and Validation

This document outlines the hybrid, two-phase approach taken to clean, validate, and normalize the `inventory_raw.csv` dataset. The methodology prioritizes deterministic, rule-based processing for speed and accuracy, while leveraging a Large Language Model (LLM) for specific, well-defined ambiguous cases.

## Phase 1: Deterministic Processing

The primary workhorse of this solution is the `run.py` script, which systematically processes each row of the raw data.

1.  **Initial Validation and Normalization**: For each record, the script performs a series of deterministic checks and transformations on key fields:
    *   **IP Address**: Validates both IPv4 and IPv6 formats using the `ipaddress` library. It handles common issues like leading zeros, octal-like representations, and invalid ranges. For valid IPs, it also derives the `ip_version`, a probable `/24` `subnet_cidr` for private ranges, and the `reverse_ptr` record.
    *   **MAC Address**: A regular expression validates and normalizes various MAC address formats (e.g., `AA-BB-CC-DD-EE-FF`, `aabb.ccdd.eeff`) into a single canonical format (`XX:XX:XX:XX:XX:XX`).
    *   **Hostname**: Validates against RFC 1123 standards to ensure characters and structure are valid.
    *   **FQDN**: Checks if the `fqdn` field is consistent with (i.e., starts with) the `hostname` field.
    *   **Owner**: A simple regex attempts to parse an email address and a team name (enclosed in parentheses).
    *   **Site**: Normalizes the site name by converting it to lowercase and replacing spaces with hyphens.

2.  **First-Pass Classification (`device_type`)**: The script attempts a preliminary classification of the `device_type` by searching for keywords (e.g., "server", "gw", "camera") within the `device_type` and `notes` fields. If a high-confidence match is found, the type is set.

3.  **Anomaly and Flagging**:
    *   Any data that fails validation is recorded in `anomalies.json`, detailing the row, field, issue, and original value.
    *   Rows with ambiguous data that cannot be resolved by these rules (specifically, `device_type` fields that are empty or don't match any keywords) are flagged internally for the next phase. A `normalization_steps` column tracks every action taken, including the `device_type_requires_llm` flag.

## Phase 2: LLM-Assisted Classification

For data flagged as ambiguous in Phase 1, a manual, controlled LLM process is used.

1.  **Targeted Prompting**: Instead of sending raw, unstructured data, a structured prompt is created for each ambiguous case (or a batch of them). The prompt includes:
    *   Clear context (the relevant data from the row).
    *   The specific task (classify the `device_type`).
    *   A constrained set of valid output categories.
    *   A requirement for a low "temperature" (≤ 0.2) to ensure deterministic, non-creative responses.
    *   A required output format (minified JSON).

2.  **Recording and Integration**:
    *   Every prompt and its corresponding LLM response is meticulously logged in `prompts.md` for reproducibility and auditing.
    *   The classified data from the LLM is then hardcoded into a dictionary (`LLM_CLASSIFICATIONS`) within the `run.py` script. This acts as a set of manual overrides.

3.  **Final Execution**: The `run.py` script is run a final time. When it encounters a row ID present in the `LLM_CLASSIFICATIONS` dictionary, it uses the high-quality, LLM-provided data directly, bypassing the initial classification logic.

This hybrid approach ensures that the vast majority of the data is handled by fast, reliable, and auditable programmatic rules. The LLM is used as a "surgical tool" only for the specific, pre-identified cases where human-like interpretation is necessary, with all interactions being fully documented and integrated back into the reproducible workflow.
