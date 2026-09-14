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
V1_PACKAGE_PATH = ROOT / "jeeb-msi-runtime-activation-bootstrap.tar"
PACKAGE_PATH = ROOT / "jeeb-msi-runtime-activation-bootstrap-v2.tar"
STAGE_WORKFLOW = ROOT.parents[2] / ".github/workflows/stage-reviewed-msi-runtime-bootstrap.yml"
RUNBOOK = ROOT / "README.md"


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
        self.assertEqual(len(installer.FILES), 7)
        self.assertTrue(installer.FILES[-1].validate_sudoers)
        self.assertEqual(len(installer.FILES), len(manifest["files"]))
        for spec, item in zip(installer.FILES, manifest["files"]):
            self.assertEqual(
                spec.predecessor_sha256,
                tuple(item.get("predecessorSha256", ())),
            )

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

    def test_only_reviewed_v1_policy_is_an_upgrade_predecessor(self):
        old = b"reviewed v1 policy\n"
        new = b"reviewed v2 policy\n"
        spec = installer.FileSpec(
            "payload/policy",
            Path("/safe/policy"),
            hashlib.sha256(new).hexdigest(),
            0o440,
            True,
            (hashlib.sha256(old).hexdigest(),),
        )
        with patch.object(installer, "_read_exact", return_value=old):
            self.assertEqual(installer._target_state(spec), "predecessor")
        with patch.object(installer, "_read_exact", return_value=b"unexpected\n"):
            with self.assertRaisesRegex(installer.InstallError, "target-drift"):
                installer._target_state(spec)

    def test_v2_install_uses_the_shared_root_owned_nonblocking_lock(self):
        parent = type(
            "Stat", (), {"st_mode": 0o040755, "st_uid": 0, "st_gid": 0}
        )()
        lock = type(
            "Stat",
            (),
            {"st_mode": 0o100600, "st_uid": 0, "st_gid": 0, "st_nlink": 1},
        )()
        with patch.object(installer, "_directory"), \
                patch.object(installer.os, "open", return_value=73) as opened, \
                patch.object(installer.os, "fstat", return_value=lock), \
                patch.object(installer.fcntl, "flock") as flocked, \
                patch.object(installer.os, "close") as closed:
            with installer.operation_lock():
                pass
        expected_flags = (
            os.O_RDWR | os.O_CREAT | os.O_NONBLOCK
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        )
        opened.assert_called_once_with(installer.DEPLOYMENT_LOCK, expected_flags, 0o600)
        flocked.assert_called_once_with(73, installer.fcntl.LOCK_EX | installer.fcntl.LOCK_NB)
        closed.assert_called_once_with(73)

    def test_later_failure_rolls_back_policy_upgrade_then_created_helper(self):
        helper = installer.FileSpec("payload/helper", Path("/safe/helper"), "a" * 64, 0o755)
        policy = installer.FileSpec(
            "payload/policy", Path("/safe/policy"), "b" * 64, 0o440, True,
            ("c" * 64,),
        )
        events: list[str] = []
        states = iter(("absent", "predecessor", "exact", "exact"))

        def final_state(spec):
            state = next(states)
            if state == "exact" and spec is policy:
                raise installer.InstallError("final-verification")
            return state

        with patch.object(installer.os, "geteuid", return_value=0), \
                patch.object(installer, "_directory"), \
                patch.object(installer, "_source_bytes", return_value=b"x"), \
                patch.object(installer, "_target_state", side_effect=final_state), \
                patch.object(installer, "_visudo"), \
                patch.object(installer, "_install_absent",
                             side_effect=lambda spec, _data: events.append("create:" + spec.destination.name)), \
                patch.object(installer, "_replace_predecessor",
                             side_effect=lambda spec, _data: events.append("upgrade:" + spec.destination.name) or b"old"), \
                patch.object(installer, "_restore_predecessor",
                             side_effect=lambda spec, _data: events.append("restore:" + spec.destination.name)), \
                patch.object(installer, "_remove_created",
                             side_effect=lambda spec: events.append("remove:" + spec.destination.name)):
            with self.assertRaisesRegex(installer.InstallError, "install-failed-rolled-back"):
                installer.install(
                    package_root=Path("/safe"), specs=(helper, policy), validate_host=False
                )
        self.assertEqual(
            events,
            ["create:helper", "upgrade:policy", "restore:policy", "remove:helper"],
        )

    def test_package_is_deterministic_and_contains_no_secret_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            source_bytes = {f"source-{index}": f"payload-{index}\n".encode()
                            for index in range(7)}
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
            hashlib.sha256(V1_PACKAGE_PATH.read_bytes()).hexdigest(),
            "07dfdb54cdbb6ad4635e7190848f43f7316516d2e71de9ba6ce23f5963fa8357",
        )
        self.assertEqual(
            hashlib.sha256(PACKAGE_PATH.read_bytes()).hexdigest(),
            "1d9aa98e9b2d5bed1f600a8875268d2fa2122f305d93900f93b9e4d4c59da2bf",
        )
        workflow = STAGE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("REF_PROTECTED: ${{ github.ref_protected }}", workflow)
        self.assertIn("[ \"$GITHUB_SHA\" = \"$EXPECTED_SHA\" ]", workflow)
        self.assertIn("MSI_SSH_USER: msi-access", workflow)
        self.assertIn("StrictHostKeyChecking yes", workflow)
        self.assertIn("PubkeyAuthentication no", workflow)
        self.assertGreaterEqual(workflow.count("1002:1002:600:1"), 3)
        self.assertIn("jeeb-msi-runtime-activation-bootstrap-v2.tar", workflow)
        self.assertIn("1d9aa98e9b2d5bed1f600a8875268d2fa2122f305d93900f93b9e4d4c59da2bf", workflow)
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

        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn(
            "source=/home/msi-access/.jeeb-deploy/"
            "jeeb-msi-runtime-activation-bootstrap-v2-1d9aa98e.tar",
            runbook,
        )
        self.assertIn(
            "1d9aa98e9b2d5bed1f600a8875268d2fa2122f305d93900f93b9e4d4c59da2bf",
            runbook,
        )
        self.assertIn("1002:1002:600:1", runbook)
        self.assertIn(
            "dd131899526f496ba24e1b70c7644e3f3674981ac4316f6787d6e2120094ef49",
            runbook,
        )
        self.assertIn(
            '/usr/bin/python3 -I "$package/install-reviewed-runtime-activation.py"',
            runbook,
        )


if __name__ == "__main__":
    unittest.main()
