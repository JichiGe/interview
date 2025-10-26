# Manual AI Enrichment - Final Batch Prompt

This file provides a single, comprehensive prompt to enrich all necessary `device_type` and `owner` fields at once, as per the project requirements.

**Instructions:**

1.  **Copy the entire "Final Batch Prompt for AI"** section below.
2.  **Paste it into an AI chat interface** that allows for setting model parameters.
3.  **Set the Temperature to `0.2` or lower.** This is critical for reproducible and non-creative outputs.
4.  The AI should return a single JSON array containing all the results.
5.  **Manually update the `inventory_clean.csv` file** with the `device_type`, `owner_team`, etc., provided by the AI for each corresponding `source_row_id`.

---

### Final Batch Prompt for AI

```
You are an expert network inventory analyst. Your task is to act as a data cleaning assistant. For a given list of network devices, you must perform two actions:
1. Infer the most likely `device_type` from the list: [server, switch, gateway, printer, iot, workstation, access-point, firewall, unknown].
2. If the `owner` field seems to be a team or department name, infer a canonical `owner_team` name (e.g., "ops" should become "Operations"). If the owner is an email or a person's name, leave the team field as null.

Analyze the following JSON array of devices. Return a single JSON array where each object contains the `source_row_id` and all the fields you were able to infer.

**Input Devices:**
[
  {
    "source_row_id": "2",
    "hostname": "host-02",
    "owner": "ops",
    "notes": "edge gw?"
  },
  {
    "source_row_id": "4",
    "hostname": "printer-01",
    "owner": "Facilities",
    "notes": ""
  },
  {
    "source_row_id": "5",
    "hostname": "iot-cam01",
    "owner": "sec",
    "notes": "camera PoE on port 3"
  },
  {
    "source_row_id": "6",
    "hostname": "local-test",
    "owner": "",
    "notes": "N/A"
  },
  {
    "source_row_id": "7",
    "hostname": "host-apipa",
    "owner": "",
    "notes": ""
  },
  {
    "source_row_id": "8",
    "hostname": "srv-10",
    "owner": "platform",
    "notes": ""
  },
  {
    "source_row_id": "9",
    "hostname": "badhost",
    "owner": "",
    "notes": ""
  },
  {
    "source_row_id": "10",
    "hostname": "neg",
    "owner": "",
    "notes": ""
  },
  {
    "source_row_id": "11",
    "hostname": "bcast",
    "owner": "",
    "notes": "Potential broadcast"
  },
  {
    "source_row_id": "12",
    "hostname": "netid",
    "owner": "",
    "notes": "Potential network id"
  },
  {
    "source_row_id": "13",
    "hostname": "dns-google",
    "owner": "",
    "notes": ""
  },
  {
    "source_row_id": "15",
    "hostname": "missing-ip",
    "owner": "",
    "notes": ""
  }
]

**Expected Output Format (Example):**
[
  {
    "source_row_id": "2",
    "inferred_device_type": "gateway",
    "inferred_owner_team": "Operations"
  },
  {
    "source_row_id": "4",
    "inferred_device_type": "printer",
    "inferred_owner_team": "Facilities"
  }
]
```
