import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(directory) / 'pilot.db'}"
        from api.app import create_app

        client = create_app().test_client()
        valid = client.post("/v1/pilot-applications", json={
            "contact_email": "merchant@example.com",
            "shop_domain": "pilot-store.myshopify.com",
            "monthly_orders": "50-199",
            "challenge": "repeat_purchase",
            "terms_accepted": True,
        })
        assert valid.status_code == 201, valid.get_data(as_text=True)
        assert client.get("/v1/pilot-applications").status_code == 401
        invalid = client.post("/v1/pilot-applications", json={
            "contact_email": "not-an-email",
            "shop_domain": "example.com",
            "monthly_orders": "50-199",
            "challenge": "repeat_purchase",
            "terms_accepted": True,
        })
        assert invalid.status_code == 400, invalid.get_data(as_text=True)
        from src.agent.pilot_application_store import list_pilot_applications
        applications = list_pilot_applications()
        assert len(applications) == 1
        assert applications[0]["shop_domain"] == "pilot-store.myshopify.com"

        from unittest.mock import patch
        from src.agent.auth_session_store import issue_session

        with patch.dict(os.environ, {"SESSION_SIGNING_KEY": "synthetic-pilot-test-signing-key-at-least-32-characters"}):
            merchant_token = issue_session("synthetic-merchant", "merchant")
            denied = client.get("/v1/pilot-applications", headers={"Authorization": f"Bearer {merchant_token}"})
            assert denied.status_code == 403
            assert "applications" not in denied.get_json()
            assert "merchant@example.com" not in denied.get_data(as_text=True)

            admin_token = issue_session("synthetic-admin", "admin")
            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            allowed = client.get("/v1/pilot-applications", headers=admin_headers)
            assert allowed.status_code == 200
            assert len(allowed.get_json()["applications"]) == 1
            assert allowed.get_json()["applications"][0]["application_id"] == valid.get_json()["application_id"]

            assert client.post("/v1/auth/logout", headers=admin_headers).status_code == 204
            revoked = client.get("/v1/pilot-applications", headers=admin_headers)
            assert revoked.status_code == 401
            assert "applications" not in revoked.get_json()
    print("Pilot application tests passed")


if __name__ == "__main__":
    main()
