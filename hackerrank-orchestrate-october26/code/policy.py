"""
Policy Engine for Ghost Data Still Exists.
Enforces deletion_rules.csv, determines remediation operations, and defines verification checks.
"""

from typing import Dict, Any, Tuple


class PolicyEngine:
    PHASE_RANK = {
        "FINDING": 1,
        "REMEDIATION": 2,
        "VERIFICATION": 3
    }

    OPERATION_RANK = {
        # Phase: FINDING
        "REPORT_REMAINING_RECORD": 1,
        "REPORT_EXPOSED_PII": 2,
        "REPORT_ACTIVE_DATA_FLOW": 3,
        "REPORT_RESTORE_RISK": 4,
        # Phase: REMEDIATION
        "DISABLE_DATA_FLOW": 1,
        "BLOCK_RESTORE": 2,
        "DELETE_RECORD": 3,
        "REDACT_RECORD": 4,
        "ANONYMIZE_RECORD": 5,
        # Phase: VERIFICATION
        "VERIFY_RECORD_ABSENT": 1,
        "VERIFY_RECORD_PRESENT": 2,
        "VERIFY_RECORD_REDACTED": 3,
        "VERIFY_RECORD_ANONYMIZED": 4,
        "VERIFY_DATA_FLOW_DISABLED": 5,
        "VERIFY_RESTORE_BLOCKED": 6
    }

    @staticmethod
    def get_remediation_for_finding(finding_op: str, system_id: str) -> Tuple[str, str]:
        """Returns (remediation_operation, target_state)."""
        if finding_op == "REPORT_ACTIVE_DATA_FLOW":
            return "DISABLE_DATA_FLOW", "DISABLED"
        elif finding_op == "REPORT_RESTORE_RISK":
            return "BLOCK_RESTORE", "BLOCKED"
        elif finding_op == "REPORT_REMAINING_RECORD":
            return "DELETE_RECORD", "ABSENT"
        elif finding_op == "REPORT_EXPOSED_PII":
            if system_id == "analytics_platform":
                return "ANONYMIZE_RECORD", "ANONYMIZED"
            else:
                return "REDACT_RECORD", "REDACTED"
        raise ValueError(f"Unknown finding operation: {finding_op}")

    @staticmethod
    def get_verification_for_remediation(rem_op: str, system_id: str) -> Tuple[str, str]:
        """Returns (verification_operation, target_state)."""
        if rem_op == "DISABLE_DATA_FLOW":
            return "VERIFY_DATA_FLOW_DISABLED", "DISABLED"
        elif rem_op == "BLOCK_RESTORE":
            return "VERIFY_RESTORE_BLOCKED", "BLOCKED"
        elif rem_op == "DELETE_RECORD":
            return "VERIFY_RECORD_ABSENT", "ABSENT"
        elif rem_op == "REDACT_RECORD":
            return "VERIFY_RECORD_REDACTED", "REDACTED"
        elif rem_op == "ANONYMIZE_RECORD":
            return "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"
        raise ValueError(f"Unknown remediation operation: {rem_op}")

    @classmethod
    def step_sort_key(cls, step: Dict[str, Any]) -> Tuple[int, int, str, str]:
        """Order: Phase -> Operation Table Order -> system_id ASC -> resource_id ASC."""
        phase_r = cls.PHASE_RANK.get(step["phase"], 99)
        op_r = cls.OPERATION_RANK.get(step["operation"], 99)
        return (phase_r, op_r, step["system_id"], step["resource_id"])

