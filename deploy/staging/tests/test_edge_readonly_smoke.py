from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/jeeb-staging-edge-readonly-smoke.yml"


class EdgeReadOnlySmokeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_uses_exact_staging_credentials_and_public_routes(self) -> None:
        for marker in (
            "environment: staging",
            "secrets.JEEB_STAGING_JEEB_INFRASTRUCTURE_CLOUDFLARE_API_TOKEN",
            "vars.JEEB_STAGING_JEEB_INFRASTRUCTURE_CLOUDFLARE_TOKEN_ID_SHA256",
            "secrets.JEEB_STAGING_WSS_PROBE_MINT_KEY",
            "scripts/verify_cloudflare_org_auth.py",
            "scripts/verify-authorized-wss.mjs",
            "https://app.jeeb.fds-1.com/__tunnel_health",
            "https://app.jeeb.fds-1.com/health/ready",
            "https://cms.jeeb.fds-1.com/healthz",
        ):
            self.assertIn(marker, self.workflow)

    def test_has_no_provider_or_origin_mutation_surface(self) -> None:
        for forbidden in (
            "wrangler",
            "cloudflared",
            "ssh ",
            "scp ",
            "versions deploy",
            "secret put",
            "tunnel route dns",
            "dns_records",
            "workers/routes",
        ):
            self.assertNotIn(forbidden, self.workflow.lower())

    def test_separates_provider_auth_application_auth_and_access_transport(self) -> None:
        self.assertIn(
            "Cloudflare API token: provider identity and Worker/domain metadata only",
            self.workflow,
        )
        self.assertIn(
            "WSS probe key: short-lived application credentials only",
            self.workflow,
        )
        self.assertIn("Cloudflare Access SSH: not used", self.workflow)


if __name__ == "__main__":
    unittest.main()
