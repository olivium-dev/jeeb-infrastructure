from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "install-reviewed-runtime-activation.py"
PACKAGER_PATH = ROOT / "package-reviewed-runtime-activation.py"
MANIFEST_PATH = ROOT / "reviewed-runtime-activation-manifest.json"
PACKAGE_PATH = ROOT / "jeeb-msi-runtime-activation-bootstrap.tar"
STAGE_WORKFLOW = ROOT.parents[2] / ".github/workflows/stage-reviewed-msi-runtime-bootstrap.yml"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


installer = load("msi_root_installer", INSTALLER_PATH)
packager = load("msi_root_packager", PACKAGER_PATH)


class RootBootstrapTests(unittest.TestCase):
    def test_installer_and_reviewed_manifest_are_exactly_aligned(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        declared = {
            (item["packageName"], item["installedPath"], item["sha256"], item["mode"])
            for item in manifest["files"]
        }
        embedded = {
            (spec.package_name, str(spec.destination), spec.sha256, format(spec.mode, "04o"))
            for spec in installer.FILES
        }
        self.assertEqual(declared, embedded)
        self.assertEqual(manifest["targetHost"], installer.EXPECTED_HOSTNAME)
        self.assertEqual(
            (manifest["transportAccount"]["name"],
             manifest["transportAccount"]["uid"],
             manifest["transportAccount"]["gid"]),
            installer.EXPECTED_TRANSPORT_ACCOUNT,
        )
        self.assertEqual(len(installer.FILES), 5)
        self.assertTrue(installer.FILES[-1].validate_sudoers)

    def test_every_source_revision_and_digest_is_fixed(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for item in manifest["files"]:
            self.assertRegex(item["revision"], r"^[0-9a-f]{40}$")
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(item["repository"].startswith("olivium-dev/"))
            self.assertTrue(item["packageName"].startswith("payload/"))

    def test_single_file_failure_after_link_rolls_back_only_created_target(self):
        data = b"reviewed helper\n"
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "helper"
            spec = installer.FileSpec("payload/helper", target, digest, 0o755)
            with patch.object(installer, "_target_state", side_effect=installer.InstallError("verify")), \
                    patch.object(installer, "_remove_created") as removed, \
                    patch.object(installer.os, "fchown"):
                with self.assertRaises(installer.InstallError):
                    installer._install_absent(spec, data)
            removed.assert_called_once_with(spec)

    def test_install_preflights_every_target_before_first_mutation(self):
        first = installer.FileSpec("payload/a", Path("/safe/a"), "a" * 64, 0o755)
        second = installer.FileSpec("payload/b", Path("/safe/b"), "b" * 64, 0o440, True)
        events: list[str] = []

        def target_state(spec):
            events.append("check:" + spec.destination.name)
            if spec is second:
                raise installer.InstallError("target-drift")
            return "absent"

        with patch.object(installer.os, "geteuid", return_value=0), \
                patch.object(installer, "_directory"), \
                patch.object(installer, "_source_bytes", return_value=b"x"), \
                patch.object(installer, "_target_state", side_effect=target_state), \
                patch.object(installer, "_install_absent", side_effect=lambda *_: events.append("install")):
            with self.assertRaisesRegex(installer.InstallError, "target-drift"):
                installer.install(
                    package_root=Path("/safe"), specs=(first, second), validate_host=False
                )
        self.assertEqual(events, ["check:a", "check:b"])

    def test_package_is_deterministic_and_contains_no_secret_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            source_bytes = {f"source-{index}": f"payload-{index}\n".encode()
                            for index in range(5)}
            manifest = {
                "schemaVersion": 1,
                "files": [
                    {
                        "repository": "olivium-dev/example",
                        "revision": str(index) * 40,
                        "sourcePath": name,
                        "packageName": f"payload/item-{index}",
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                    for index, (name, data) in enumerate(source_bytes.items(), start=1)
                ],
            }
            manifest_path = temporary_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            fake_installer = temporary_root / "installer.py"
            fake_installer.write_text("# reviewed installer\n", encoding="utf-8")
            with patch.object(packager, "MANIFEST", manifest_path), \
                    patch.object(packager, "INSTALLER", fake_installer), \
                    patch.object(packager, "fetch",
                                 side_effect=lambda _repo, _rev, path: source_bytes[path]):
                first = Path(temporary) / "first.tar"
                second = Path(temporary) / "second.tar"
                packager.build(first)
                packager.build(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            archive = first.read_bytes()
            for forbidden in (b"MSI_SSH_PASSWORD=", b"FIREBASE_JSON=", b"SMTP_PASSWORD="):
                self.assertNotIn(forbidden, archive)

    def test_checked_in_package_and_unprivileged_stage_workflow_are_exact(self):
        self.assertEqual(
            hashlib.sha256(PACKAGE_PATH.read_bytes()).hexdigest(),
            "07dfdb54cdbb6ad4635e7190848f43f7316516d2e71de9ba6ce23f5963fa8357",
        )
        workflow = STAGE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("REF_PROTECTED: ${{ github.ref_protected }}", workflow)
        self.assertIn("[ \"$GITHUB_SHA\" = \"$EXPECTED_SHA\" ]", workflow)
        self.assertIn("MSI_SSH_USER: msi-access", workflow)
        self.assertIn("StrictHostKeyChecking yes", workflow)
        self.assertIn("PubkeyAuthentication no", workflow)
        self.assertIn("1002:1002:600", workflow)
        self.assertIn("/usr/bin/ln '$incoming' '$REMOTE_PACKAGE'", workflow)
        self.assertGreaterEqual(
            workflow.count("test ! -L /home/msi-access/.jeeb-deploy"), 3
        )
        self.assertGreaterEqual(
            workflow.count("test -d /home/msi-access/.jeeb-deploy"), 3
        )
        self.assertIn(
            '"set -euo pipefail; test -d /home/msi-access/.jeeb-deploy; test ! -L /home/msi-access/.jeeb-deploy; if test',
            workflow,
        )
        self.assertNotIn("sudo ", workflow)
        self.assertNotIn("/usr/bin/sudo", workflow)


if __name__ == "__main__":
    unittest.main()
