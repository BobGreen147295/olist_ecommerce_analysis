import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from src.agent.commerce_store import get_connected_data_health, import_order_csv

    with tempfile.TemporaryDirectory() as directory:
        previous_url = os.environ.get("DATABASE_URL")
        previous_hash_key = os.environ.get("CUSTOMER_ID_HASH_KEY")
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(directory) / 'commerce.db'}"
        os.environ["CUSTOMER_ID_HASH_KEY"] = "test-customer-id-hash-key-at-least-32-chars"
        try:
            mapping = {"order_id": "id", "ordered_at": "ordered", "total_amount": "amount", "customer_id": "customer"}
            defaults = {"currency": "USD", "market": "US", "timezone": "UTC"}
            import_order_csv(b"id,ordered,amount,customer\na-1,2026-09-01T00:00:00Z,10,shared-customer\n", "Merchant A", mapping, "merchant-a", defaults)
            import_order_csv(b"id,ordered,amount,customer\nb-1,2026-09-02T00:00:00Z,20,shared-customer\n", "Merchant B", mapping, "merchant-b", defaults)
            assert get_connected_data_health("merchant-a")["source"]["display_name"] == "Merchant A"
            assert get_connected_data_health("merchant-b")["source"]["display_name"] == "Merchant B"
            connection = sqlite3.connect(Path(directory) / "commerce.db")
            try:
                customer_ids = [row[0] for row in connection.execute("SELECT customer_id FROM commerce_orders ORDER BY order_id")]
            finally:
                connection.close()
            assert customer_ids[0] != "shared-customer"
            assert customer_ids[1] != "shared-customer"
            assert customer_ids[0] != customer_ids[1]
            try:
                import_order_csv(
                    b"id,ordered,amount,customer_email\nc-1,2026-09-03T00:00:00Z,30,person@example.com\n",
                    "Unsafe", {**mapping, "customer_id": "customer_email"}, "merchant-a", defaults,
                )
                raise AssertionError("email column must not be accepted as a customer identifier")
            except ValueError as exc:
                assert "匿名稳定 ID" in str(exc)
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
            if previous_hash_key is None:
                os.environ.pop("CUSTOMER_ID_HASH_KEY", None)
            else:
                os.environ["CUSTOMER_ID_HASH_KEY"] = previous_hash_key
    print("Commerce data tenancy tests passed")


if __name__ == "__main__":
    main()
