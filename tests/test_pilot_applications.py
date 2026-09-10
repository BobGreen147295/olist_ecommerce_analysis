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
    print("Pilot application tests passed")


if __name__ == "__main__":
    main()
