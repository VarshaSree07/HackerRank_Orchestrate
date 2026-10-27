"""
LLM Client Module for Ghost Data Still Exists.
Provides robust live LLM integration for unstructured request intent classification
and evidence interpretation, with granular error tracking and graceful deterministic fallback.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Tuple

try:
    import requests
    from requests.exceptions import Timeout, ConnectionError, RequestException
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

logger = logging.getLogger("DeletionAuditLLM")


class LLMClient:
    """
    Live LLM client supporting Google Gemini, OpenAI, and Anthropic REST endpoints.
    Provides rigorous credential checking, prompt dispatch, JSON response parsing,
    granular error categorization (auth failure, rate limit, timeout, network error, malformed response),
    and verifiable telemetry tracking.
    """

    def __init__(self):
        self.openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.mock_endpoint = os.environ.get("MOCK_LLM_ENDPOINT", "").strip()

        # Telemetry & Accounting
        self.calls_attempted = 0
        self.calls_succeeded = 0
        self.calls_failed = 0
        self.fallback_count = 0
        self.input_tokens = 0
        self.output_tokens = 0

        # Last error diagnostics
        self.last_status_code: Optional[int] = None
        self.last_error_type: Optional[str] = None
        self.last_error_message: Optional[str] = None
        self.fallback_reasons: Dict[str, int] = {}

    @property
    def is_live_api_configured(self) -> bool:
        """Returns True ONLY if an authoritative API credential exists."""
        return bool(self.gemini_key or self.openai_key or self.anthropic_key or self.mock_endpoint)

    @property
    def active_provider(self) -> Optional[str]:
        if self.gemini_key:
            return "Google Gemini"
        if self.openai_key:
            return "OpenAI"
        if self.anthropic_key:
            return "Anthropic"
        if self.mock_endpoint:
            return "Mock / Test Endpoint"
        return None

    def _record_fallback(self, reason: str, details: str = "") -> None:
        self.fallback_count += 1
        self.last_error_type = reason
        self.last_error_message = details
        self.fallback_reasons[reason] = self.fallback_reasons.get(reason, 0) + 1

    def call_raw(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """
        Calls the active external LLM API endpoint via standard HTTPS.
        Returns the raw string output, or None if credentials are absent or request fails.
        """
        if not self.is_live_api_configured:
            self._record_fallback("NO_CREDENTIALS", "No LLM API keys configured in environment.")
            return None

        self.calls_attempted += 1

        # 1. Google Gemini REST API
        if self.gemini_key:
            return self._call_gemini(prompt, system_prompt)

        # 2. OpenAI REST API
        if self.openai_key:
            return self._call_openai(prompt, system_prompt)

        # 3. Anthropic REST API
        if self.anthropic_key:
            return self._call_anthropic(prompt, system_prompt)

        # 4. Mock / Local Test Server
        if self.mock_endpoint:
            return self._call_mock(prompt, system_prompt)

        return None

    def _call_gemini(self, prompt: str, system_prompt: str) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
        }
        headers = {"Content-Type": "application/json"}
        try:
            if HAS_REQUESTS:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                self.last_status_code = resp.status_code
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    self.calls_succeeded += 1
                    self.input_tokens += len(prompt) // 4
                    self.output_tokens += len(text) // 4
                    return text
                elif resp.status_code in (401, 403):
                    self.calls_failed += 1
                    self._record_fallback("AUTH_FAILURE", f"Gemini auth failed: HTTP {resp.status_code}")
                    return None
                elif resp.status_code == 429:
                    self.calls_failed += 1
                    self._record_fallback("RATE_LIMIT", "Gemini rate limit exceeded: HTTP 429")
                    return None
                else:
                    self.calls_failed += 1
                    self._record_fallback("HTTP_ERROR", f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
                    return None
            else:
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    self.calls_succeeded += 1
                    self.input_tokens += len(prompt) // 4
                    self.output_tokens += len(text) // 4
                    return text
        except Timeout:
            self.calls_failed += 1
            self._record_fallback("TIMEOUT", "Gemini request timed out after 10s")
            return None
        except ConnectionError:
            self.calls_failed += 1
            self._record_fallback("NETWORK_ERROR", "Failed to connect to Google Gemini endpoint")
            return None
        except Exception as e:
            self.calls_failed += 1
            self._record_fallback("UNEXPECTED_ERROR", str(e))
            return None

    def _call_openai(self, prompt: str, system_prompt: str) -> Optional[str]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt or "You are an expert data privacy audit assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        try:
            if HAS_REQUESTS:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                self.last_status_code = resp.status_code
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    self.calls_succeeded += 1
                    self.input_tokens += usage.get("prompt_tokens", len(prompt) // 4)
                    self.output_tokens += usage.get("completion_tokens", len(text) // 4)
                    return text
                elif resp.status_code in (401, 403):
                    self.calls_failed += 1
                    self._record_fallback("AUTH_FAILURE", f"OpenAI auth failed: HTTP {resp.status_code}")
                    return None
                elif resp.status_code == 429:
                    self.calls_failed += 1
                    self._record_fallback("RATE_LIMIT", "OpenAI rate limit exceeded: HTTP 429")
                    return None
                else:
                    self.calls_failed += 1
                    self._record_fallback("HTTP_ERROR", f"OpenAI HTTP {resp.status_code}: {resp.text[:200]}")
                    return None
            else:
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    text = data["choices"][0]["message"]["content"]
                    self.calls_succeeded += 1
                    self.input_tokens += len(prompt) // 4
                    self.output_tokens += len(text) // 4
                    return text
        except Timeout:
            self.calls_failed += 1
            self._record_fallback("TIMEOUT", "OpenAI request timed out after 10s")
            return None
        except ConnectionError:
            self.calls_failed += 1
            self._record_fallback("NETWORK_ERROR", "Failed to connect to OpenAI endpoint")
            return None
        except Exception as e:
            self.calls_failed += 1
            self._record_fallback("UNEXPECTED_ERROR", str(e))
            return None

    def _call_anthropic(self, prompt: str, system_prompt: str) -> Optional[str]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}]
        }
        try:
            if HAS_REQUESTS:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                self.last_status_code = resp.status_code
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["content"][0]["text"]
                    self.calls_succeeded += 1
                    self.input_tokens += data.get("usage", {}).get("input_tokens", len(prompt) // 4)
                    self.output_tokens += data.get("usage", {}).get("output_tokens", len(text) // 4)
                    return text
                elif resp.status_code in (401, 403):
                    self.calls_failed += 1
                    self._record_fallback("AUTH_FAILURE", f"Anthropic auth failed: HTTP {resp.status_code}")
                    return None
                elif resp.status_code == 429:
                    self.calls_failed += 1
                    self._record_fallback("RATE_LIMIT", "Anthropic rate limit exceeded: HTTP 429")
                    return None
                else:
                    self.calls_failed += 1
                    self._record_fallback("HTTP_ERROR", f"Anthropic HTTP {resp.status_code}: {resp.text[:200]}")
                    return None
        except Timeout:
            self.calls_failed += 1
            self._record_fallback("TIMEOUT", "Anthropic request timed out after 10s")
            return None
        except ConnectionError:
            self.calls_failed += 1
            self._record_fallback("NETWORK_ERROR", "Failed to connect to Anthropic endpoint")
            return None
        except Exception as e:
            self.calls_failed += 1
            self._record_fallback("UNEXPECTED_ERROR", str(e))
            return None

    def _call_mock(self, prompt: str, system_prompt: str) -> Optional[str]:
        """Calls local mock endpoint when configured for testing."""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {"prompt": prompt, "system_prompt": system_prompt}
            resp = requests.post(self.mock_endpoint, json=payload, headers=headers, timeout=2)
            self.last_status_code = resp.status_code
            if resp.status_code == 200:
                self.calls_succeeded += 1
                return resp.text
            else:
                self.calls_failed += 1
                self._record_fallback("MOCK_HTTP_ERROR", f"Mock server returned {resp.status_code}")
                return None
        except Exception as e:
            self.calls_failed += 1
            self._record_fallback("MOCK_NETWORK_ERROR", str(e))
            return None

    def classify_request_intent(self, case_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        """
        Uses an LLM to analyze user request text and classify whether it authorizes
        permanent account/data deletion, or is a non-deletion inquiry.
        """
        if not self.is_live_api_configured:
            return None

        system_prompt = (
            "You are a GDPR/CCPA Privacy Legal Audit Assistant. Determine whether the user's message "
            "authorizes permanent account and personal data deletion (Right to Erasure), or is a non-deletion "
            "request (such as Right of Access, Data Portability, Login Reset, Name/Phone Correction, or "
            "Marketing Opt-Out where the account must remain active).\n"
            "Return JSON: {\"is_deletion_authorized\": bool, \"action_category\": str, \"reasoning\": str}"
        )
        prompt = (
            f"Case ID: {case_id}\n"
            f"User Request Text: \"\"\"{request_text}\"\"\"\n\n"
            "Analyze the intent and return structured JSON."
        )

        raw = self.call_raw(prompt, system_prompt)
        if not raw:
            return None

        try:
            parsed = json.loads(raw)
            if "is_deletion_authorized" not in parsed:
                self.calls_failed += 1
                self._record_fallback("MALFORMED_RESPONSE", "Missing 'is_deletion_authorized' in JSON")
                return None
            return parsed
        except Exception as e:
            self.calls_failed += 1
            self._record_fallback("MALFORMED_RESPONSE", f"Invalid JSON response: {e}")
            return None

    def interpret_unstructured_evidence(self, file_id: str, content: str, subject_identifiers: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Uses an LLM to inspect free-form support tickets, message bodies, or log payloads
        for unredacted personal identifiers or active sync triggers.
        """
        if not self.is_live_api_configured:
            return None

        system_prompt = (
            "You are an automated privacy compliance inspector. Inspect the provided business text "
            "and determine whether any of the subject's direct identifiers (name, email, phone) remain exposed, "
            "or if an active synchronization process is ongoing.\n"
            "Return JSON: {\"findings\": [{\"system_id\": str, \"resource_id\": str, \"issue\": str, \"has_exposed_pii\": bool}]}"
        )
        prompt = (
            f"File ID: {file_id}\n"
            f"Subject Identifiers: {subject_identifiers}\n"
            f"Content:\n\"\"\"{content[:1500]}\"\"\"\n"
        )

        raw = self.call_raw(prompt, system_prompt)
        if not raw:
            return None

        try:
            parsed = json.loads(raw)
            return parsed.get("findings", [])
        except Exception as e:
            self.calls_failed += 1
            self._record_fallback("MALFORMED_RESPONSE", f"Invalid JSON in evidence interpretation: {e}")
            return None
