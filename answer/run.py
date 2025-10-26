#!/usr/bin/env python3
import csv
import json
import re
import ipaddress
from pathlib import Path

# --- Configuration ---
INPUT_CSV = Path(__file__).parent / "inventory_raw.csv"
OUTPUT_CSV = Path(__file__).parent / "inventory_clean.csv"
ANOMALIES_JSON = Path(__file__).parent / "anomalies.json"
TARGET_HEADERS = [
    "source_row_id",
    "ip", "ip_valid", "ip_version", "subnet_cidr", "reverse_ptr",
    "hostname", "hostname_valid", "fqdn", "fqdn_consistent",
    "mac", "mac_valid",
    "device_type", "device_type_confidence",
    "owner", "owner_email", "owner_team",
    "site", "site_normalized",
    "normalization_steps"
]

# --- LLM Overrides ---
LLM_CLASSIFICATIONS = {
    "6": {"device_type": "server", "confidence": 0.85},
    "7": {"device_type": "workstation", "confidence": 0.9},
    "9": {"device_type": "unknown", "confidence": 0.95},
    "10": {"device_type": "unknown", "confidence": 0.9},
    "11": {"device_type": "unknown", "confidence": 0.95},
    "12": {"device_type": "unknown", "confidence": 0.95},
    "15": {"device_type": "unknown", "confidence": 0.9}
}

LLM_OWNER_OVERRIDES = {
    "2": {"owner_team": "operations", "owner_email": "operations@corp.example.com"},
    "4": {"owner_team": "facilities", "owner_email": "facilities@corp.example.com"},
    "5": {"owner_team": "security", "owner_email": "security@corp.example.com"},
    "8": {"owner_team": "platform", "owner_email": "platform@corp.example.com"},
    "13": {"owner_team": "google-dns", "owner_email": None}
}

# --- Data Processing Functions ---

def validate_and_normalize_ip(ip_str):
    """Validates and normalizes an IP address (v4 or v6), handling octal-like strings in v4."""
    if not ip_str or not isinstance(ip_str, str):
        return False, ip_str, None, None, None, "missing"
    
    ip_str = ip_str.strip()

    if ':' in ip_str:
        try:
            original_ip_str = ip_str
            if '%' in ip_str:
                ip_str = ip_str.split('%')[0]
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.version != 6:
                 return False, original_ip_str, None, None, None, "mixed_notation"
            return True, str(ip_obj.exploded), 6, "", ip_obj.reverse_pointer, "ok"
        except ValueError as e:
            return False, original_ip_str, None, None, None, str(e)

    parts = ip_str.split('.')
    if len(parts) != 4:
        return False, ip_str, None, None, None, "wrong_part_count"
    
    try:
        canonical_parts = []
        for p in parts:
            if not p.isdigit():
                if not (p.startswith('-') and p[1:].isdigit()):
                    return False, ip_str, None, None, None, "non_numeric"
            v = int(p)
            if not 0 <= v <= 255:
                return False, ip_str, None, None, None, "octet_out_of_range"
            canonical_parts.append(str(v))
        
        normalized_ip = ".".join(canonical_parts)
        ip_obj = ipaddress.ip_address(normalized_ip)
        
        subnet_cidr = ""
        if ip_obj.is_private:
            subnet_cidr = f"{'.'.join(str(ip_obj).split('.')[:3])}.0/24"
            
        return True, str(ip_obj), 4, subnet_cidr, ip_obj.reverse_pointer, "ok"

    except (ValueError, TypeError):
        return False, ip_str, None, None, None, "invalid_format"

def normalize_and_validate_mac(mac_str):
    """Validates and normalizes a MAC address to a canonical format."""
    if not mac_str or not isinstance(mac_str, str):
        return False, None, "missing"

    cleaned_mac = re.sub(r'[:\-.]', '', mac_str).upper()
    if len(cleaned_mac) == 12 and all(c in '0123456789ABCDEF' for c in cleaned_mac):
        normalized_mac = ':'.join(cleaned_mac[i:i+2] for i in range(0, 12, 2))
        return True, normalized_mac, "ok"
    else:
        return False, mac_str.strip(), "invalid_format"

