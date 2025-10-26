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
    "ip", "ip_valid", "ip_version", "subnet_cidr", "reverse_ptr",
    "hostname", "hostname_valid", "fqdn", "fqdn_consistent",
    "mac", "mac_valid",
    "owner", "owner_email", "owner_team",
    "device_type", "device_type_confidence",
    "site", "site_normalized",
    "source_row_id", "normalization_steps"
]

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

    # --- Device Type (Manual step) ---
    processed["device_type"] = row.get("device_type", "").strip()

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

    with open(ANOMALIES_JSON, mode='w', encoding='utf-8') as outfile:
        json.dump(anomalies, outfile, indent=2)
    print(f"Successfully wrote anomalies to {ANOMALIES_JSON}")

if __name__ == "__main__":
    main()
