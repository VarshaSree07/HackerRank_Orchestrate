"""
Evaluation Runner for Ghost Data Still Exists.
Evaluates the deletion audit agent against public benchmark cases and custom synthetic scenarios.
Computes case-level status accuracy, step-level accuracy, field-level accuracy, and sequence accuracy.
"""

import os
import sys
import csv
import json
from typing import Dict, List, Any

# Add parent code directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_code_dir = os.path.dirname(current_dir)
if parent_code_dir not in sys.path:
    sys.path.insert(0, parent_code_dir)

from auditor import DeletionAuditAgent


def evaluate_dataset(agent: DeletionAuditAgent, requests_path: str, ground_truth_path: str) -> Dict[str, Any]:
    with open(requests_path, "r", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        ground_truth = {r["case_id"]: r for r in csv.DictReader(f)}

    total_cases = len(requests)
    status_matches = 0
    total_steps_exp = 0
    total_steps_pred = 0
    step_matches = 0
    exact_sequence_matches = 0

    field_comparisons = {
        "phase": {"correct": 0, "total": 0},
        "system_id": {"correct": 0, "total": 0},
        "resource_id": {"correct": 0, "total": 0},
        "operation": {"correct": 0, "total": 0},
        "state": {"correct": 0, "total": 0},
        "evidence_id": {"correct": 0, "total": 0}
    }

    results = []

    for req in requests:
        cid = req["case_id"]
        pred = agent.audit_case(req)
        gt = ground_truth.get(cid)
        if not gt:
            continue

        pred_status = pred["deletion_status"]
        gt_status = gt["deletion_status"]
        is_status_correct = (pred_status == gt_status)
        if is_status_correct:
            status_matches += 1

        pred_steps = json.loads(pred["steps_json"])
        gt_steps = json.loads(gt["steps_json"])

        total_steps_exp += len(gt_steps)
        total_steps_pred += len(pred_steps)

        # Check sequence match
        seq_match = is_status_correct and (len(pred_steps) == len(gt_steps))
        if seq_match:
            for i in range(len(gt_steps)):
                for k in ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]:
                    if pred_steps[i].get(k) != gt_steps[i].get(k):
                        seq_match = False
                        break
        if seq_match:
            exact_sequence_matches += 1

        # Step and field level comparison
        for i, s_gt in enumerate(gt_steps):
            if i < len(pred_steps):
                s_pred = pred_steps[i]
                step_exact = True
                for f_name in field_comparisons:
                    field_comparisons[f_name]["total"] += 1
                    if s_gt.get(f_name) == s_pred.get(f_name):
                        field_comparisons[f_name]["correct"] += 1
                    else:
                        step_exact = False
                if step_exact:
                    step_matches += 1
            else:
                for f_name in field_comparisons:
                    field_comparisons[f_name]["total"] += 1

        results.append({
            "case_id": cid,
            "status_match": is_status_correct,
            "sequence_match": seq_match,
            "pred_status": pred_status,
            "gt_status": gt_status
        })

    status_acc = (status_matches / total_cases * 100.0) if total_cases else 0.0
    seq_acc = (exact_sequence_matches / total_cases * 100.0) if total_cases else 0.0
    step_acc = (step_matches / total_steps_exp * 100.0) if total_steps_exp else 0.0

    field_acc = {}
    for f_name, counts in field_comparisons.items():
        field_acc[f_name] = (counts["correct"] / counts["total"] * 100.0) if counts["total"] else 0.0

    return {
        "total_cases": total_cases,
        "status_matches": status_matches,
        "status_accuracy": status_acc,
        "exact_sequence_matches": exact_sequence_matches,
        "sequence_accuracy": seq_acc,
        "total_steps_expected": total_steps_exp,
        "total_steps_predicted": total_steps_pred,
        "step_matches": step_matches,
        "step_accuracy": step_acc,
        "field_accuracy": field_acc,
        "case_results": results
    }


def main():
    repo_root = os.path.dirname(parent_code_dir)
    dataset_dir = os.path.join(repo_root, "dataset")
    sample_reqs = os.path.join(dataset_dir, "sample_deletion_requests.csv")
    sample_gt = os.path.join(dataset_dir, "sample_output.csv")

    print("=" * 60)
    print("Ghost Data Still Exists — Evaluation Suite")
    print("=" * 60)

    agent = DeletionAuditAgent(dataset_dir)
    print(f"Loaded auditor with {len(agent.observations)} observations.")

    print(f"\nEvaluating on public sample requests: {sample_reqs}")
    metrics = evaluate_dataset(agent, sample_reqs, sample_gt)

    print("\n" + "-" * 40)
    print("BENCHMARK EVALUATION RESULTS")
    print("-" * 40)
    print(f"Case Status Accuracy:    {metrics['status_accuracy']:.2f}% ({metrics['status_matches']}/{metrics['total_cases']})")
    print(f"Sequence Accuracy:       {metrics['sequence_accuracy']:.2f}% ({metrics['exact_sequence_matches']}/{metrics['total_cases']})")
    print(f"Step-level Accuracy:     {metrics['step_accuracy']:.2f}% ({metrics['step_matches']}/{metrics['total_steps_expected']})")
    print("\nField-level Accuracies:")
    for f_name, acc in metrics["field_accuracy"].items():
        print(f"  - {f_name:12s}: {acc:.2f}%")


if __name__ == "__main__":
    main()