def validate_hostname(hostname_str):
    """Validates a hostname based on RFC 1123."""
    if not hostname_str or not isinstance(hostname_str, str):
        return False, "missing"
    
    hostname = hostname_str.strip()
    if len(hostname) > 253:
        return False, "too_long"
    if not re.match(r'^(?!-)[A-Z0-9-]{1,63}(?<!-)$', hostname, re.IGNORECASE):
        return False, "invalid_chars"
        
    return True, "ok"

def parse_owner(owner_str):
    """Parses owner string to extract email and team."""
    if not owner_str or not isinstance(owner_str, str):
        return None, None
    
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', owner_str)
    email = email_match.group(0) if email_match else None
    
    team_match = re.search(r'\((.*?)\)', owner_str)
    team = team_match.group(1) if team_match else None
    
    return email, team

def normalize_site(site_str):
    """Normalizes site names using a programmatic rule."""
    if not site_str or not isinstance(site_str, str):
        return None
    return site_str.strip().lower().replace(' ', '-')

def classify_device_type(device_type_str, notes_str):
    """Classifies device type using deterministic rules and flags ambiguous cases for LLM."""
    if not device_type_str and not notes_str:
        return None, 0.1, True # Needs LLM

    # Combine device_type and notes for better context
    context_str = f"{device_type_str or ''} {notes_str or ''}".lower().strip()

    # Simple keyword matching
    device_map = {
        "server": ["server", "db host"],
        "switch": ["switch"],
        "router": ["router", "gw"],
        "firewall": ["firewall"],
        "printer": ["printer"],
        "iot": ["iot", "camera"],
        "access-point": ["access-point", "ap"],
    }

    for device, keywords in device_map.items():
        for keyword in keywords:
            if keyword in context_str:
                return device, 0.9, False # High confidence

    # If no rule matches, it needs LLM
    return device_type_str, 0.3, True

