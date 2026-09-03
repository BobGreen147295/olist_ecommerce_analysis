import os
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        previous_url = os.environ.get("DATABASE_URL")
        previous_key = os.environ.get("CONNECTION_TOKEN_ENCRYPTION_KEY")
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(directory) / 'connections.db'}"
        os.environ["CONNECTION_TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        try:
            from src.agent.merchant_connection_store import (
                consume_authorization_state,
                issue_authorization_state,
                list_connection_summaries,
                save_shopify_connection,
            )

            state = issue_authorization_state("merchant-a", "demo-shop.myshopify.com")
            context = consume_authorization_state(state)
            assert context["shop_domain"] == "demo-shop.myshopify.com"
            try:
                consume_authorization_state(state)
                raise AssertionError("state must be single-use")
            except ValueError:
                pass

            save_shopify_connection(context["workspace_id"], context["shop_domain"], "shpat_test_secret", ["read_orders"])
            assert list_connection_summaries("merchant-b") == []
            summary = list_connection_summaries("merchant-a")
            assert summary[0]["shop_domain"] == "demo-shop.myshopify.com"
            assert "shpat_test_secret" not in repr(summary)
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
            if previous_key is None:
                os.environ.pop("CONNECTION_TOKEN_ENCRYPTION_KEY", None)
            else:
                os.environ["CONNECTION_TOKEN_ENCRYPTION_KEY"] = previous_key
    print("Merchant connection security tests passed")


if __name__ == "__main__":
    main()
