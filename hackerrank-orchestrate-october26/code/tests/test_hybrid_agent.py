"""
Unit and Integration Tests for Ghost Data Still Exists Hybrid AI Agent.
Comprehensive verification of:
1. Missing credential handling (no false AI claims).
2. Live / Mock AI intent interpretation.
3. API failure modes: Auth failure (401/403), Rate limit (429), Timeout, Network failure, Malformed response.
4. Grounded evidence validation of AI candidate findings.
5. Deterministic compliance and policy engine rules.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

try:
    from requests.exceptions import Timeout, ConnectionError
except ImportError:
    Timeout = Exception
    ConnectionError = Exception

# Add code directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_code_dir = os.path.dirname(current_dir)
if parent_code_dir not in sys.path:
    sys.path.insert(0, parent_code_dir)

from identity import IdentityResolver
from evidence_parser import EvidenceParser
from policy import PolicyEngine
from llm_client import LLMClient
from auditor import DeletionAuditAgent


class TestHybridAgentComprehensive(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.dirname(parent_code_dir)
        self.dataset_dir = os.path.join(self.repo_root, "dataset")

    def test_01_no_api_key_configured(self):
        """Situation 1: No API key configured. Confirms clean fallback without false AI claims."""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "", "GEMINI_API_KEY": "",
            "ANTHROPIC_API_KEY": "", "MOCK_LLM_ENDPOINT": ""
        }):
            llm = LLMClient()
            self.assertFalse(llm.is_live_api_configured)
            self.assertIsNone(llm.active_provider)

            res = llm.call_raw("test prompt")
            self.assertIsNone(res)
            self.assertEqual(llm.last_error_type, "NO_CREDENTIALS")
            self.assertEqual(llm.fallback_count, 1)

            agent = DeletionAuditAgent(self.dataset_dir)
            self.assertFalse(agent.ai_telemetry["is_live_ai_configured"])
            self.assertEqual(agent.ai_telemetry["ai_intent_calls"], 0)

            # Test deterministic fallback correctly identifies non-deletion
            is_non_del = agent.is_non_deletion_request("case_533", "The mobile number on my profile is out of date. Please replace it.")
            self.assertTrue(is_non_del)
            self.assertEqual(agent.ai_telemetry["ai_intent_calls"], 0)

    def test_02_validly_configured_provider_mock(self):
        """Situation 2: Valid provider response. Confirms AI intent is parsed and incorporated."""
        mock_resp = json.dumps({
            "is_deletion_authorized": False,
            "action_category": "PORTABILITY_REQUEST",
            "reasoning": "User requested data download, explicitly asked to keep account active."
        })

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-valid-key"}):
            agent = DeletionAuditAgent(self.dataset_dir)
            self.assertTrue(agent.ai_telemetry["is_live_ai_configured"])
            self.assertEqual(agent.ai_telemetry["provider"], "OpenAI")

            with patch.object(agent.llm, "call_raw", return_value=mock_resp):
                is_non_del = agent.is_non_deletion_request("case_535", "I want to download my data. Please keep the account.")
                self.assertTrue(is_non_del)
                self.assertEqual(agent.ai_telemetry["ai_intent_calls"], 1)
                self.assertEqual(len(agent.ai_telemetry["ai_classified_cases"]), 1)
                self.assertEqual(agent.ai_telemetry["ai_classified_cases"][0]["action_category"], "PORTABILITY_REQUEST")

    def test_03_invalid_credentials_auth_failure(self):
        """Situation 3: Invalid credentials / 401 Auth Failure. Confirms error recorded & fallback utilized."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-invalid-expired-key"}):
            llm = LLMClient()
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.text = '{"error": {"message": "Incorrect API key provided"}}'

            with patch("requests.post", return_value=mock_resp):
                res = llm.call_raw("test prompt")
                self.assertIsNone(res)
                self.assertEqual(llm.last_status_code, 401)
                self.assertEqual(llm.last_error_type, "AUTH_FAILURE")
                self.assertEqual(llm.calls_failed, 1)
                self.assertEqual(llm.fallback_count, 1)

    def test_04_rate_limiting(self):
        """Situation 4: Rate limiting / 429 Too Many Requests."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-rate-limited-key"}):
            llm = LLMClient()
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_resp.text = '{"error": {"message": "Rate limit exceeded"}}'

            with patch("requests.post", return_value=mock_resp):
                res = llm.call_raw("test prompt")
                self.assertIsNone(res)
                self.assertEqual(llm.last_status_code, 429)
                self.assertEqual(llm.last_error_type, "RATE_LIMIT")
                self.assertEqual(llm.calls_failed, 1)

    def test_05_timeout(self):
        """Situation 5: Request timeout."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-timeout-key"}):
            llm = LLMClient()
            with patch("requests.post", side_effect=Timeout("Connection timed out")):
                res = llm.call_raw("test prompt")
                self.assertIsNone(res)
                self.assertEqual(llm.last_error_type, "TIMEOUT")
                self.assertEqual(llm.calls_failed, 1)

    def test_06_network_failure(self):
        """Situation 6: Network connection failure."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-network-fail-key"}):
            llm = LLMClient()
            with patch("requests.post", side_effect=ConnectionError("DNS lookup failed")):
                res = llm.call_raw("test prompt")
                self.assertIsNone(res)
                self.assertEqual(llm.last_error_type, "NETWORK_ERROR")
                self.assertEqual(llm.calls_failed, 1)

    def test_07_malformed_response(self):
        """Situation 7: Malformed / non-JSON response from LLM."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            llm = LLMClient()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"choices": [{"message": {"content": "This is raw text, not valid JSON"}}]}

            with patch("requests.post", return_value=mock_resp):
                intent = llm.classify_request_intent("case_01", "Please delete my account")
                self.assertIsNone(intent)
                self.assertEqual(llm.last_error_type, "MALFORMED_RESPONSE")

    def test_08_evidence_grounding_validation(self):
        """Verify strict evidence manifest and temporal bounds validation for AI candidate findings."""
        agent = DeletionAuditAgent(self.dataset_dir)
        audit_at = "2026-09-15T12:00:00Z"
        req_at = "2026-09-01T12:00:00Z"

        valid_finding = {
            "system_id": "account_service",
            "resource_id": "account_005",
            "operation": "REPORT_REMAINING_RECORD",
            "file_id": "evidence_54",
            "captured_at": "2026-09-02T10:00:00Z"
        }
        self.assertTrue(agent.validate_candidate_finding(valid_finding, audit_at, req_at))

        # Rejection: Ungrounded file_id
        bad_fid = dict(valid_finding, file_id="hallucinated_evidence_999")
        self.assertFalse(agent.validate_candidate_finding(bad_fid, audit_at, req_at))

        # Rejection: Captured after cutoff
        future_finding = dict(valid_finding, captured_at="2026-10-01T00:00:00Z")
        self.assertFalse(agent.validate_candidate_finding(future_finding, audit_at, req_at))

        # Rejection: Captured before deletion requested
        stale_finding = dict(valid_finding, captured_at="2026-08-01T00:00:00Z")
        self.assertFalse(agent.validate_candidate_finding(stale_finding, audit_at, req_at))

        # Rejection: Invalid invented platform
        bad_sys = dict(valid_finding, system_id="fake_storage_service")
        self.assertFalse(agent.validate_candidate_finding(bad_sys, audit_at, req_at))

    def test_09_deterministic_policy_enforcement(self):
        """Verify deterministic rules in PolicyEngine."""
        # 1. Action mapping
        op, st = PolicyEngine.get_remediation_for_finding("REPORT_ACTIVE_DATA_FLOW", "integration_service")
        self.assertEqual(op, "DISABLE_DATA_FLOW")
        self.assertEqual(st, "DISABLED")

        # 2. Ordering
        step_f = {"phase": "FINDING", "operation": "REPORT_REMAINING_RECORD", "system_id": "account_service", "resource_id": "account_001"}
        step_r = {"phase": "REMEDIATION", "operation": "DELETE_RECORD", "system_id": "account_service", "resource_id": "account_001"}
        step_v = {"phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "system_id": "account_service", "resource_id": "account_001"}

        self.assertLess(PolicyEngine.step_sort_key(step_f), PolicyEngine.step_sort_key(step_r))
        self.assertLess(PolicyEngine.step_sort_key(step_r), PolicyEngine.step_sort_key(step_v))

    def test_10_account_resolution_and_zero_padding(self):
        """Regression Test: Verify 3-digit zero-padding for initial users and FIFO activity resolution."""
        agent = DeletionAuditAgent(self.dataset_dir)
        # 1. user_01 through user_10 must be formatted as account_001..account_010
        self.assertEqual(agent.resolve_account_id("user_01", "2026-08-18T09:14:00Z", "2026-08-20T16:42:00Z", "COMPLETE"), "account_001")
        self.assertEqual(agent.resolve_account_id("user_05", "2026-08-27T14:17:00Z", "2026-08-28T09:03:00Z", "COMPLETE"), "account_005")
        self.assertEqual(agent.resolve_account_id("user_10", "2026-08-31T15:42:00Z", "2026-09-02T10:08:00Z", "COMPLETE"), "account_010")

        # 2. Activity-based resolution for user_12 (COMPLETE) -> account_9797
        acc_12 = agent.resolve_account_id("user_12", "2026-08-23T12:00:00Z", "2026-08-25T12:00:00Z", "COMPLETE")
        self.assertEqual(acc_12, "account_9797")

    def test_11_evidence_retention_of_anonymized_records(self):
        """Regression Test: Verify parser preserves anonymized records and 404 absence lookups."""
        parser = EvidenceParser(self.dataset_dir)
        obs = parser.parse_all()
        # Ensure anonymized analytics records are not dropped when user_id is None
        anonymized_analytics = [o for o in obs if o.get("system_id") == "analytics_platform" and o.get("operation") == "VERIFY_RECORD_ANONYMIZED"]
        self.assertTrue(len(anonymized_analytics) > 0)
        # Verify analytics_901 from evidence_56 is present
        an_901 = next((o for o in anonymized_analytics if o.get("resource_id") == "analytics_901"), None)
        self.assertIsNotNone(an_901)
        self.assertEqual(an_901["file_id"], "evidence_56")
        self.assertEqual(an_901["state"], "ANONYMIZED")


if __name__ == "__main__":
    unittest.main()
