from __future__ import annotations

import logging
import os
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_BACKUP_SCHEDULER_STARTED = False
_BACKUP_SCHEDULER_LOCK = threading.Lock()
_BACKUP_SCHEDULER_STOP_EVENT = threading.Event()

_DEFAULT_BACKUP_INTERVAL_SECONDS = 12 * 60 * 60


def _scheduler_enabled() -> bool:
    raw = os.getenv("BACKUP_SCHEDULER_ENABLED")
    if raw is None:
        return True
    normalized = str(raw).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _is_runserver_worker() -> bool:
    if not getattr(settings, "DEBUG", False):
        return True
    return os.environ.get("RUN_MAIN") == "true"


def _backup_interval_seconds() -> float:
    raw = os.getenv("BACKUP_SCHEDULER_INTERVAL_SECONDS")
    if raw is None:
        return float(_DEFAULT_BACKUP_INTERVAL_SECONDS)

    try:
        interval = float(raw)
    except (TypeError, ValueError):
        interval = float(_DEFAULT_BACKUP_INTERVAL_SECONDS)

    return max(1.0, interval)


def _backup_worker() -> None:
    from .views_system import _trigger_system_auto_backup

    logger.info("系统自动备份调度线程已启动")
    interval_seconds = _backup_interval_seconds()
    logger.info("系统自动备份调度间隔: %s 秒", int(interval_seconds))

    while not _BACKUP_SCHEDULER_STOP_EVENT.is_set():
        if _BACKUP_SCHEDULER_STOP_EVENT.wait(timeout=interval_seconds):
            break
        try:
            _trigger_system_auto_backup()
        except Exception:
            logger.exception("系统自动备份执行失败")


def start_backup_scheduler() -> None:
    global _BACKUP_SCHEDULER_STARTED

    if not _scheduler_enabled():
        return
    if not _is_runserver_worker():
        return

    with _BACKUP_SCHEDULER_LOCK:
        if _BACKUP_SCHEDULER_STARTED:
            return
        thread = threading.Thread(target=_backup_worker, daemon=True, name="backup-5min-scheduler")
        thread.start()
        _BACKUP_SCHEDULER_STARTED = True
