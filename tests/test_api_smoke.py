import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_PROVIDER", "ollama")

from api.app import _format_agent_answer, create_app  # noqa: E402


def main() -> None:
    client = create_app().test_client()
    health = client.get("/health")
    assert health.status_code == 200, health.get_data(as_text=True)
    readiness = client.get("/v1/integrations/shopify/readiness")
    assert readiness.status_code == 200, readiness.get_data(as_text=True)
    assert readiness.json["state"] in {"configuration_required", "ready_to_authorize"}
    invalid = client.post("/v1/chat", json={})
    assert invalid.status_code == 400, invalid.get_data(as_text=True)
    answer = _format_agent_answer({
        "diagnosis": {"findings": [{"evidence": ["近 6 个月销售额环比下降 12%"]}]},
        "action_drafts": [{"title": "挽回流失风险客户", "actions": ["先选择 200 名客户", "设置对照组"]}],
    })
    assert "query_" not in answer and "##" not in answer
    assert "挽回流失风险客户" in answer
    print("API smoke tests passed")


if __name__ == "__main__":
    main()
