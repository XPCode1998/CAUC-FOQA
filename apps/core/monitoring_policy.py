"""QAR 参数监控白名单策略。"""

import math

from apps.core.models import QAR_Parameter_Attribute
from apps.core.parameter_metadata import VISUALIZATION_PARAMETER_SET


# 监控参数：与飞行参数可视化页面涉及参数保持一致。
MONITORED_PARAMETER_SET = set(VISUALIZATION_PARAMETER_SET)

# 目标分布策略：严重约2%，普通约3%（总超限约5%）
CRITICAL_Z = 2.326347874  # 双侧 1% / 99%
WARNING_Z = 1.959963985   # 双侧 2.5% / 97.5%


def apply_monitoring_policy():
    """应用监控策略并返回更新记录数。"""
    updated = 0
    rows = QAR_Parameter_Attribute.objects.all().only(
        "id",
        "parameter_name",
        "is_monitored",
        "warning_lower",
        "warning_upper",
        "critical_lower",
        "critical_upper",
    )

    for row in rows:
        should_monitor = row.parameter_name in MONITORED_PARAMETER_SET
        changed = False

        if row.is_monitored != should_monitor:
            row.is_monitored = should_monitor
            changed = True

        if not should_monitor:
            if row.warning_lower is not None:
                row.warning_lower = None
                changed = True
            if row.warning_upper is not None:
                row.warning_upper = None
                changed = True
            if row.critical_lower is not None:
                row.critical_lower = None
                changed = True
            if row.critical_upper is not None:
                row.critical_upper = None
                changed = True

        if changed:
            row.save(
                update_fields=[
                    "is_monitored",
                    "warning_lower",
                    "warning_upper",
                    "critical_lower",
                    "critical_upper",
                ]
            )
            updated += 1

    return updated


def apply_threshold_policy_from_existing_stats():
    """基于已有 mean/variance 快速推导阈值，避免全量扫描导致长耗时。"""
    updated = 0
    rows = QAR_Parameter_Attribute.objects.all().only(
        "id",
        "parameter_name",
        "is_monitored",
        "mean",
        "variance",
        "warning_lower",
        "warning_upper",
        "critical_lower",
        "critical_upper",
    )

    for row in rows:
        if not row.is_monitored:
            continue
        if row.mean is None or row.variance is None:
            continue

        std = math.sqrt(row.variance) if row.variance > 0 else 0.0
        warning_lower = round(float(row.mean - WARNING_Z * std), 2)
        warning_upper = round(float(row.mean + WARNING_Z * std), 2)
        critical_lower = round(float(row.mean - CRITICAL_Z * std), 2)
        critical_upper = round(float(row.mean + CRITICAL_Z * std), 2)

        changed = False
        if row.warning_lower != warning_lower:
            row.warning_lower = warning_lower
            changed = True
        if row.warning_upper != warning_upper:
            row.warning_upper = warning_upper
            changed = True
        if row.critical_lower != critical_lower:
            row.critical_lower = critical_lower
            changed = True
        if row.critical_upper != critical_upper:
            row.critical_upper = critical_upper
            changed = True

        if changed:
            row.save(
                update_fields=[
                    "warning_lower",
                    "warning_upper",
                    "critical_lower",
                    "critical_upper",
                ]
            )
            updated += 1

    return updated
