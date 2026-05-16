from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
import requests
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.api.utils import fail, ok
from apps.core.models import QAR, QAR_Overview, QAR_Parameter_Attribute


METRIC_QUERY = "查询响应时间"
METRIC_VISUAL = "可视化响应时间"
METRIC_UPLOAD = "上传速度"
METRIC_UPLOAD_PROBE_500M = "500M文件上传"

METRIC_QUERY_LEGACY = "技术指标1-数据查询响应时间"
METRIC_VISUAL_LEGACY = "技术指标2-数据可视化响应时间"
METRIC_UPLOAD_LEGACY = "技术指标3-数据上传速度"
METRIC_UPLOAD_PROBE_500M_LEGACY = "技术指标11-500M数据导入链路探测"


def _metric_aliases(metric_name: str) -> tuple[str, ...]:
    aliases = {
        METRIC_QUERY: (METRIC_QUERY, METRIC_QUERY_LEGACY),
        METRIC_VISUAL: (METRIC_VISUAL, METRIC_VISUAL_LEGACY),
        METRIC_UPLOAD: (METRIC_UPLOAD, METRIC_UPLOAD_LEGACY),
        METRIC_UPLOAD_PROBE_500M: (METRIC_UPLOAD_PROBE_500M, METRIC_UPLOAD_PROBE_500M_LEGACY),
    }
    return aliases.get(metric_name, (metric_name,))


def _find_metric_item(items: list[dict[str, Any]], metric_name: str) -> dict[str, Any]:
    lookup = set(_metric_aliases(metric_name))
    for item in items:
        if item.get("metric") in lookup:
            return item
    return {}

SYSTEM_TEST_JOBS: dict[str, dict[str, Any]] = {}
SYSTEM_TEST_LOCK = threading.Lock()
MAX_SYSTEM_TEST_JOBS = 30

BACKUP_RESTORE_JOBS: dict[str, dict[str, Any]] = {}
BACKUP_RESTORE_LOCK = threading.Lock()
MAX_BACKUP_RESTORE_JOBS = 50

SYSTEM_TABLE_PREFIXES = ("django_", "auth_")
SYSTEM_TABLE_EXACT = {"sqlite_sequence"}
BACKUP_TABLE_NAME = "QAR_Parameter_Attribute"
BACKUP_FILE_PREFIX = "qar_parameter_attribute"
BACKUP_FILE_SUFFIX = ".json.gz"
BACKUP_RECORD_FIELDS = [
    "parameter_name",
    "description",
    "unit",
    "min_value",
    "max_value",
    "mean",
    "variance",
    "normalized_variance",
    "warning_lower",
    "warning_upper",
    "critical_lower",
    "critical_upper",
    "is_monitored",
    "updated_time",
]


def _project_root() -> Path:
    return Path(settings.BASE_DIR)


def _benchmark_root() -> Path:
    return _project_root() / "benchmark_results"


def _backup_root() -> Path:
    root = os.getenv("BACKUP_DIR")
    if root:
        return Path(root)
    return _project_root() / "backups" / "db"


def _ops_log_file() -> Path:
    return _project_root() / "benchmark_results" / "system_ops.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(min_value, min(max_value, value))


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _extract_named_float(text: str, key: str) -> float | None:
    match = re.search(rf"{re.escape(key)}=([0-9]+(?:\.[0-9]+)?)", text or "")
    if not match:
        return None
    return _safe_float(match.group(1))


def _format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(max(size, 0))
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    if idx == 0:
        return f"{int(value)} {units[idx]}"
    return f"{value:.2f} {units[idx]}"


def _is_system_table(table_name: str) -> bool:
    normalized = str(table_name or "").strip().lower()
    if not normalized:
        return True
    if normalized in SYSTEM_TABLE_EXACT:
        return True
    return any(normalized.startswith(prefix) for prefix in SYSTEM_TABLE_PREFIXES)


def _append_ops_log(action: str, status: str, detail: str, extra: dict[str, Any] | None = None) -> None:
    payload = {
        "time": _now_iso(),
        "action": action,
        "status": status,
        "detail": detail,
    }
    if extra:
        payload["extra"] = extra

    log_file = _ops_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_ops_logs(limit: int = 120) -> list[dict[str, Any]]:
    log_file = _ops_log_file()
    if not log_file.exists():
        return []

    rows: list[dict[str, Any]] = []
    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]


def _parse_summary_file(summary_file: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not summary_file.exists():
        return rows

    with summary_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 4)
            if len(parts) < 5:
                continue
            rows.append(
                {
                    "metric": parts[0].strip(),
                    "status": parts[1].strip(),
                    "target": parts[2].strip(),
                    "observed": parts[3].strip(),
                    "detail": parts[4].strip(),
                }
            )
    return rows


