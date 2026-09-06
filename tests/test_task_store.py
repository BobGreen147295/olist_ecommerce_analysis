import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from src.agent.task_store import create_task, launch_simulated_campaign, update_task

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "tasks.json"
        task = create_task(
            {
                "title": "Simulation only",
                "channel": "email",
                "budget": 25,
                "duration_days": 7,
            },
            path=path,
            owner="merchant-a",
        )
        update_task(task["task_id"], {"status": "confirmed"}, path=path, owner="merchant-a")
        launched = launch_simulated_campaign(
            task["task_id"],
            audience_size=10,
            market="US",
            path=path,
            owner="merchant-a",
        )
        execution = launched["execution"]
        assert execution["campaign_id"].startswith("sim_")
        assert execution["mode"] == "simulation"
        assert execution["audience_size"] == 10
        assert not {"recipients", "customer_ids", "email", "phone"} & set(execution)
        assert "recipient" not in path.read_text(encoding="utf-8").lower()
    print("Simulated campaign safety tests passed")


if __name__ == "__main__":
    main()
