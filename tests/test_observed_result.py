import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.task_store import create_task, prepare_manual_execution, record_observed_result


def test_observed_result_is_owner_scoped_and_aggregate_only() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "tasks.json"
        task = create_task(
            {"title": "Pilot", "audience": "Anonymous consented cohort"},
            source_diagnosis={"source": "consented_reactivation_aggregate"},
            path=path,
            owner="merchant-a",
        )
        prepare_manual_execution(
            task["task_id"], channel="email", budget=200, market="US", locale="en-US",
            attribution_window_days=14, path=path, owner="merchant-a",
        )
        assert record_observed_result(
            task["task_id"], treatment_users=100, treatment_orders=20,
            treatment_revenue=2000, control_users=100, control_orders=10,
            control_revenue=1000, cost=200, currency="USD",
            revenue_net_of_refunds=True, path=path, owner="merchant-b",
        ) is None
        completed = record_observed_result(
            task["task_id"], treatment_users=100, treatment_orders=20,
            treatment_revenue=2000, control_users=100, control_orders=10,
            control_revenue=1000, cost=200, currency="USD",
            revenue_net_of_refunds=True, path=path, owner="merchant-a",
        )
        result = completed["result"]
        assert completed["status"] == "completed"
        assert result["conversion_uplift_pp"] == 10
        assert result["incremental_revenue"] == 1000
        assert result["roi"] == 4
        assert result["source"] == "merchant_reported_aggregate"
        assert not {"email", "phone", "customer_id", "recipients"} & set(result)
        try:
            record_observed_result(
                task["task_id"], treatment_users=100, treatment_orders=20,
                treatment_revenue=2000, control_users=100, control_orders=10,
                control_revenue=1000, cost=200, currency="USD",
                revenue_net_of_refunds=True, path=path, owner="merchant-a",
            )
            raise AssertionError("completed result must not be overwritten")
        except ValueError:
            pass


if __name__ == "__main__":
    test_observed_result_is_owner_scoped_and_aggregate_only()
    print("Observed result attribution tests passed")
