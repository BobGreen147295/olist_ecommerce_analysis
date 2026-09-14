import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.task_store import create_task, get_manual_execution_package, prepare_manual_execution


def test_manual_execution_package_excludes_customer_data() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "tasks.json"
        task = create_task(
            {
                "title": "Consented reactivation pilot",
                "audience": "12 位已同意营销的匿名客户（不生成名单）",
                "actions": ["人工确认优惠", "保留对照组"],
                "expected_metric": "增量净收入",
                "consent_basis": "仅限已授予营销同意的匿名客户",
            },
            source_diagnosis={"source": "consented_reactivation_aggregate"},
            path=path,
            owner="merchant-a",
        )
        confirmed = prepare_manual_execution(
            task["task_id"], channel="email", budget=25, market="US", locale="en-US",
            attribution_window_days=14, path=path, owner="merchant-a",
        )
        package = get_manual_execution_package(task["task_id"], path=path, owner="merchant-a")

        assert confirmed and confirmed["status"] == "confirmed"
        assert package and package["customer_contact_data"] == "not_included"
        assert not {"email", "phone", "address", "customer_ids", "recipients"} & set(package)
        assert get_manual_execution_package(task["task_id"], path=path, owner="merchant-b") is None


if __name__ == "__main__":
    test_manual_execution_package_excludes_customer_data()
    print("Manual execution package safety tests passed")
