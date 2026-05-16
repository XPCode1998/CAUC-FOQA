from django.db.models import Count, Min, Max
from django.utils import timezone

from apps.core.models import QAR, QAR_Parameter_Attribute, QAR_Overview
from apps.core.mask_codec import get_mask_fields
from apps.core.models import QAR_Mask

RISK_LABEL_TEXT = {
    0: '正常状态',
    1: '结冰状态',
    2: '单发失效',
    3: '双发失效',
    4: '低能量',
}


def _is_observed_mask_bit(value):
    """Normalize mask bit semantics: 1=observed, 0=missing.

    Be tolerant to historical string values like '0'/'1'.
    """
    if value is None:
        return False

    if isinstance(value, bool):
        return bool(value)

    if isinstance(value, (int, float)):
        return int(value) != 0

    text = str(value).strip().lower()
    if text in {'0', 'false', 'f', 'no', 'n', ''}:
        return False
    if text in {'1', 'true', 't', 'yes', 'y'}:
        return True
    return bool(text)


def _monitored_attrs():
    attrs = list(
        QAR_Parameter_Attribute.objects.filter(is_monitored=True).values(
            'parameter_name',
            'warning_lower',
            'warning_upper',
            'critical_lower',
            'critical_upper',
        )
    )
    monitored = [a for a in attrs if a.get('parameter_name')]
    monitored_fields = [a['parameter_name'] for a in monitored]
    # QAR 管理页“参数维度”按数据字段总维度展示，而不是按维度分类数量。
    dimension_count = len(QAR.get_fields())
    return monitored, monitored_fields, dimension_count


def _is_exceeded(value, attr):
    if value is None:
        return False
    if attr.get('critical_lower') is not None and value < attr['critical_lower']:
        return True
    if attr.get('critical_upper') is not None and value > attr['critical_upper']:
        return True
    if attr.get('warning_lower') is not None and value < attr['warning_lower']:
        return True
    if attr.get('warning_upper') is not None and value > attr['warning_upper']:
        return True
    return False


def _compute_exceed_ratio(qar_id, monitored_params):
    monitored_fields = [item['parameter_name'] for item in monitored_params if item.get('parameter_name')]
    if not monitored_fields:
        return 0.0

    attr_map = {item['parameter_name']: item for item in monitored_params}
    exceeded_cells = 0
    observed_cells = 0

    queryset = QAR.objects.filter(qar_id=qar_id).values(*monitored_fields)
    for row in queryset.iterator(chunk_size=1000):
        for field in monitored_fields:
            value = row.get(field)
            if value is None:
                continue
            observed_cells += 1
            if _is_exceeded(value, attr_map[field]):
                exceeded_cells += 1

    if observed_cells <= 0:
        return 0.0
    return round((exceeded_cells / observed_cells) * 100, 2)


def _compute_missing_ratio(qar_id):
    mask_fields = get_mask_fields()
    if not mask_fields:
        return 0.0

    total_records = 0
    missing_count = 0
    qs = QAR_Mask.objects.filter(qar_id=qar_id).values('mask_list')
    for row in qs.iterator(chunk_size=1000):
        total_records += 1
        values = row.get('mask_list') or []
        observed = sum(1 for value in values if _is_observed_mask_bit(value))
        row_missing = max(len(mask_fields), len(values)) - observed if values else len(mask_fields)
        missing_count += max(row_missing, 0)

    total_cells = total_records * len(mask_fields)
    if total_cells <= 0:
        return 0.0
    return round((missing_count / total_cells) * 100, 2)


def rebuild_qar_summary(qar_id):
    if not qar_id:
        return None

    base_qs = QAR.objects.filter(qar_id=qar_id)
    agg = base_qs.aggregate(
        total_rows=Count('id'),
        min_sim_time=Min('dSimTime'),
        max_sim_time=Max('dSimTime'),
    )

    total_rows = agg.get('total_rows') or 0
    if total_rows <= 0:
        QAR_Overview.objects.filter(qar_id=qar_id).delete()
        return None

    monitored_params, _, dimension_count = _monitored_attrs()
    exceed_ratio = _compute_exceed_ratio(qar_id, monitored_params)
    missing_ratio = _compute_missing_ratio(qar_id)

    min_t = agg.get('min_sim_time')
    max_t = agg.get('max_sim_time')
    flight_duration = round((max_t - min_t), 2) if (min_t is not None and max_t is not None) else 0.0

    existing_summary = QAR_Overview.objects.filter(qar_id=qar_id).first()
    if existing_summary is not None and existing_summary.label is not None:
        label_value = existing_summary.label
    else:
        label_value = 0

    try:
        label_value = int(label_value)
    except (TypeError, ValueError):
        label_value = 0

    now = timezone.now()
    defaults = {
        'flight_duration': flight_duration,
        'parameter_dimension': dimension_count,
        'exceed_ratio': exceed_ratio,
        'missing_ratio': missing_ratio,
        'risk_label': RISK_LABEL_TEXT.get(label_value, '未知'),
        'record_count': total_rows,
        'label': label_value,
        'created_time': now,
        'updated_time': now,
    }
    summary, _ = QAR_Overview.objects.update_or_create(qar_id=qar_id, defaults=defaults)
    return summary


def rebuild_qar_summaries(qar_ids):
    for qar_id in set([item for item in qar_ids if item]):
        rebuild_qar_summary(qar_id)


def rebuild_all_qar_summaries():
    qar_ids = list(
        QAR.objects.exclude(qar_id__isnull=True)
        .exclude(qar_id='')
        .values_list('qar_id', flat=True)
        .distinct()
    )
    rebuild_qar_summaries(qar_ids)
    QAR_Overview.objects.exclude(qar_id__in=qar_ids).delete()