def process_row(row, anomalies):
    """Processes a single row of inventory data."""
    source_row_id = row.get("source_row_id", "")
    processed = {key: None for key in TARGET_HEADERS}
    processed["source_row_id"] = source_row_id
    steps = []

    # --- IP Address ---
    raw_ip = row.get("ip")
    ip_valid, norm_ip, ip_ver, subnet, rev_ptr, ip_reason = validate_and_normalize_ip(raw_ip)
    processed["ip"] = norm_ip
    processed["ip_valid"] = ip_valid
    if ip_valid:
        processed["ip_version"] = ip_ver
        processed["subnet_cidr"] = subnet
        processed["reverse_ptr"] = rev_ptr
        steps.append("ip_normalized")
    else:
        if ip_reason != "missing":
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": "ip", "type": ip_reason, "value": raw_ip}],
                "recommended_actions": ["Correct IP or mark record for review"]
            })
            steps.append(f"ip_invalid_{ip_reason}")

    # --- MAC Address ---
    raw_mac = row.get("mac")
    mac_valid, norm_mac, mac_reason = normalize_and_validate_mac(raw_mac)
    processed["mac"] = norm_mac
    processed["mac_valid"] = mac_valid
    if mac_valid:
        steps.append("mac_normalized")
    else:
        if mac_reason == "invalid_format":
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": "mac", "type": "invalid_format", "value": raw_mac}],
                "recommended_actions": ["Correct MAC address to a standard format."]
            })
            steps.append("mac_invalid_format")

    # --- Hostname and FQDN ---
    raw_hostname = row.get("hostname", "").strip()
    raw_fqdn = row.get("fqdn", "").strip()
    processed["hostname"] = raw_hostname
    processed["fqdn"] = raw_fqdn
    
    hostname_valid, hostname_reason = validate_hostname(raw_hostname)
    processed["hostname_valid"] = hostname_valid
    if not hostname_valid and hostname_reason != "missing":
        anomalies.append({
            "source_row_id": source_row_id,
            "issues": [{"field": "hostname", "type": hostname_reason, "value": raw_hostname}],
            "recommended_actions": ["Ensure hostname follows RFC1123 standards."]
        })
        steps.append(f"hostname_invalid_{hostname_reason}")

    if raw_fqdn and raw_hostname:
        if raw_fqdn.startswith(raw_hostname):
            processed["fqdn_consistent"] = True
        else:
            processed["fqdn_consistent"] = False
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": "fqdn", "type": "inconsistent_with_hostname", "value": f"hostname: {raw_hostname}, fqdn: {raw_fqdn}"}],
                "recommended_actions": ["Verify FQDN corresponds to hostname."]
            })
            steps.append("fqdn_inconsistent")

    # --- Owner ---
    raw_owner = row.get("owner", "")
    processed["owner"] = raw_owner.strip()
    if source_row_id in LLM_OWNER_OVERRIDES:
        owner_result = LLM_OWNER_OVERRIDES[source_row_id]
        processed["owner_email"] = owner_result["owner_email"]
        processed["owner_team"] = owner_result["owner_team"]
        steps.append("owner_from_llm")
    else:
        email, team = parse_owner(raw_owner)
        processed["owner_email"] = email
        processed["owner_team"] = team
        if raw_owner and (email or team):
            steps.append("owner_parsed")

    # --- Site ---
    raw_site = row.get("site", "")
    norm_site = normalize_site(raw_site)
    processed["site"] = raw_site.strip()
    processed["site_normalized"] = norm_site
    if norm_site and norm_site != raw_site.strip():
        steps.append("site_normalized")

    # --- Device Type ---
    raw_device_type = row.get("device_type", "")
    raw_notes = row.get("notes", "")

    if source_row_id in LLM_CLASSIFICATIONS:
        llm_result = LLM_CLASSIFICATIONS[source_row_id]
        processed["device_type"] = llm_result["device_type"]
        processed["device_type_confidence"] = llm_result["confidence"]
        steps.append("device_type_from_llm")
    else:
        device_type, confidence, needs_llm = classify_device_type(raw_device_type, raw_notes)
        processed["device_type"] = device_type
        processed["device_type_confidence"] = confidence
        if needs_llm:
            steps.append("device_type_requires_llm")
        else:
            steps.append("device_type_classified")

    # --- Final Anomaly Check for Remaining Blanks ---
    final_check_fields = {
        "fqdn": "FQDN is missing. If possible, derive from hostname or investigate source system.",
        "mac": "MAC address is missing. This is a critical field for DHCP services.",
        "site_normalized": "Site information is missing."
    }

    for field, message in final_check_fields.items():
        if not processed.get(field):
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{"field": field, "type": "missing_value", "value": row.get(field, "")}],
                "recommended_actions": [message + " Manual review required."]
            })
            steps.append(f"{field}_missing")

    # Check for missing subnet_cidr (only if IP was valid)
    if processed.get("ip_valid") and not processed.get("subnet_cidr"):
        anomalies.append({
            "source_row_id": source_row_id,
            "issues": [{"field": "subnet_cidr", "type": "not_derived", "value": ""}],
            "recommended_actions": ["Subnet CIDR was not derived (e.g., for public, loopback, or link-local IPs). Review if this is expected."]
        })
        steps.append("subnet_cidr_not_derived")

    # Check for missing owner
    if not raw_owner:
        anomalies.append({
            "source_row_id": source_row_id,
            "issues": [{"field": "owner", "type": "missing_value", "value": ""}],
            "recommended_actions": ["Owner field is empty. Manual review required."]
        })
        steps.append("owner_missing")
    # Check for unresolved owner (if field was not empty but couldn't be parsed)
    elif raw_owner and not processed.get("owner_team") and not processed.get("owner_email"):
        anomalies.append({
            "source_row_id": source_row_id,
            "issues": [{"field": "owner", "type": "unresolved_field", "value": raw_owner}],
            "recommended_actions": ["Owner could not be parsed. Manual review required."]
        })
        steps.append("owner_unresolved")

    # Final check for 'unknown' device_type
    if processed.get("device_type") == "unknown":
        anomalies.append({
            "source_row_id": source_row_id,
            "issues": [{"field": "device_type", "type": "classified_as_unknown", "value": raw_device_type}],
            "recommended_actions": ["Device type was classified as 'unknown'. Manual investigation is required."]
        })
        steps.append("device_type_is_unknown")
    # Final check for unresolved device_type
    elif not processed.get("device_type"):
        anomalies.append({
            "source_row_id": source_row_id,
            "issues": [{"field": "device_type", "type": "unresolved_field", "value": raw_device_type}],
            "recommended_actions": ["Device type could not be determined. Manual review required."]
        })
        steps.append("device_type_unresolved")

    # --- Cross-Field Consistency Check ---
    hostname_lower = processed.get("hostname", "").lower()
    final_device_type = processed.get("device_type")

    if hostname_lower and final_device_type:
        consistency_map = {
            "server": ["server", "srv"],
            "router": ["router", "rtr", "gw"],
            "switch": ["switch", "sw"],
            "firewall": ["firewall", "fw"],
            "printer": ["printer", "print"],
            "access-point": ["ap"]
        }

        inferred_type = None
        for dtype, keywords in consistency_map.items():
            if inferred_type: break
            for keyword in keywords:
                if keyword in hostname_lower:
                    inferred_type = dtype
                    break
        
        if inferred_type and inferred_type != final_device_type:
            anomalies.append({
                "source_row_id": source_row_id,
                "issues": [{
                    "field": "hostname/device_type",
                    "type": "inconsistent_hostname_devicetype",
                    "value": f"hostname is '{processed.get('hostname')}' but device_type is '{final_device_type}'"
                }],
                "recommended_actions": [f"Hostname suggests device should be a '{inferred_type}', but it is classified as '{final_device_type}'. Manual verification needed."]
            })
            steps.append("inconsistent_host_type")

    processed["normalization_steps"] = "|".join(steps)
    return processed
