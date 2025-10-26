# Known Limitations and Trade-offs

This document outlines the known limitations, risks, and trade-offs associated with the data cleaning and enrichment process.

### 1. Risk of LLM Hallucination and Inaccuracy
- **Description:** When using a Large Language Model (LLM) to classify ambiguous `device_type` or parse complex `owner` fields, there is an inherent risk of the model "hallucinating" or providing incorrect information. The model's output is probabilistic, not deterministic.
- **Mitigation:** This risk is mitigated by using a low "temperature" setting (e.g., <= 0.2) to encourage more predictable outputs. Furthermore, a `device_type_confidence` score is added to the schema, allowing downstream systems to filter or flag low-confidence classifications for human review. The prompts are also engineered to request structured output (JSON) to limit free-form, creative responses.

### 2. Lack of External Context and Ground Truth
- **Description:** The cleaning process operates solely on the data within `inventory_raw.csv`. It has no access to external systems like corporate directories, network monitoring tools, or configuration management databases (CMDB). Therefore, it cannot definitively validate information like the `owner` of a device or its true `site`. For example, an `owner` might be a former employee, but the script has no way of knowing this.
- **Trade-off:** The goal is to clean and structure the *provided* data, not to perform a full audit against external sources. The enrichment is a "best effort" based on the available information. A more advanced system would require API access to these external sources.

### 3. Unmodeled Complex Network Scenarios (e.g., Split-Horizon FQDN)
- **Description:** The validation logic for FQDNs assumes a simple relationship where the FQDN starts with the hostname (e.g., `hostname.domain.com`). It does not account for more complex DNS scenarios like split-horizon DNS, where a hostname might resolve to different FQDNs or IPs depending on the source of the query.
- **Limitation:** The `fqdn_consistent` flag is based on a simplistic string comparison and does not perform any actual DNS lookups. It cannot detect or model these advanced configurations.

### 4. Heuristic-Based Field Derivation
- **Description:** Some derived fields are based on simple heuristics that may not hold true in all cases. For example, the `subnet_cidr` is assumed to be a `/24` for all private IP addresses. In a real-world network, private subnets can have many different prefix lengths (e.g., /16, /22, /27).
- **Trade-off:** This heuristic provides a reasonable default for creating a complete record but may be inaccurate. A more accurate approach would require network topology information that is not present in the source data.