#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ASSEMBLER = BASE_DIR / "scripts" / "assemble-release.py"
VALIDATOR = BASE_DIR / "scripts" / "validate-release.py"


class AssembleReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sources: dict[str, Path] = {}
        for name in ("shell", "cases", "deliveries", "settlements"):
            source = self.root / name
            source.mkdir()
            self.sources[name] = source

        (self.sources["shell"] / "index.html").write_text(
            '<script src="main.js"></script>\n', encoding="utf-8"
        )
        (self.sources["shell"] / "main.js").write_text(
            'const remotes=["/mf/cases/remoteEntry.js",'
            '"/mf/deliveries/remoteEntry.js",'
            '"/mf/settlements/remoteEntry.js"];const gateway="/gateway";\n',
            encoding="utf-8",
        )
        for name in ("cases", "deliveries", "settlements"):
            (self.sources[name] / "remoteEntry.js").write_text(
                f'__webpack_public_path__="/mf/{name}/";\n', encoding="utf-8"
            )
            (self.sources[name] / "123.js").write_text(
                f'console.log("{name}-lazy")\n', encoding="utf-8"
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def command(self, output: Path) -> list[str]:
        return [
            sys.executable,
            str(ASSEMBLER),
            "--shell",
            str(self.sources["shell"]),
            "--cases",
            str(self.sources["cases"]),
            "--deliveries",
            str(self.sources["deliveries"]),
            "--settlements",
            str(self.sources["settlements"]),
            "--output",
            str(output),
            "--release-id",
            "release-test",
            "--cms-commit",
            "a" * 40,
            "--gateway-commit",
            "b" * 40,
            "--openapi-sha256",
            "c" * 64,
        ]

    def test_assembles_exact_production_remote_layout_and_manifest(self) -> None:
        output = self.root / "artifact"
        subprocess.run(self.command(output), check=True, capture_output=True, text=True)
        subprocess.run(
            [sys.executable, str(VALIDATOR), str(output), "--expected-release-id", "release-test"],
            check=True,
            capture_output=True,
            text=True,
        )

        for remote in ("cases", "deliveries", "settlements"):
            self.assertTrue((output / "mf" / remote / "remoteEntry.js").is_file())
            self.assertTrue((output / "mf" / remote / "123.js").is_file())
        self.assertFalse((output / "mf" / "case-management").exists())

        manifest_names = {
            line.split("  ", 1)[1]
            for line in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        }
        inventory = {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        }
        self.assertEqual(manifest_names, inventory)
        metadata = json.loads((output / "release.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["cmsCommit"], "a" * 40)
        self.assertEqual(metadata["gatewayCommit"], "b" * 40)
        self.assertEqual(metadata["openapiSha256"], "c" * 64)

        for name in inventory:
            expected = next(
                line[:64]
                for line in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
                if line.endswith(f"  {name}")
            )
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)

    def test_rejects_output_nested_inside_a_source(self) -> None:
        output = self.sources["shell"] / "artifact"
        result = subprocess.run(self.command(output), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output must not be inside the shell dist", result.stderr)

    def test_rejects_shell_paths_owned_by_the_assembler(self) -> None:
        (self.sources["shell"] / "release.json").write_text("{}", encoding="utf-8")
        result = subprocess.run(self.command(self.root / "artifact"), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assembler-reserved path", result.stderr)


if __name__ == "__main__":
    unittest.main()
