import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from src.agent.commerce_store import get_connected_data_health, import_order_csv

    with tempfile.TemporaryDirectory() as directory:
        previous_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(directory) / 'commerce.db'}"
        try:
            mapping = {"order_id": "id", "ordered_at": "ordered", "total_amount": "amount"}
            defaults = {"currency": "USD", "market": "US", "timezone": "UTC"}
            import_order_csv(b"id,ordered,amount\na-1,2026-09-01T00:00:00Z,10\n", "Merchant A", mapping, "merchant-a", defaults)
            import_order_csv(b"id,ordered,amount\nb-1,2026-09-02T00:00:00Z,20\n", "Merchant B", mapping, "merchant-b", defaults)
            assert get_connected_data_health("merchant-a")["source"]["display_name"] == "Merchant A"
            assert get_connected_data_health("merchant-b")["source"]["display_name"] == "Merchant B"
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
    print("Commerce data tenancy tests passed")


if __name__ == "__main__":
    main()
