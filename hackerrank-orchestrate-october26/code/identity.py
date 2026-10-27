"""
Identity Resolution Module for Ghost Data Still Exists.
Resolves stable user IDs, current identity profiles, and historical aliases (emails, phones, hashes).
"""

import os
import csv
from typing import Dict, Set, Optional, Any


class IdentityResolver:
    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.users_by_id: Dict[str, Dict[str, Any]] = {}
        self.email_to_uid: Dict[str, str] = {}
        self.phone_to_uid: Dict[str, str] = {}
        self.hash_to_uid: Dict[str, str] = {}
        self._load_identities()
        self._load_audit_logs()

    def _load_identities(self) -> None:
        identities_path = os.path.join(self.dataset_dir, "user_identities.csv")
        if not os.path.exists(identities_path):
            raise FileNotFoundError(f"User identities file not found: {identities_path}")

        with open(identities_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"]
                email = row["email"].strip().lower()
                phone = row["phone"].strip()
                email_hash = row["email_hash"].strip()
                name = row["name"].strip()

                self.users_by_id[uid] = {
                    "user_id": uid,
                    "name": name,
                    "primary_email": email,
                    "primary_phone": phone,
                    "primary_hash": email_hash,
                    "emails": {email},
                    "phones": {phone},
                    "email_hashes": {email_hash},
                    "updated_at": row.get("updated_at", "")
                }

                if email:
                    self.email_to_uid[email] = uid
                if phone:
                    self.phone_to_uid[phone] = uid
                if email_hash:
                    self.hash_to_uid[email_hash] = uid

    def _load_audit_logs(self) -> None:
        audit_path = os.path.join(self.dataset_dir, "user_audit_log.csv")
        if not os.path.exists(audit_path):
            return

        with open(audit_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"]
                if uid not in self.users_by_id:
                    continue

                field = row.get("field_name", "").strip()
                old_val = row.get("old_value", "").strip()
                new_val = row.get("new_value", "").strip()

                if field == "email":
                    if old_val:
                        old_lower = old_val.lower()
                        self.users_by_id[uid]["emails"].add(old_lower)
                        self.email_to_uid[old_lower] = uid
                    if new_val:
                        new_lower = new_val.lower()
                        self.users_by_id[uid]["emails"].add(new_lower)
                        self.email_to_uid[new_lower] = uid
                elif field == "phone":
                    if old_val:
                        self.users_by_id[uid]["phones"].add(old_val)
                        self.phone_to_uid[old_val] = uid
                    if new_val:
                        self.users_by_id[uid]["phones"].add(new_val)
                        self.phone_to_uid[new_val] = uid
                elif field == "email_hash":
                    if old_val:
                        self.users_by_id[uid]["email_hashes"].add(old_val)
                        self.hash_to_uid[old_val] = uid
                    if new_val:
                        self.users_by_id[uid]["email_hashes"].add(new_val)
                        self.hash_to_uid[new_val] = uid

    def resolve(self, identifier: Optional[str]) -> Optional[str]:
        """Resolves any identifier (user_id, email, phone, or hash) to a stable user_id."""
        if not identifier:
            return None
        token = str(identifier).strip()
        if token in self.users_by_id:
            return token
        token_lower = token.lower()
        if token_lower in self.email_to_uid:
            return self.email_to_uid[token_lower]
        if token in self.phone_to_uid:
            return self.phone_to_uid[token]
        if token in self.hash_to_uid:
            return self.hash_to_uid[token]
        return None

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.users_by_id.get(user_id)

