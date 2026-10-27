"""
Main CLI entrypoint for Ghost Data Still Exists.
Processes dataset/deletion_requests.csv and writes output.csv at repository root.
"""

import os
import sys
import csv
import json
import time

# Ensure code directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auditor import DeletionAuditAgent


def main():
    start_time = time.time()
    dataset_dir = "dataset"
    requests_path = os.path.join(dataset_dir, "deletion_requests.csv")
    output_path = "output.csv"

    print("=" * 60)
    print("Ghost Data Still Exists — Deletion Audit Agent")
    print("=" * 60)
    print(f"Loading dataset from: {dataset_dir}")
    print(f"Reading evaluation requests from: {requests_path}")

    if not os.path.exists(requests_path):
        print(f"Error: {requests_path} does not exist.")
        sys.exit(1)

    agent = DeletionAuditAgent(dataset_dir=dataset_dir)
    print(f"Ingested {len(agent.observations)} multi-system evidence observations.")
    print(f"Loaded {len(agent.system_activities)} global activities from system_activity.csv.")

    with open(requests_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print(f"Processing {len(reader)} evaluation requests...")

    output_rows = []
    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}

    for row in reader:
        result = agent.audit_case(row)
        status_counts[result["deletion_status"]] = status_counts.get(result["deletion_status"], 0) + 1
        output_rows.append(result)

    # Sort output rows strictly by case_id
    def case_sort_key(item):
        cid = item["case_id"]
        try:
            return int(cid.split("_")[1])
        except Exception:
            return cid

    output_rows.sort(key=case_sort_key)

    print(f"Writing {len(output_rows)} audited results to {output_path}...")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for row in output_rows:
            writer.writerow([row["case_id"], row["deletion_status"], row["steps_json"]])

    elapsed = time.time() - start_time
    print("\nAudit Run Completed Successfully!")
    print(f"Total Cases Processed: {len(output_rows)}")
    print(f"Status Distribution: {status_counts}")
    print(f"Total Execution Time: {elapsed:.2f} seconds")
    print(f"Completed output written to: {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()