def main():
    """Main function to run the data cleaning process."""
    anomalies = []
    cleaned_rows = []

    try:
        with open(INPUT_CSV, mode='r', newline='', encoding='utf-8') as infile:
            raw_data = list(csv.DictReader(infile))
        
        for row in raw_data:
            processed = process_row(row, anomalies)
            cleaned_rows.append(processed)

    except FileNotFoundError:
        print(f"Error: Input file not found at {INPUT_CSV}")
        return

    with open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=TARGET_HEADERS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(cleaned_rows)
    print(f"Successfully wrote cleaned data to {OUTPUT_CSV}")

    # --- Duplicate Value Detection ---
    ip_counts = {}
    mac_counts = {}
    hostname_counts = {}

    # First pass: count occurrences of values
    for row in cleaned_rows:
        # Only check for duplicates on valid, non-special IPs
        if row.get("ip_valid") and row.get("ip"):
            try:
                ip_obj = ipaddress.ip_address(row["ip"])
                if not (ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_unspecified):
                    ip_counts.setdefault(row["ip"], []).append(row["source_row_id"])
            except ValueError:
                pass  # Ignore errors on values that might be invalid despite the flag

        if row.get("mac_valid") and row.get("mac"):
            mac_counts.setdefault(row["mac"], []).append(row["source_row_id"])
        
        if row.get("hostname_valid") and row.get("hostname"):
            hostname_counts.setdefault(row["hostname"].lower(), []).append(row["source_row_id"])

    # Second pass: create anomalies for any duplicates found
    duplicate_checks = {
        "ip": ip_counts,
        "mac": mac_counts,
        "hostname": hostname_counts
    }

    for field, counts in duplicate_checks.items():
        for value, row_ids in counts.items():
            if len(row_ids) > 1:
                # This value is a duplicate, create an anomaly for all rows that have it
                for row_id in row_ids:
                    anomalies.append({
                        "source_row_id": row_id,
                        "issues": [{
                            "field": field,
                            "type": "duplicate_value",
                            "value": value,
                            "duplicated_in_rows": row_ids
                        }],
                        "recommended_actions": [f"This {field} is a duplicate. See 'duplicated_in_rows' for all conflicting records."]
                    })

    # Group anomalies by source_row_id
    grouped_anomalies = {}
    for anomaly in anomalies:
        row_id = anomaly["source_row_id"]
        if row_id not in grouped_anomalies:
            grouped_anomalies[row_id] = {
                "source_row_id": row_id,
                "issues": []
            }
        # Extend the list of issues for that row_id
        grouped_anomalies[row_id]["issues"].extend(anomaly["issues"])
    
    final_anomalies_list = list(grouped_anomalies.values())

    with open(ANOMALIES_JSON, mode='w', encoding='utf-8') as outfile:
        json.dump(final_anomalies_list, outfile, indent=2)
    print(f"Successfully wrote anomalies to {ANOMALIES_JSON}")

if __name__ == "__main__":
    main()
