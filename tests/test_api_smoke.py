import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_PROVIDER", "ollama")

from api.app import create_app  # noqa: E402


def main() -> None:
    client = create_app().test_client()
    health = client.get("/health")
    assert health.status_code == 200, health.get_data(as_text=True)
    invalid = client.post("/v1/chat", json={})
    assert invalid.status_code == 400, invalid.get_data(as_text=True)
    print("API smoke tests passed")


if __name__ == "__main__":
    main()