def _collect_metric_runs(limit: int = 16) -> list[dict[str, Any]]:
    root = _benchmark_root()
    if not root.exists():
        return []

    runs: list[dict[str, Any]] = []
    for run_dir in root.glob("raw_*"):
        if not run_dir.is_dir():
            continue
        summary_file = run_dir / "summary.tsv"
        items = _parse_summary_file(summary_file)
        if not items:
            continue

        run_id = run_dir.name.replace("raw_", "", 1)
        run_time = run_id
        try:
            run_time = datetime.strptime(run_id, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

        pass_count = sum(1 for item in items if item["status"] == "PASS")
        fail_count = sum(1 for item in items if item["status"] == "FAIL")
        skip_count = sum(1 for item in items if item["status"] == "SKIP")

        runs.append(
            {
                "run_id": run_id,
                "run_time": run_time,
                "items": items,
                "summary": {
                    "pass": pass_count,
                    "fail": fail_count,
                    "skip": skip_count,
                    "total": len(items),
                },
            }
        )

    runs.sort(key=lambda item: item["run_id"], reverse=True)
    return runs[:limit]


def _build_trend_series(runs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    series = {
        "query_p95_s": [],
        "visual_p95_s": [],
        "upload_avg_mb_s": [],
    }

    for run in reversed(runs):
        items = run["items"]
        query = _extract_named_float(_find_metric_item(items, METRIC_QUERY).get("observed", ""), "p95")
        visual = _extract_named_float(_find_metric_item(items, METRIC_VISUAL).get("observed", ""), "p95")
        upload = _extract_named_float(_find_metric_item(items, METRIC_UPLOAD).get("observed", ""), "avg")

        label = run["run_time"]
        if query is not None:
            series["query_p95_s"].append({"label": label, "value": query})
        if visual is not None:
            series["visual_p95_s"].append({"label": label, "value": visual})
        if upload is not None:
            series["upload_avg_mb_s"].append({"label": label, "value": upload})

    return series


def _build_kpis(latest_run: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not latest_run:
        return []

    items = latest_run["items"]

    query_item = _find_metric_item(items, METRIC_QUERY)
    visual_item = _find_metric_item(items, METRIC_VISUAL)
    upload_item = _find_metric_item(items, METRIC_UPLOAD)

    return [
        {
            "key": "query_p95",
            "label": "查询 P95",
            "value": query_item.get("observed") or "-",
            "target": query_item.get("target") or "-",
            "status": query_item.get("status") or "UNKNOWN",
        },
        {
            "key": "visual_p95",
            "label": "可视化 P95",
            "value": visual_item.get("observed") or "-",
            "target": visual_item.get("target") or "-",
            "status": visual_item.get("status") or "UNKNOWN",
        },
        {
            "key": "upload_speed",
            "label": "上传均速",
            "value": upload_item.get("observed") or "-",
            "target": upload_item.get("target") or "-",
            "status": upload_item.get("status") or "UNKNOWN",
        },
        {
            "key": "pass_total",
            "label": "通过项 / 总项",
            "value": f"{latest_run['summary']['pass']} / {latest_run['summary']['total']}",
            "target": "全部通过",
            "status": "PASS" if latest_run["summary"]["fail"] == 0 else "FAIL",
        },
    ]


def _calc_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "avg": 0.0,
            "p95": 0.0,
            "max": 0.0,
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    idx95 = max(0, min(n - 1, int((n * 0.95) - 1 if (n * 0.95).is_integer() else int(n * 0.95))))
    avg = sum(sorted_vals) / n
    return {
        "count": n,
        "min": sorted_vals[0],
        "avg": avg,
        "p95": sorted_vals[idx95],
        "max": sorted_vals[-1],
    }


def _init_system_test_job(config: dict[str, int]) -> dict[str, Any]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_rounds = (
        int(config.get("query_runs", 0))
        + int(config.get("visual_runs", 0))
        + int(config.get("upload_runs", 0))
        + 1
    )
    return {
        "job_id": str(uuid.uuid4()),
        "status": "running",
        "error": "",
        "run_id": run_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "finished_at": None,
        "config": config,
        "progress": {
            "current_metric": "准备中",
            "done_rounds": 0,
            "total_rounds": total_rounds,
        },
        "metrics": {
            "query": {
                "label": METRIC_QUERY,
                "target": "P95 < 3s",
                "runs_total": int(config.get("query_runs", 0)),
                "runs_done": 0,
                "latest": None,
                "stats": _calc_stats([]),
                "non_200": 0,
                "status": "RUNNING",
            },
            "visual": {
                "label": METRIC_VISUAL,
                "target": "P95 < 5s",
                "runs_total": int(config.get("visual_runs", 0)),
                "runs_done": 0,
                "latest": None,
                "stats": _calc_stats([]),
                "non_200": 0,
                "status": "RUNNING",
            },
            "upload": {
                "label": METRIC_UPLOAD,
                "target": "AVG > 50MB/s",
                "runs_total": int(config.get("upload_runs", 0)),
                "runs_done": 0,
                "latest": None,
                "stats": _calc_stats([]),
                "success": 0,
                "status": "RUNNING",
            },
            "upload_probe_500m": {
                "label": METRIC_UPLOAD_PROBE_500M,
                "target": "约500MB文件可上传到后台(不入库)",
                "runs_total": 1,
                "runs_done": 0,
                "latest": None,
                "stats": _calc_stats([]),
                "success": 0,
                "generated_size_mb": 0.0,
                "received_size_mb": 0.0,
                "status": "RUNNING",
            },
        },
        "summary": {
            "pass": 0,
            "fail": 0,
        },
    }


def _save_system_test_job(job: dict[str, Any]) -> None:
    with SYSTEM_TEST_LOCK:
        SYSTEM_TEST_JOBS[job["job_id"]] = job
        if len(SYSTEM_TEST_JOBS) > MAX_SYSTEM_TEST_JOBS:
            ordered = sorted(SYSTEM_TEST_JOBS.values(), key=lambda item: item.get("created_at", ""))
            for old in ordered[: len(SYSTEM_TEST_JOBS) - MAX_SYSTEM_TEST_JOBS]:
                SYSTEM_TEST_JOBS.pop(old["job_id"], None)


def _update_system_test_job(job_id: str, updater) -> None:
    with SYSTEM_TEST_LOCK:
        job = SYSTEM_TEST_JOBS.get(job_id)
        if not job:
            return
        updater(job)
        job["updated_at"] = _now_iso()


def _get_system_test_job(job_id: str) -> dict[str, Any] | None:
    with SYSTEM_TEST_LOCK:
        job = SYSTEM_TEST_JOBS.get(job_id)
        if not job:
            return None
        return json.loads(json.dumps(job))


def _init_backup_restore_job(job_type: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    job = {
        "job_id": str(uuid.uuid4()),
        "job_type": job_type,
        "status": "running",
        "error": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "finished_at": None,
        "progress": {
            "percent": 0,
            "stage": "初始化",
            "detail": "任务已创建",
        },
        "result": {},
        "logs": [],
    }
    if extra:
        job["extra"] = extra
    return job


def _save_backup_restore_job(job: dict[str, Any]) -> None:
    with BACKUP_RESTORE_LOCK:
        BACKUP_RESTORE_JOBS[job["job_id"]] = job
        if len(BACKUP_RESTORE_JOBS) > MAX_BACKUP_RESTORE_JOBS:
            ordered = sorted(BACKUP_RESTORE_JOBS.values(), key=lambda item: item.get("created_at", ""))
            for old in ordered[: len(BACKUP_RESTORE_JOBS) - MAX_BACKUP_RESTORE_JOBS]:
                BACKUP_RESTORE_JOBS.pop(old["job_id"], None)


def _update_backup_restore_job(job_id: str, updater) -> None:
    with BACKUP_RESTORE_LOCK:
        job = BACKUP_RESTORE_JOBS.get(job_id)
        if not job:
            return
        updater(job)
        job["updated_at"] = _now_iso()


def _get_backup_restore_job(job_id: str) -> dict[str, Any] | None:
    with BACKUP_RESTORE_LOCK:
        job = BACKUP_RESTORE_JOBS.get(job_id)
        if not job:
            return None
        return json.loads(json.dumps(job))


def _update_backup_restore_progress(job_id: str, percent: int, stage: str, detail: str = "") -> None:
    def _update(job: dict[str, Any]):
        job["progress"] = {
            "percent": max(0, min(100, int(percent))),
            "stage": stage,
            "detail": detail,
        }

    _update_backup_restore_job(job_id, _update)


def _append_backup_restore_output(job_id: str, line: str) -> None:
    clean = (line or "").strip()
    if not clean:
        return

    def _update(job: dict[str, Any]):
        logs = job.get("logs") or []
        logs.append(clean)
        job["logs"] = logs[-80:]

    _update_backup_restore_job(job_id, _update)


def _finish_backup_restore_job(job_id: str, status: str, error: str = "", result: dict[str, Any] | None = None) -> None:
    def _update(job: dict[str, Any]):
        job["status"] = status
        job["error"] = error
        job["finished_at"] = _now_iso()
        if result is not None:
            job["result"] = result

    _update_backup_restore_job(job_id, _update)


def _run_backup_job(job_id: str) -> None:
    backup_root = _backup_root()
    backup_root.mkdir(parents=True, exist_ok=True)

    retention_days = _env_int("RETENTION_DAYS", 14, 1, 3650)

    try:
        job = _get_backup_restore_job(job_id) or {}
        executor_info = job.get("extra") or {}
        if not executor_info:
            executor_info = _normalize_backup_executor(None, executor_type="system")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        _update_backup_restore_progress(job_id, 5, "初始化", "开始执行参数情况表备份")
        _append_backup_restore_output(job_id, f"备份目录: {backup_root}")

        _update_backup_restore_progress(job_id, 20, "采集数据", "正在采集 QAR_Parameter_Attribute 表数据")
        payload = _build_parameter_attribute_backup_payload(executor_info)
        backup_file = backup_root / f"{BACKUP_FILE_PREFIX}_{timestamp}{BACKUP_FILE_SUFFIX}"

        _update_backup_restore_progress(job_id, 72, "写入备份文件", "正在写入备份文件")
        _write_json_gz(backup_file, payload)
        _append_backup_restore_output(
            job_id,
            f"已备份 {payload.get('record_count', 0)} 条 QAR_Parameter_Attribute 记录",
        )

        _update_backup_restore_progress(job_id, 88, "清理历史备份", "正在清理历史备份")
        deleted_count = 0
        cutoff = time.time() - (retention_days * 24 * 3600)
        for item in backup_root.iterdir():
            if not item.is_file() or not item.name.endswith(BACKUP_FILE_SUFFIX):
                continue
            try:
                if item.stat().st_mtime < cutoff:
                    item.unlink(missing_ok=True)
                    deleted_count += 1
            except Exception:
                continue
        _append_backup_restore_output(job_id, f"清理超过 {retention_days} 天备份: {deleted_count} 个")

        _update_backup_restore_progress(job_id, 100, "备份完成", f"备份完成: {backup_file.name}")
        _append_backup_restore_output(job_id, f"备份完成: {backup_file.name}")

        items = _list_backup_files()
        _append_ops_log(
            "backup",
            "PASS",
            "备份成功",
            {
                "backup_file": backup_file.name,
                "executor_type": executor_info.get("executor_type"),
                "executor_label": executor_info.get("executor_label"),
                "record_count": payload.get("record_count", 0),
            },
        )
        _finish_backup_restore_job(
            job_id,
            "completed",
            result={
                "message": "备份执行成功（仅 QAR_Parameter_Attribute）",
                "backup_file": backup_file.name,
                "backup_mode": "single_table_json",
                "executor_type": executor_info.get("executor_type"),
                "executor_label": executor_info.get("executor_label"),
                "record_count": payload.get("record_count", 0),
                "items": items,
            },
        )
    except subprocess.TimeoutExpired:
        _append_ops_log("backup", "FAIL", "备份执行超时")
        _finish_backup_restore_job(job_id, "failed", error="备份执行超时")
    except Exception as exc:
        _append_ops_log("backup", "FAIL", f"备份异常: {str(exc)}")
        _finish_backup_restore_job(job_id, "failed", error=f"备份异常: {str(exc)}")


def _start_backup_job(executor_info: dict[str, str]) -> str:
    job = _init_backup_restore_job("backup", executor_info)
    _save_backup_restore_job(job)

    thread = threading.Thread(
        target=_run_backup_job,
        args=(job["job_id"],),
        daemon=True,
    )
    thread.start()
    return job["job_id"]


def _trigger_system_auto_backup() -> str:
    executor_info = _normalize_backup_executor(None, executor_type="system")
    job_id = _start_backup_job(executor_info)
    _append_ops_log("backup", "PASS", "系统自动备份任务已启动", {"job_id": job_id, **executor_info})
    return job_id


def _run_restore_job(job_id: str, backup_name: str) -> None:
    _update_backup_restore_progress(job_id, 5, "准备恢复", "恢复任务已启动")
    _append_backup_restore_output(job_id, f"开始恢复备份: {backup_name}")

    try:
        _update_backup_restore_progress(job_id, 12, "恢复前检查", "后台执行恢复前健康检查")
        precheck = _run_restore_health_checks(backup_name)
        if not precheck["can_restore"]:
            _append_ops_log("restore", "FAIL", "恢复前检查未通过", {"backup_name": backup_name, "precheck": precheck})
            _finish_backup_restore_job(
                job_id,
                "failed",
                error="恢复前检查未通过，已拦截恢复",
                result={
                    "backup_name": backup_name,
                    "precheck": precheck,
                },
            )
            return

        _update_backup_restore_progress(job_id, 20, "执行数据恢复", "正在导入备份数据")
        _restore_from_backup(backup_name)
        _append_backup_restore_output(job_id, "恢复过程执行完成")

        _update_backup_restore_progress(job_id, 80, "恢复后探活", "正在执行探活检查")
        postcheck = _run_post_restore_probes()
        status = "PASS" if postcheck["passed"] else "FAIL"
        detail = "恢复成功，探活通过" if postcheck["passed"] else "恢复完成，但探活存在失败项"

        _append_ops_log(
            "restore",
            status,
            detail,
            {
                "backup_name": backup_name,
                "precheck": precheck,
                "postcheck": postcheck,
            },
        )

        _finish_backup_restore_job(
            job_id,
            "completed",
            result={
                "message": detail,
                "backup_name": backup_name,
                "precheck": precheck,
                "postcheck": postcheck,
            },
        )
        _update_backup_restore_progress(job_id, 100, "恢复完成", detail)
    except Exception as exc:
        _append_ops_log("restore", "FAIL", f"恢复失败: {str(exc)}", {"backup_name": backup_name})
        _finish_backup_restore_job(job_id, "failed", error=f"恢复失败: {str(exc)}")


def _auth_header_from_request(request) -> str:
    auth = request.META.get("HTTP_AUTHORIZATION")
    if auth:
        return auth

    token = request.auth
    if token:
        return f"Bearer {token}"
    return ""


def _timed_request(session: requests.Session, method: str, url: str, **kwargs) -> tuple[int, float, dict[str, Any] | None]:
    started = time.perf_counter()
    resp = session.request(method=method, url=url, timeout=30, **kwargs)
    cost = time.perf_counter() - started
    payload = None
    try:
        payload = resp.json()
    except Exception:
        payload = None
    return resp.status_code, cost, payload


def _job_write_summary_file(job: dict[str, Any]) -> None:
    run_id = str(job.get("run_id") or datetime.now().strftime("%Y%m%d_%H%M%S")).strip()
    run_dir = _benchmark_root() / f"raw_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_file = run_dir / "summary.tsv"

    query = job["metrics"]["query"]
    visual = job["metrics"]["visual"]
    upload = job["metrics"]["upload"]
    upload_probe_500m = job["metrics"].get("upload_probe_500m") or {}

    query_observed = f"p95={query['stats']['p95']:.6f}s, non200={query['non_200']}, runs={query['runs_done']}"
    query_detail = (
        f"count={query['stats']['count']} min={query['stats']['min']:.6f} avg={query['stats']['avg']:.6f} "
        f"p95={query['stats']['p95']:.6f} max={query['stats']['max']:.6f}"
    )

    visual_observed = f"p95={visual['stats']['p95']:.6f}s, non200={visual['non_200']}, runs={visual['runs_done']}"
    visual_detail = (
        f"count={visual['stats']['count']} min={visual['stats']['min']:.6f} avg={visual['stats']['avg']:.6f} "
        f"p95={visual['stats']['p95']:.6f} max={visual['stats']['max']:.6f}"
    )

    upload_observed = f"avg={upload['stats']['avg']:.6f}MB/s, success={upload['success']}/{upload['runs_done']}"
    upload_detail = (
        f"count={upload['stats']['count']} min={upload['stats']['min']:.6f} avg={upload['stats']['avg']:.6f} "
        f"p95={upload['stats']['p95']:.6f} max={upload['stats']['max']:.6f}"
    )

    probe_stats = upload_probe_500m.get("stats") or _calc_stats([])
    probe_observed = (
        f"http_success={upload_probe_500m.get('success', 0)}, "
        f"generated={float(upload_probe_500m.get('generated_size_mb', 0.0)):.2f}MB, "
        f"received={float(upload_probe_500m.get('received_size_mb', 0.0)):.2f}MB"
    )
    probe_detail = (
        f"count={probe_stats['count']} min={probe_stats['min']:.6f} avg={probe_stats['avg']:.6f} "
        f"p95={probe_stats['p95']:.6f} max={probe_stats['max']:.6f}"
    )

    lines = [
        f"{METRIC_QUERY}|{query['status']}|< 3s|{query_observed}|{query_detail}",
        f"{METRIC_VISUAL}|{visual['status']}|< 5s|{visual_observed}|{visual_detail}",
        f"{METRIC_UPLOAD}|{upload['status']}|> 50 MB/s|{upload_observed}|{upload_detail}",
        f"{METRIC_UPLOAD_PROBE_500M}|{upload_probe_500m.get('status', 'FAIL')}|约500MB文件可上传到后台(不入库)|{probe_observed}|{probe_detail}",
    ]

    with summary_file.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _run_system_test_job(job_id: str, base_url: str, auth_header: str, config: dict[str, int]) -> None:
    session = requests.Session()
    if auth_header:
        session.headers.update({"Authorization": auth_header})

    query_runs = int(config.get("query_runs", 20))
    visual_runs = int(config.get("visual_runs", 10))
    upload_runs = int(config.get("upload_runs", 3))

    query_times: list[float] = []
    query_non_200 = 0
    visual_times: list[float] = []
    visual_non_200 = 0
    upload_speeds: list[float] = []
    upload_success = 0

    def mark_progress(metric_name: str, done_inc: int = 1):
        def _update(job: dict[str, Any]):
            job["progress"]["current_metric"] = metric_name
            job["progress"]["done_rounds"] = min(
                job["progress"]["total_rounds"],
                int(job["progress"]["done_rounds"]) + done_inc,
            )

        _update_system_test_job(job_id, _update)

    def update_metric(metric_key: str, payload: dict[str, Any]):
        def _update(job: dict[str, Any]):
            job["metrics"][metric_key].update(payload)

        _update_system_test_job(job_id, _update)

    try:
        qar_id = ""
        status, _, payload = _timed_request(session, "GET", f"{base_url}/api/v1/data/qar-ids", params={"limit": 1})
        if status == 200 and isinstance(payload, dict):
            qar_id = ((payload.get("data") or {}).get("items") or [""])[0] or ""

        for i in range(query_runs):
            params = {"page": 1, "page_size": 50}
            if qar_id:
                params["qar_id"] = qar_id
            status, cost, _ = _timed_request(session, "GET", f"{base_url}/api/v1/data/preview", params=params)
            query_times.append(cost)
            if status != 200:
                query_non_200 += 1

            stats = _calc_stats(query_times)
            update_metric(
                "query",
                {
                    "runs_done": i + 1,
                    "latest": cost,
                    "stats": stats,
                    "non_200": query_non_200,
                },
            )
            mark_progress("数据查询响应时间")

        if not qar_id:
            status, _, payload = _timed_request(session, "GET", f"{base_url}/api/v1/data/qar-ids", params={"limit": 1})
            if status == 200 and isinstance(payload, dict):
                qar_id = ((payload.get("data") or {}).get("items") or [""])[0] or ""

        for i in range(visual_runs):
            if not qar_id:
                visual_non_200 += 1
                visual_times.append(0.0)
            else:
                status, cost, _ = _timed_request(
                    session,
                    "GET",
                    f"{base_url}/api/v1/flight/charts",
                    params={"qar_id": qar_id, "max_points": 1200},
                )
                visual_times.append(cost)
                if status != 200:
                    visual_non_200 += 1

            stats = _calc_stats(visual_times)
            update_metric(
                "visual",
                {
                    "runs_done": i + 1,
                    "latest": visual_times[-1] if visual_times else None,
                    "stats": stats,
                    "non_200": visual_non_200,
                },
            )
            mark_progress("数据可视化响应时间")

        sample_file = _project_root() / "test.csv"
        file_size_mb = (sample_file.stat().st_size / 1024 / 1024) if sample_file.exists() else 0.0

        for i in range(upload_runs):
            speed = 0.0
            if sample_file.exists():
                with sample_file.open("rb") as fp:
                    status, cost, payload = _timed_request(
                        session,
                        "POST",
                        f"{base_url}/api/v1/system/test/upload-probe",
                        files={"file": (sample_file.name, fp, "text/csv")},
                    )

                code = (payload or {}).get("code") if isinstance(payload, dict) else None
                if status == 200 and code == 0 and cost > 0:
                    speed = file_size_mb / cost
                    upload_success += 1

            upload_speeds.append(speed)
            stats = _calc_stats(upload_speeds)
            update_metric(
                "upload",
                {
                    "runs_done": i + 1,
                    "latest": speed,
                    "stats": stats,
                    "success": upload_success,
                },
            )
            mark_progress("数据上传速度")

        query_stats = _calc_stats(query_times)
        visual_stats = _calc_stats(visual_times)
        upload_stats = _calc_stats(upload_speeds)

        query_pass = query_non_200 == 0 and query_stats["p95"] < 3.0
        visual_pass = visual_non_200 == 0 and visual_stats["p95"] < 5.0
        upload_pass = upload_success > 0 and upload_stats["avg"] > 50.0

        current_job = _get_system_test_job(job_id) or {}
        probe_metric = (current_job.get("metrics") or {}).get("upload_probe_500m") or {}
        upload_probe_500m_pass = str(probe_metric.get("status") or "").upper() == "PASS"

        def _finish(job: dict[str, Any]):
            job["metrics"]["query"]["status"] = "PASS" if query_pass else "FAIL"
            job["metrics"]["visual"]["status"] = "PASS" if visual_pass else "FAIL"
            job["metrics"]["upload"]["status"] = "PASS" if upload_pass else "FAIL"
            if str(job["metrics"]["upload_probe_500m"].get("status") or "").upper() != "PASS":
                job["metrics"]["upload_probe_500m"]["status"] = "FAIL"
            job["status"] = "completed"
            job["finished_at"] = _now_iso()
            job["progress"]["done_rounds"] = int(job["progress"].get("total_rounds") or 0)
            job["progress"]["current_metric"] = "完成"
            job["summary"] = {
                "pass": int(query_pass) + int(visual_pass) + int(upload_pass) + int(upload_probe_500m_pass),
                "fail": int(not query_pass) + int(not visual_pass) + int(not upload_pass) + int(not upload_probe_500m_pass),
            }

        _update_system_test_job(job_id, _finish)
        done_job = _get_system_test_job(job_id)
        if done_job:
            _job_write_summary_file(done_job)
            _append_ops_log("system_test", "PASS", "一键测试完成", {"job_id": job_id, "summary": done_job["summary"]})

    except Exception as exc:
        def _fail(job: dict[str, Any]):
            job["status"] = "failed"
            job["error"] = str(exc)
            job["finished_at"] = _now_iso()

        _update_system_test_job(job_id, _fail)
        _append_ops_log("system_test", "FAIL", f"一键测试失败: {str(exc)}", {"job_id": job_id})


def _resolve_db_info() -> dict[str, str]:
    db = settings.DATABASES.get("default", {})
    return {
        "engine": db.get("ENGINE") or "",
        "name": db.get("NAME") or "",
        "user": db.get("USER") or "",
        "password": db.get("PASSWORD") or "",
        "host": db.get("HOST") or "127.0.0.1",
        "port": str(db.get("PORT") or ""),
    }


def _normalize_backup_executor(request_user=None, executor_type: str = "user") -> dict[str, str]:
    executor_kind = "system" if executor_type == "system" else "user"
    if executor_kind == "system":
        return {
            "executor_type": "system",
            "executor_label": "系统自动备份",
            "executor_name": "system",
        }

    username = ""
    if request_user is not None and getattr(request_user, "is_authenticated", False):
        try:
            username = request_user.get_username() or ""
        except Exception:
            username = getattr(request_user, "username", "") or ""

    username = str(username or "").strip() or "unknown"
    return {
        "executor_type": "user",
        "executor_label": f"用户：{username}",
        "executor_name": username,
    }


def _build_parameter_attribute_backup_payload(executor_info: dict[str, str]) -> dict[str, Any]:
    now = _now_iso()
    records = list(
        QAR_Parameter_Attribute.objects.all()
        .order_by("parameter_name")
        .values(*BACKUP_RECORD_FIELDS)
    )
    payload = {
        "format": "qar_parameter_attribute_backup_v1",
        "table_name": BACKUP_TABLE_NAME,
        "created_at": now,
        "record_count": len(records),
        "records": records,
    }
    payload.update(executor_info or {})
    return payload


def _write_json_gz(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(_to_json_safe(payload), f, ensure_ascii=False)


def _read_json_gz(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _list_backup_files() -> list[dict[str, Any]]:
    root = _backup_root()
    if not root.exists():
        return []

    rows: list[dict[str, Any]] = []
    for file in root.iterdir():
        if not file.is_file():
            continue
        if not file.name.endswith(BACKUP_FILE_SUFFIX):
            continue

        try:
            payload = _read_json_gz(file)
        except Exception:
            payload = {}
        rows.append(
            {
                "name": file.name,
                "path": str(file),
                "table_name": payload.get("table_name") or BACKUP_TABLE_NAME,
                "created_at": payload.get("created_at") or datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc).isoformat(),
                "executor_type": payload.get("executor_type") or "user",
                "executor_label": payload.get("executor_label") or "未知",
                "executor_name": payload.get("executor_name") or "",
                "record_count": payload.get("record_count") or 0,
                "modified_at": datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    rows.sort(key=lambda item: item.get("created_at") or item.get("modified_at") or "", reverse=True)
    return rows


def _restore_sqlite(db_name: str, backup_path: Path) -> None:
    db_path = Path(db_name)
    if not db_path.is_absolute():
        db_path = _project_root() / db_path

    if not db_path.exists():
        raise RuntimeError(f"SQLite 数据库文件不存在: {db_path}")
    _restore_parameter_attribute_backup(backup_path)


def _export_sqlite_data_only(db_path: Path, backup_file: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.text_factory = str
        with backup_file.open("w", encoding="utf-8") as out:
            out.write("PRAGMA foreign_keys=OFF;\n")
            out.write("BEGIN TRANSACTION;\n")
            for line in conn.iterdump():
                sql = (line or "").strip()
                if not sql.startswith("INSERT INTO "):
                    continue
                match = re.match(r'^INSERT INTO\s+"?([^"\s]+)"?', sql, flags=re.IGNORECASE)
                if not match:
                    continue
                table_name = match.group(1)
                if _is_system_table(table_name):
                    continue
                out.write(sql + "\n")
            out.write("COMMIT;\n")
            out.write("PRAGMA foreign_keys=ON;\n")


def _clear_all_table_data() -> None:
    db = _resolve_db_info()
    engine = db.get("engine") or ""

    with connection.cursor() as cursor:
        if "postgresql" in engine:
            cursor.execute(
                """
                SELECT quote_ident(schemaname) || '.' || quote_ident(tablename)
                FROM pg_tables
                WHERE schemaname = 'public'
                """
            )
            tables = [row[0] for row in cursor.fetchall() if not _is_system_table(str(row[0]).split(".")[-1].strip('"'))]
            if tables:
                cursor.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
            return

        if "mysql" in engine:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                """
            )
            table_names = [row[0] for row in cursor.fetchall()]
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            for table_name in table_names:
                if _is_system_table(table_name):
                    continue
                safe_name = str(table_name).replace("`", "``")
                cursor.execute(f"TRUNCATE TABLE `{safe_name}`")
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
            return

        if "sqlite3" in engine:
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """
            )
            table_names = [row[0] for row in cursor.fetchall()]
            cursor.execute("PRAGMA foreign_keys=OFF")
            for table_name in table_names:
                if _is_system_table(table_name):
                    continue
                safe_name = str(table_name).replace('"', '""')
                cursor.execute(f'DELETE FROM "{safe_name}"')
            cursor.execute(
                """
                DELETE FROM sqlite_sequence
                WHERE name NOT LIKE 'django_%' AND name NOT LIKE 'auth_%'
                """
            )
            cursor.execute("PRAGMA foreign_keys=ON")
            return

    raise RuntimeError(f"暂不支持的数据库引擎: {engine}")


def _clear_parameter_attribute_table() -> None:
    QAR_Parameter_Attribute.objects.all().delete()


def _restore_parameter_attribute_backup(backup_path: Path) -> None:
    payload = _read_json_gz(backup_path)
    if payload.get("table_name") != BACKUP_TABLE_NAME:
        raise RuntimeError("备份文件表名不匹配")

    records = payload.get("records") or []
    if not isinstance(records, list):
        raise RuntimeError("备份文件内容格式错误")

    objs: list[QAR_Parameter_Attribute] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        row = {field: item.get(field) for field in BACKUP_RECORD_FIELDS}
        if row.get("updated_time"):
            try:
                row["updated_time"] = datetime.fromisoformat(str(row["updated_time"]))
            except Exception:
                row["updated_time"] = timezone.now()
        else:
            row["updated_time"] = timezone.now()
        objs.append(QAR_Parameter_Attribute(**row))

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")

    with transaction.atomic():
        _clear_parameter_attribute_table()
        if objs:
            QAR_Parameter_Attribute.objects.bulk_create(objs, batch_size=1000)


def _restore_sqlite_data_only_sql(db_path: Path, backup_path: Path) -> None:
    temp_file: NamedTemporaryFile | None = None
    sql_path = backup_path
    try:
        if backup_path.suffix == ".gz":
            temp_file = NamedTemporaryFile(delete=False, suffix=".sql")
            with gzip.open(backup_path, "rb") as src, open(temp_file.name, "wb") as dst:
                shutil.copyfileobj(src, dst)
            sql_path = Path(temp_file.name)

        _clear_all_table_data()
        with sqlite3.connect(str(db_path)) as conn:
            script = sql_path.read_text(encoding="utf-8")
            conn.executescript(script)
            conn.commit()
    finally:
        if temp_file:
            Path(temp_file.name).unlink(missing_ok=True)


def _pipe_sql_dump_to_client(backup_path: Path, command: list[str], env: dict[str, str]) -> None:
    restore_timeout = _env_int("RESTORE_TIMEOUT_SECONDS", 3600, 60, 24 * 3600)
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(_project_root()),
    )

    try:
        if process.stdin is None:
            raise RuntimeError("无法打开数据库客户端输入流")

        if backup_path.suffix == ".gz":
            source = gzip.open(backup_path, "rb")
        else:
            source = open(backup_path, "rb")

        with source as src:
            shutil.copyfileobj(src, process.stdin)

        process.stdin.close()
        process.stdin = None
        stdout, stderr = process.communicate(timeout=restore_timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError("恢复执行超时")

    if process.returncode != 0:
        raise RuntimeError((stderr or b"").decode("utf-8", errors="ignore")[:3000] or "恢复执行失败")


def _restore_postgresql(db: dict[str, str], backup_path: Path) -> None:
    cmd = [
        "psql",
        "-h",
        db["host"] or "127.0.0.1",
        "-p",
        db["port"] or "5432",
        "-U",
        db["user"],
        "-d",
        db["name"],
    ]
    env = os.environ.copy()
    env["PGPASSWORD"] = db["password"]
    _pipe_sql_dump_to_client(backup_path, cmd, env)


def _restore_mysql(db: dict[str, str], backup_path: Path) -> None:
    cmd = [
        "mysql",
        "-h",
        db["host"] or "127.0.0.1",
        "-P",
        db["port"] or "3306",
        "-u",
        db["user"],
        db["name"],
    ]
    env = os.environ.copy()
    env["MYSQL_PWD"] = db["password"]
    _pipe_sql_dump_to_client(backup_path, cmd, env)


def _restore_from_backup(backup_name: str) -> None:
    backup_dir = _backup_root()
    backup_path = (backup_dir / backup_name).resolve()
    if backup_dir.resolve() not in backup_path.parents:
        raise RuntimeError("不允许访问备份目录外的文件")

    if not backup_path.exists() or not backup_path.is_file():
        raise RuntimeError("备份文件不存在")
    if not backup_path.name.endswith(BACKUP_FILE_SUFFIX):
        raise RuntimeError("仅支持参数情况表备份文件（.json.gz）")

    _restore_parameter_attribute_backup(backup_path)


def _result_item(name: str, passed: bool, detail: str, value: Any = None) -> dict[str, Any]:
    row = {
        "name": name,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }
    if value is not None:
        row["value"] = value
    return row


def _run_restore_health_checks(backup_name: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    backup_dir = _backup_root().resolve()
    backup_path = (backup_dir / backup_name).resolve()
    in_backup_dir = backup_dir == backup_path.parent
    checks.append(
        _result_item(
            "backup_path_scope",
            in_backup_dir,
            "备份文件位于允许目录" if in_backup_dir else "备份文件路径不在允许目录",
            str(backup_path),
        )
    )

    backup_exists = backup_path.exists() and backup_path.is_file()
    checks.append(
        _result_item(
            "backup_file_exists",
            backup_exists,
            "备份文件存在" if backup_exists else "备份文件不存在",
        )
    )

    backup_readable = backup_exists and os.access(backup_path, os.R_OK)
    checks.append(
        _result_item(
            "backup_readable",
            backup_readable,
            "备份文件可读取" if backup_readable else "备份文件不可读取",
        )
    )

    backup_format_supported = backup_name.endswith(BACKUP_FILE_SUFFIX)
    checks.append(
        _result_item(
            "backup_format_supported",
            backup_format_supported,
            "备份文件格式支持" if backup_format_supported else "仅支持参数情况表备份文件（.json.gz）",
            backup_name,
        )
    )

    db = _resolve_db_info()
    engine = db.get("engine") or ""
    engine_supported = any(name in engine for name in ("sqlite3", "postgresql", "mysql"))
    checks.append(
        _result_item(
            "db_engine_supported",
            engine_supported,
            "数据库引擎可恢复" if engine_supported else f"暂不支持恢复引擎: {engine}",
            engine,
        )
    )

    if "postgresql" in engine:
        has_client = shutil.which("psql") is not None
        checks.append(
            _result_item(
                "db_restore_client",
                has_client,
                "检测到 psql 客户端" if has_client else "未检测到 psql 客户端",
            )
        )
    elif "mysql" in engine:
        has_client = shutil.which("mysql") is not None
        checks.append(
            _result_item(
                "db_restore_client",
                has_client,
                "检测到 mysql 客户端" if has_client else "未检测到 mysql 客户端",
            )
        )

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            value = cursor.fetchone()[0]
        checks.append(_result_item("db_connectivity", value == 1, "数据库连通", value))
    except Exception as exc:
        checks.append(_result_item("db_connectivity", False, f"数据库连通失败: {str(exc)}"))

    try:
        sample_count = QAR.objects.count()
        checks.append(_result_item("qar_query", True, "QAR 数据可读", sample_count))
    except Exception as exc:
        checks.append(_result_item("qar_query", False, f"QAR 查询失败: {str(exc)}"))

    can_restore = all(item["passed"] for item in checks)
    return {
        "backup_name": backup_name,
        "can_restore": can_restore,
        "checked_at": _now_iso(),
        "items": checks,
    }


def _run_post_restore_probes() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    probes: list[dict[str, Any]] = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            value = cursor.fetchone()[0]
        probes.append(_result_item("db_ping", value == 1, "数据库探活成功", value))
    except Exception as exc:
        probes.append(_result_item("db_ping", False, f"数据库探活失败: {str(exc)}"))

    try:
        user_count = get_user_model().objects.count()
        probes.append(_result_item("auth_model_probe", True, "认证模型可访问", user_count))
    except Exception as exc:
        probes.append(_result_item("auth_model_probe", False, f"认证模型探活失败: {str(exc)}"))

    try:
        qar_count = QAR.objects.count()
        probes.append(_result_item("qar_model_probe", True, "QAR 主表可访问", qar_count))
    except Exception as exc:
        probes.append(_result_item("qar_model_probe", False, f"QAR 主表探活失败: {str(exc)}"))

    try:
        summary_count = QAR_Overview.objects.count()
        probes.append(_result_item("summary_model_probe", True, "QAR 汇总表可访问", summary_count))
    except Exception as exc:
        probes.append(_result_item("summary_model_probe", False, f"QAR 汇总表探活失败: {str(exc)}"))

    ended = datetime.now(timezone.utc)
    duration_ms = max(0, int((ended - started).total_seconds() * 1000))
    passed = all(item["passed"] for item in probes)
    return {
        "passed": passed,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_ms": duration_ms,
        "items": probes,
    }


class SystemTestUploadProbeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return fail("缺少 file 文件", status_code=400)

        size_bytes = getattr(upload, "size", None)
        if size_bytes is None:
            size_bytes = 0
            for chunk in upload.chunks():
                size_bytes += len(chunk)

        return ok(
            {
                "filename": upload.name,
                "size_bytes": int(size_bytes or 0),
            },
            message="上传探测成功",
        )


class SystemMetricsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        runs = _collect_metric_runs(limit=16)
        latest_run = runs[0] if runs else None
        return ok(
            {
                "latest_run": latest_run,
                "kpis": _build_kpis(latest_run),
                "trend": _build_trend_series(runs),
                "runs": runs,
            }
        )


class BackupListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return ok(
            {
                "backup_dir": str(_backup_root()),
                "items": _list_backup_files(),
                "logs": _read_ops_logs(),
            }
        )


class BackupRunAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        executor_info = _normalize_backup_executor(getattr(request, "user", None), executor_type="user")
        job_id = _start_backup_job(executor_info)
        _append_ops_log("backup", "PASS", "备份任务已启动", {"job_id": job_id, **executor_info})
        return ok(
            {
                "job_id": job_id,
                "job_type": "backup",
                "status": "running",
                "executor_type": executor_info.get("executor_type"),
                "executor_label": executor_info.get("executor_label"),
            }
        )


class BackupPrecheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        backup_name = (request.GET.get("backup_name") or "").strip()
        if not backup_name:
            return fail("缺少 backup_name", status_code=400)
        if "/" in backup_name or "\\" in backup_name:
            return fail("backup_name 非法", status_code=400)

        check_result = _run_restore_health_checks(backup_name)
        status = "PASS" if check_result["can_restore"] else "FAIL"
        _append_ops_log("restore_precheck", status, "恢复前健康检查", {"result": check_result})
        return ok(check_result)


class BackupRestoreAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        backup_name = (request.data.get("backup_name") or "").strip()
        confirm_text = (request.data.get("confirm_text") or "").strip().upper()

        if not backup_name:
            return fail("缺少 backup_name", status_code=400)
        if "/" in backup_name or "\\" in backup_name:
            return fail("backup_name 非法", status_code=400)
        if confirm_text != "RESTORE":
            return fail("确认口令错误，请输入 RESTORE", status_code=400)

        job = _init_backup_restore_job("restore", {"backup_name": backup_name})
        _save_backup_restore_job(job)

        thread = threading.Thread(
            target=_run_restore_job,
            args=(job["job_id"], backup_name),
            daemon=True,
        )
        thread.start()

        _append_ops_log("restore", "PASS", "恢复任务已启动", {"job_id": job["job_id"], "backup_name": backup_name})
        return ok(
            {
                "job_id": job["job_id"],
                "job_type": "restore",
                "status": "running",
                "backup_name": backup_name,
                "precheck": None,
            }
        )


class BackupJobStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        job_id = (request.GET.get("job_id") or "").strip()
        if not job_id:
            return fail("缺少 job_id", status_code=400)

        job = _get_backup_restore_job(job_id)
        if not job:
            return fail("任务不存在", status_code=404)

        return ok({"job": job})


class OpsLogAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logs = _read_ops_logs(limit=min(max(int(request.GET.get("limit", 120)), 1), 500))
        return ok({"items": logs})


class SystemTestRunAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        query_runs = min(max(int(request.data.get("query_runs", 20)), 1), 200)
        visual_runs = min(max(int(request.data.get("visual_runs", 10)), 1), 200)
        upload_runs = min(max(int(request.data.get("upload_runs", 3)), 1), 50)

        config = {
            "query_runs": query_runs,
            "visual_runs": visual_runs,
            "upload_runs": upload_runs,
        }

        job = _init_system_test_job(config)
        _save_system_test_job(job)

        base_url = request.build_absolute_uri("/").rstrip("/")
        auth_header = _auth_header_from_request(request)

        thread = threading.Thread(
            target=_run_system_test_job,
            args=(job["job_id"], base_url, auth_header, config),
            daemon=True,
        )
        thread.start()

        _append_ops_log("system_test", "PASS", "一键测试已启动", {"job_id": job["job_id"], "config": config})
        return ok({"job_id": job["job_id"], "config": config, "status": "running"})


class SystemTestStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        job_id = (request.GET.get("job_id") or "").strip()
        if not job_id:
            return fail("缺少 job_id", status_code=400)

        job = _get_system_test_job(job_id)
        if not job:
            return fail("测试任务不存在", status_code=404)

        return ok({"job": job})


class SystemTestMetricUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job_id = (request.data.get("job_id") or "").strip()
        metric_key = (request.data.get("metric_key") or "").strip()
        if not job_id:
            return fail("缺少 job_id", status_code=400)
        if metric_key != "upload_probe_500m":
            return fail("仅支持更新 upload_probe_500m 指标", status_code=400)

        job = _get_system_test_job(job_id)
        if not job:
            return fail("测试任务不存在", status_code=404)

        try:
            latest = float(request.data.get("latest", 0.0))
        except (TypeError, ValueError):
            latest = 0.0

        try:
            generated_size_mb = float(request.data.get("generated_size_mb", 0.0))
        except (TypeError, ValueError):
            generated_size_mb = 0.0

        try:
            received_size_mb = float(request.data.get("received_size_mb", 0.0))
        except (TypeError, ValueError):
            received_size_mb = 0.0

        success = 1 if str(request.data.get("success", "0")).strip().lower() in {"1", "true", "yes", "on"} else 0
        status = "PASS" if success == 1 else "FAIL"
        probe_stats = _calc_stats([latest])

        def _update_metric(job_obj: dict[str, Any]):
            metric = job_obj.get("metrics", {}).get("upload_probe_500m")
            if not isinstance(metric, dict):
                return

            prev_done = int(metric.get("runs_done") or 0)

            metric.update(
                {
                    "runs_done": 1,
                    "latest": latest,
                    "stats": probe_stats,
                    "success": success,
                    "generated_size_mb": round(generated_size_mb, 2),
                    "received_size_mb": round(received_size_mb, 2),
                    "status": status,
                }
            )

            if prev_done <= 0:
                progress = job_obj.get("progress") or {}
                progress["done_rounds"] = min(
                    int(progress.get("total_rounds") or 0),
                    int(progress.get("done_rounds") or 0) + 1,
                )
                progress["current_metric"] = "500M数据导入链路探测"
                job_obj["progress"] = progress

            if job_obj.get("status") == "completed":
                metrics = job_obj.get("metrics", {})
                statuses = [
                    str((metrics.get("query") or {}).get("status") or "FAIL").upper(),
                    str((metrics.get("visual") or {}).get("status") or "FAIL").upper(),
                    str((metrics.get("upload") or {}).get("status") or "FAIL").upper(),
                    str((metrics.get("upload_probe_500m") or {}).get("status") or "FAIL").upper(),
                ]
                pass_count = sum(1 for s in statuses if s == "PASS")
                fail_count = len(statuses) - pass_count
                job_obj["summary"] = {
                    "pass": pass_count,
                    "fail": fail_count,
                }

        _update_system_test_job(job_id, _update_metric)
        updated_job = _get_system_test_job(job_id)
        if updated_job and updated_job.get("status") == "completed":
            _job_write_summary_file(updated_job)

        return ok({"job": updated_job})
