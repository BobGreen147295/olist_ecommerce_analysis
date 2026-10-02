"""Offline product acceptance baseline using synthetic aggregates and SQLite.

Exit 0: all automated acceptance checks pass; 1: product gaps; 2: harness error.
This does not call an LLM or verify human usability/commercial effectiveness.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = dict(treatment_users=100, treatment_orders=20, treatment_revenue=2000,
            control_users=100, control_orders=10, control_revenue=1000, cost=200)


def sql_metrics(inputs: dict) -> dict:
    """Independent SQL reference; no calls to the production calculator."""
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("""
            WITH input(tu, tor, tr, cu, cor, cr, cost) AS (VALUES (?, ?, ?, ?, ?, ?, ?)),
            reference AS (
                SELECT *, tor * 1.0 / tu AS tc, cor * 1.0 / cu AS cc,
                    tor - tu * cor * 1.0 / cu AS extra_orders,
                    COALESCE(cr * 1.0 / NULLIF(cor, 0), 0) AS baseline_aov
                FROM input
            )
            SELECT tc AS treatment_conversion, cc AS control_conversion,
                100 * (tc - cc) AS conversion_uplift_pp,
                (tc - cc) / NULLIF(cc, 0) AS relative_lift,
                extra_orders AS incremental_orders,
                extra_orders * baseline_aov AS incremental_revenue,
                (extra_orders * baseline_aov - cost) / NULLIF(cost, 0) AS roi
            FROM reference
        """, tuple(inputs[key] for key in BASE)).fetchone()
        return dict(row)


def equal_metrics(actual: dict, expected: dict) -> None:
    precision = {"conversion_uplift_pp": 4, "incremental_orders": 2,
                 "incremental_revenue": 2, "recent_net_sales": 2,
                 "previous_net_sales": 2, "gross_sales": 2, "refunds": 2}
    for key, value in expected.items():
        received = actual.get(key)
        if value is None:
            if key not in actual or received is not None:
                raise AssertionError(f"{key}: expected null, got {received!r}")
        elif not isinstance(received, (int, float)) or not math.isfinite(received):
            raise AssertionError(f"{key}: expected finite {value}, got {received!r}")
        elif not math.isclose(received, round(value, precision.get(key, 6)), rel_tol=0, abs_tol=1e-8):
            raise AssertionError(f"{key}: expected {value}, got {received}")


def synthetic_summary() -> dict:
    days = []
    for i in range(14):
        net = 100 if i < 7 else 60
        days.append(dict(date=(date(2026, 9, 1) + timedelta(days=i)).isoformat(),
                         orders=2, gross_sales=120, net_sales=net, refunds=120-net))
    return {"is_development_store": False, "order_trend": {
        "window_days": 30, "orders_scanned": 28, "truncated": False, "days": days,
        "totals": {"orders": 28, "gross_sales": 1680, "net_sales": 1120, "refunds": 560}}}


def sql_signal_evidence(summary: dict) -> dict:
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE daily(day TEXT PRIMARY KEY, net REAL, gross REAL, adjustments REAL)")
        db.executemany("INSERT INTO daily VALUES (?, ?, ?, ?)", [
            (d["date"], d["net_sales"], d["gross_sales"], d["refunds"])
            for d in summary["order_trend"]["days"]])
        recent, previous, gross, adjustments = db.execute("""
            SELECT SUM(CASE WHEN day >= '2026-09-08' THEN net ELSE 0 END),
                   SUM(CASE WHEN day < '2026-09-08' THEN net ELSE 0 END),
                   SUM(gross), SUM(adjustments) FROM daily
        """).fetchone()
    return {"net_sales_decline": {"recent_net_sales": recent, "previous_net_sales": previous},
            "refund_pressure": {"gross_sales": gross, "refunds": adjustments}}


def check_signal_evidence(signals: list, expected: dict) -> None:
    ids = [signal["id"] for signal in signals]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise AssertionError(f"Expected exactly {sorted(expected)}, got {ids}")
    for signal in signals:
        equal_metrics(signal.get("evidence", {}), expected[signal["id"]])


def run_evaluation() -> list[dict]:
    # Import only deterministic paths. No account, stored data, or model is loaded.
    from api.app import app, _shopify_opportunity_readiness, _shopify_store_opportunities
    from src.agent.evaluation import evaluate_experiment
    from src.agent.observability import evaluate_response_quality

    rows = []

    def check(name, dimension, evidence, action):
        try:
            action()
            status, detail = "pass", "Acceptance condition satisfied"
        except AssertionError as exc:
            status, detail = "fail", str(exc)
        except Exception as exc:
            # Unexpected exceptions are not evidence of a safe refusal.
            status, detail = "error", type(exc).__name__
        rows.append(dict(id=name, dimension=dimension, status=status,
                         evidence=evidence, detail=detail))

    for name, changes in [
        ("positive_lift", {}), ("unequal_groups", {"treatment_users": 200}),
        ("negative_lift", {"treatment_orders": 5}), ("zero_cost", {"cost": 0}),
        ("zero_control_orders", {"control_orders": 0, "control_revenue": 0}),
        ("fractional_currency", {"control_revenue": 123.45, "cost": 19.99}),
        ("treatment_revenue_change", {"treatment_revenue": 9900}),
    ]:
        inputs = {**BASE, **changes}
        check(name, "metric_accuracy", "evaluation.evaluate_experiment vs independent SQLite estimator",
              lambda inputs=inputs: equal_metrics(evaluate_experiment(**inputs), sql_metrics(inputs)))

    def rejected(changes):
        try:
            evaluate_experiment(**{**BASE, **changes})
        except ValueError:
            return
        raise AssertionError("Invalid input was accepted instead of a clear ValueError")

    for name, changes in [("missing_control", {"control_users": 0}),
                          ("negative_cost", {"cost": -1}),
                          ("nonfinite_revenue", {"control_revenue": float("nan")}),
                          ("fractional_users", {"treatment_users": 100.5})]:
        check(name, "insufficient_data", "evaluation.evaluate_experiment input boundary",
              lambda changes=changes: rejected(changes))

    summary = synthetic_summary()
    expected = sql_signal_evidence(summary)
    check("signal_numeric_evidence", "traceability", "14 synthetic daily aggregates / SQL period sums",
          lambda: check_signal_evidence(_shopify_store_opportunities(summary), expected))

    def draft_traceability():
        with tempfile.TemporaryDirectory() as directory, \
             patch("src.agent.task_store.TASKS_PATH", Path(directory) / "tasks.json"), \
             patch("src.agent.task_store._use_database", return_value=False), \
             patch("api.app._require_session", return_value={"username": "synthetic-eval"}), \
             patch("src.agent.merchant_connection_store.get_shopify_connection_status", return_value={"summary": summary}):
            for signal_id, values in expected.items():
                response = app.test_client().post("/v1/tasks/from-shopify-signal", json={"signal_id": signal_id})
                assert response.status_code == 201, f"Synthetic draft request returned {response.status_code}"
                source = response.get_json()["task"].get("source_diagnosis", {})
                assert source.get("signal_id") == signal_id, "Draft lost its source signal reference"
                assert source.get("evidence"), f"{signal_id}: source reference exists but numeric evidence snapshot is missing"
                equal_metrics(source["evidence"], values)

    check("draft_evidence_link", "traceability", "POST /v1/tasks/from-shopify-signal with synthetic input and temporary storage",
          draft_traceability)

    def false_evidence_score():
        output = {"diagnosis": {"findings": [{"title": "Synthetic false claim",
                  "evidence": ["Revenue = 999999"], "source": "nonexistent_tool"}]},
                  "tool_results": []}
        score = evaluate_response_quality(output)
        if score["evidence_coverage"] > 0 or score["source_citation_rate"] > 0:
            raise AssertionError("Fabricated, unresolvable evidence is credited by the structural scorer")

    check("fabricated_citation_not_credited", "traceability",
          "observability.evaluate_response_quality adversarial synthetic output", false_evidence_score)

    def blocked(payload):
        state = _shopify_opportunity_readiness(payload)["state"]
        signals = _shopify_store_opportunities(payload)
        if state == "ready" or signals:
            raise AssertionError(f"Unsafe input accepted: state={state}, signals={len(signals)}")

    cases = {"no_trend": {}, "development_store": {**summary, "is_development_store": True}}
    for name, change in [("small_sample", {"orders_scanned": 19}),
                         ("short_history", {"days": summary["order_trend"]["days"][:2]}),
                         ("truncated_history", {"truncated": True}),
                         ("missing_dates", {"days": [{}, {}, {}]})]:
        cases[name] = {**summary, "order_trend": {**summary["order_trend"], **change}}
    missing_net = deepcopy(summary)
    for day in missing_net["order_trend"]["days"][7:]:
        del day["net_sales"]
    cases["missing_net_sales"] = missing_net
    for name, payload in cases.items():
        check(name, "insufficient_data", "api readiness and signal generation",
              lambda payload=payload: blocked(payload))

    def small_experiment():
        output = evaluate_experiment(**{**BASE, "treatment_users": 2, "treatment_orders": 1,
                                     "control_users": 2, "control_orders": 1})
        if not (output.get("warnings") or output.get("limitations")):
            raise AssertionError("Two users per group produce results without a sample-size limitation")

    check("small_experiment_warning", "insufficient_data", "experiment sample-size limitation",
          small_experiment)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optional synthetic-only JSON report path")
    args = parser.parse_args()
    try:
        with patch.object(socket.socket, "connect", side_effect=RuntimeError("Offline evaluation")), \
             patch.object(socket, "create_connection", side_effect=RuntimeError("Offline evaluation")):
            rows = run_evaluation()
    except Exception as exc:
        print(f"Evaluation unavailable: {type(exc).__name__}", file=sys.stderr)
        return 2
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    sources = ["scripts/evaluate_product.py", "api/app.py", "src/agent/evaluation.py",
               "src/agent/observability.py", "src/agent/task_store.py",
               "src/agent/agent_graph.py", "web/src/app/learning/page.tsx"]
    report = {"version": "revenueops-acceptance-v1", "data": "synthetic_aggregate_only",
              "git_revision": revision.stdout.strip(), "python": sys.version.split()[0],
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
              "cases": rows, "counts": {s: sum(r["status"] == s for r in rows)
                                          for s in ("pass", "fail", "error")},
              "pending": ["live_model_grounding", "operator_usability", "paired_workflow_comparison"]}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for row in rows:
        print(f"{row['status'].upper():5} {row['id']}: {row['detail']}")
    print(json.dumps(report["counts"]))
    return 2 if report["counts"]["error"] else int(report["counts"]["fail"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
