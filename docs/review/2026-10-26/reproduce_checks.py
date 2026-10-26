"""Bounded review probes. Does not retrain or overwrite the project's artifacts.

Run from the project root with venv/Scripts/python.exe and this file's path.
The JSON beside this script records observations, including reproduced defects.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import importlib.metadata
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd

from ml_pipeline.backtest import run_backtest


def load_json(name: str) -> dict:
    return json.loads((ROOT / "saved_models" / f"{name}.json").read_text(encoding="utf-8"))


def synthetic_panel(returns: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.bdate_range("2026-01-05", periods=len(returns)),
        "stock_code": ["000001"] * len(returns),
        "ret_5d_fwd": returns,
        "score_lgb": np.ones(len(returns)),
        "pct_chg": np.zeros(len(returns)),
    })


async def request_json(app, path: str, query: str = "") -> tuple[int, object]:
    sent = []
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": query.encode(),
        "root_path": "", "headers": [], "server": ("127.0.0.1", 8008),
        "client": ("127.0.0.1", 12345),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=30)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(body)


def main() -> None:
    results: dict = {"review_date": "2026-10-26", "root": str(ROOT)}
    packages = ["lightgbm", "shap", "pandas", "numpy", "scikit-learn", "optuna", "fastapi"]
    results["versions"] = {p: importlib.metadata.version(p) for p in packages}

    tracked = subprocess.check_output(["git", "ls-files", "--", "*.py"], cwd=ROOT, text=True).splitlines()
    syntax_errors = []
    for name in tracked:
        try:
            ast.parse((ROOT / name).read_text(encoding="utf-8-sig"), filename=name)
        except SyntaxError as exc:
            syntax_errors.append(str(exc))
    results["syntax"] = {"files": len(tracked), "errors": syntax_errors}

    # A first-period 50% loss must be included in maximum drawdown.
    mdd = run_backtest(synthetic_panel([-0.5] * 5 + [0.0] * 5), k=1)
    results["initial_drawdown"] = {
        "reported": mdd["strategy"]["max_drawdown"],
        "correct_including_initial_capital": round(min(mdd["strategy"]["nav"]) - 1, 6),
        "nav": mdd["strategy"]["nav"],
    }

    # Flat intraperiod prices with a 100 -> 200 gap between adjacent periods.
    prices = pd.DataFrame({"open": [100.0] * 6 + [200.0] * 10,
                           "close": [100.0] * 6 + [200.0] * 10})
    labels = prices["close"].shift(-5) / prices["open"].shift(-1) - 1
    gap = run_backtest(synthetic_panel(labels.iloc[:10].tolist()), k=1)
    results["holding_gap"] = {
        "reported_total_return": gap["strategy"]["total_return"],
        "continuous_holding_gross_return": prices.loc[10, "close"] / prices.loc[1, "open"] - 1,
        "actions": [p["holdings"][0]["action"] for p in gap["rebalance_ledger"]],
        "period_costs": [p["cost"] for p in gap["rebalance_ledger"]],
    }

    from backend.app.services.data_engineering_service import DataEngineeringService

    # Use fresh instances and a temporary config so no production state changes.
    deadlocks = {}
    with tempfile.TemporaryDirectory(prefix="alpha_review_") as temp:
        for method in ["save_schedule_config", "clear_logs"]:
            service = DataEngineeringService()
            service.schedule_config_file = str(Path(temp) / "schedule.json")
            target = (lambda s=service: s.save_schedule_config({"enabled": False})) if method == "save_schedule_config" else service.clear_logs
            worker = threading.Thread(target=target, daemon=True)
            worker.start()
            worker.join(timeout=0.4)
            deadlocks[method] = {"still_running": worker.is_alive(), "lock_held": service.lock.locked()}
    results["service_deadlocks"] = deadlocks

    from ml_pipeline.risk_guard import RiskKillSwitch

    guard = RiskKillSwitch()
    risky = [{"stock_code": "000001", "industry": "same_sector", "recommend_rating": "A"},
             {"stock_code": "600036", "industry": "same_sector", "recommend_rating": "A"}]
    results["risk_filter"] = {
        "actual_single_stock_weight": 0.5, "actual_sector_weight": 1.0,
        "returned_statuses": [x["risk_status"] for x in guard.filter_recommendations(risky)],
        "reported_gauges": guard.status_report["gauges"],
    }

    from backend.app.services.recommend_service import RecommendationService

    # A two-date cache must not combine historical and current scores.
    service = RecommendationService.__new__(RecommendationService)
    service.data_df = pd.DataFrame({
        "\u4ee3\u7801": ["000001", "600519"],
        "\u66f4\u65b0\u65e5\u671f": ["2026-10-20", "2026-10-21"],
        "\u8dd1\u8d62\u5019\u9009\u6c60\u5747\u503c\u6982\u7387": [0.9, 0.1],
    })
    service.reload = lambda: None
    service._get_market_indicator_cache = lambda: {}
    current = service.get_topk()
    invalid = service.get_topk(date="1900-01-01")
    results["recommendation_dates"] = {
        "latest_candidates": current["total_candidates"],
        "latest_codes": [x["stock_code"] for x in current["recommendations"]],
        "latest_returned_date": current["date"],
        "invalid_requested_date": "1900-01-01", "invalid_returned_date": invalid["date"],
        "invalid_returned_candidates": invalid["total_candidates"],
    }

    bundle = joblib.load(ROOT / "saved_models" / "lgbm_market_classifier.pkl")
    explainer = joblib.load(ROOT / "saved_models" / "shap_explainer.pkl")
    model = bundle["model"]
    features = bundle["feature_cols"]
    from ml_pipeline.train_explainer import verify_additivity

    results["shap_additivity"] = verify_additivity(model, explainer, bundle["test"][features].head(200))
    report = load_json("training_report")
    wf = load_json("walk_forward")
    bt = load_json("backtest_result")
    results["artifact_consistency"] = {
        "training_report_has_loss": bool(report.get("loss_history")),
        "bundle_has_loss": bool(bundle.get("loss_history")),
        "train_dates_saved": bundle["train"]["date"].nunique(),
        "train_dates_expected_with_current_purge": int(report["panel"]["dates"] * 0.7) - 5,
        "first_walk_forward_train_end": wf["windows"][0]["train_end"],
        "first_walk_forward_validation_start": wf["windows"][0]["val_start"],
        "aggregated_periods": wf["backtest_aggregated"]["strategy"]["periods"],
        "aggregated_has_execution_params": "params" in wf["backtest_aggregated"],
        "aggregate_dates": len(wf["backtest_aggregated"].get("dates", [])),
        "report_backtest_periods": report["backtest"]["strategy"]["periods"],
        "standalone_backtest_periods": bt["strategy"]["periods"],
        "point_in_time_history_exists": (ROOT / "data/csi300_membership_history.csv").exists(),
        "subsample_freq": model.get_params()["subsample_freq"],
    }
    lifecycle = DataEngineeringService().get_system_status()["model_lifecycle"]["market_model"]
    results["lifecycle_metadata"] = {
        "displayed_auc": lifecycle["metrics"]["auc"],
        "actual_test_auc": bundle["metrics"]["test"]["auc"],
        "displayed_n_estimators": lifecycle["best_params"]["n_estimators"],
        "actual_n_estimators": model.n_estimators_,
    }

    # Same seed and trees: changing subsample has no effect when frequency is 0.
    import lightgbm as lgb

    sample_rng = np.random.default_rng(42)
    sample_x = sample_rng.normal(size=(1000, 4))
    sample_y = (sample_x[:, 0] + sample_rng.normal(size=1000) > 0).astype(int)
    common = {"n_estimators": 20, "random_state": 42, "verbose": -1, "n_jobs": 2}
    a = lgb.LGBMClassifier(**common, subsample=0.6).fit(sample_x, sample_y)
    b = lgb.LGBMClassifier(**common, subsample=1.0).fit(sample_x, sample_y)
    results["inactive_subsample"] = {
        "max_prediction_difference": float(np.max(np.abs(a.predict_proba(sample_x) - b.predict_proba(sample_x)))),
        "subsample_freq": a.get_params()["subsample_freq"],
    }

    from ml_pipeline.stress_test import CRISIS_SCENARIOS, HYPOTHETICAL_SHOCKS

    train_end = pd.Timestamp(bundle["train"]["date"].max())
    results["stress_test"] = {
        "model_train_end": str(train_end.date()),
        "crises_entirely_before_train_end": [s["id"] for s in CRISIS_SCENARIOS if pd.Timestamp(s["end_date"]) <= train_end],
        "constant_impacts": [s["estimated_impact"] for s in HYPOTHETICAL_SHOCKS],
        "constant_statuses": [s["pass_status"] for s in HYPOTHETICAL_SHOCKS],
        "saved_beta": load_json("attribution")["regression"]["beta"],
    }

    # Reproduce the optional-argument failure, using only temporary destinations.
    import models.model_trainer as trainer

    rng = np.random.default_rng(0)
    training_panel = pd.DataFrame(rng.normal(size=(600, len(features))), columns=features)
    training_panel["date"] = np.repeat(pd.bdate_range("2020-01-01", periods=60), 10)
    training_panel["target_up"] = np.tile([0, 1], 300)
    training_panel["stock_code"] = np.tile([f"{i:06}" for i in range(10)], 60)
    with tempfile.TemporaryDirectory(prefix="alpha_review_train_") as temp:
        params = {**trainer.DEFAULT_PARAMS, "n_estimators": 5, "n_jobs": 2}
        with patch.object(trainer, "SAVED_MODELS_DIR", temp), patch.object(trainer, "DEFAULT_PARAMS", params), contextlib.redirect_stdout(io.StringIO()):
            try:
                trainer.train_market_model(panel=training_panel, n_trials=1, force_retrain=True)
                results["optional_candidate_factors"] = {"exception": None}
            except Exception as exc:
                results["optional_candidate_factors"] = {"exception": type(exc).__name__, "message": str(exc)}

    from backend.app.main import app

    async def smoke():
        out = {}
        for path in ["/api/health", "/api/v1/recommend/topk", "/api/v1/explain/global",
                     "/api/v1/evaluation/metrics", "/api/v1/evaluation/backtest",
                     "/api/v1/engineering/status"]:
            try:
                code, body = await request_json(app, path)
                out[path] = {"status": code, "size": len(json.dumps(body))}
                if path.endswith("/topk"):
                    out[path]["recommendations"] = len(body["recommendations"])
                    stock = body["recommendations"][0]["stock_code"]
                    local_code, local = await request_json(app, f"/api/v1/explain/local/{stock}")
                    out["local_explanation"] = {"status": local_code, "space": local.get("output_space"),
                                                "rounded_additivity_error": abs(local.get("base_value", 0) + sum(x["shap_value"] for x in local.get("features", [])) - local.get("predicted_margin", 0))}
            except Exception as exc:
                out[path] = {"exception": type(exc).__name__, "message": str(exc)}
        return out

    results["api_smoke"] = asyncio.run(smoke())
    target = Path(__file__).with_name("checks.json")
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=True, indent=2, default=str))


if __name__ == "__main__":
    main()
