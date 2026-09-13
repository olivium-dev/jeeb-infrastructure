#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import dispatch_credential_validation_only as subject


SECRET = "JEEB_STAGING_CHAT_SERVICE_JEEB_FIREBASE_JSON"
FULL_REPO = "olivium-dev/chat-service"


class Tests(unittest.TestCase):
    def target(self):
        return subject.Target(
            "chat-service",
            "main",
            "staging",
            (SECRET,),
            ("JEEB_FIREBASE_CLIENT_EMAIL_SHA256",),
        )

    @staticmethod
    def metadata(path, key, _category):
        if key == "repositories":
            return [{"full_name": FULL_REPO}]
        if key == "secrets":
            return []
        if "/environments/staging/" in path:
            return [{
                "name": "JEEB_FIREBASE_CLIENT_EMAIL_SHA256",
                "value": "1" * 64,
            }]
        return []

    @staticmethod
    def gh(path, _category):
        if path.endswith("/branches/main"):
            return {"protected": True, "commit": {"sha": "a" * 40}}
        if path == f"repos/{FULL_REPO}":
            return {"default_branch": "main"}
        if path == f"orgs/{subject.ORG}/actions/secrets/{SECRET}":
            return {"name": SECRET, "visibility": "selected"}
        raise AssertionError(path)

    def test_environment_fallback_cannot_mask_missing_org_secret(self):
        def metadata(path, key, category):
            if key == "secrets" and "/environments/staging/" in path:
                return [{"name": SECRET}]
            return self.metadata(path, key, category)

        def gh(path, category):
            if path == f"orgs/{subject.ORG}/actions/secrets/{SECRET}":
                raise subject.GateError("metadata-unavailable:org-secret")
            return self.gh(path, category)

        with mock.patch.object(subject, "gh_json", side_effect=gh), \
             mock.patch.object(subject, "bounded_items", side_effect=metadata):
            with self.assertRaisesRegex(subject.GateError, "org-secret"):
                subject.require_exact_scope(self.target())

    def test_present_org_secret_is_rejected_when_repository_shadowed(self):
        def metadata(path, key, category):
            if (
                key == "secrets"
                and path.startswith("repos/")
                and "/environments/" not in path
            ):
                return [{"name": SECRET}]
            return self.metadata(path, key, category)

        with mock.patch.object(subject, "gh_json", side_effect=self.gh), \
             mock.patch.object(subject, "bounded_items", side_effect=metadata):
            with self.assertRaisesRegex(subject.GateError, "higher-precedence-shadow"):
                subject.require_exact_scope(self.target())

    def test_selected_acl_must_contain_only_the_consumer(self):
        def metadata(path, key, category):
            if key == "repositories":
                return [{"full_name": FULL_REPO}, {"full_name": "olivium-dev/other"}]
            return self.metadata(path, key, category)

        with mock.patch.object(subject, "gh_json", side_effect=self.gh), \
             mock.patch.object(subject, "bounded_items", side_effect=metadata):
            with self.assertRaisesRegex(subject.GateError, "org-secret-acl-mismatch"):
                subject.require_exact_scope(self.target())

    def test_exact_org_only_metadata_passes(self):
        with mock.patch.object(subject, "gh_json", side_effect=self.gh), \
             mock.patch.object(subject, "bounded_items", side_effect=self.metadata):
            commit = subject.require_exact_scope(self.target())
        self.assertEqual(commit, "a" * 40)


if __name__ == "__main__":
    unittest.main()
