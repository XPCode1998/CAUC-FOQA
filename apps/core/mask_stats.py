from __future__ import annotations

from collections import defaultdict

from apps.core.mask_codec import get_mask_fields, get_mask_index_map
from apps.core.models import QAR_Overview, QAR_Mask, QAR_Parameter_Attribute


_STATUS_LABELS = {
    0: '正常状态',
    1: '结冰状态',
    2: '单发失效',
    3: '双发失效',
    4: '低能量',
}


def calculate_flight_status_stats() -> list[dict]:
    mask_fields = get_mask_fields()
    status_counters = defaultdict(lambda: {'total': 0, 'missing': 0})
    qar_labels = dict(QAR_Overview.objects.values_list('qar_id', 'label'))

    for mask_row in QAR_Mask.objects.values('qar_id', 'mask_list').iterator(chunk_size=1000):
        label = qar_labels.get(mask_row.get('qar_id'), 0)
        values = mask_row.get('mask_list') or []
        observed = sum(1 for v in values if bool(v))
        missing = max(len(mask_fields), len(values)) - observed if values else len(mask_fields)

        status_counters[label]['total'] += 1
        status_counters[label]['missing'] += max(missing, 0)

    status_stats = []
    for label, name in _STATUS_LABELS.items():
        total = status_counters[label]['total']
        total_cells = total * len(mask_fields)
        missing = status_counters[label]['missing']

        missing_rate = round((missing / total_cells) * 100, 2) if total_cells > 0 else 0.0
        completeness = round(100 - missing_rate, 2)

        status_class = 'danger' if missing_rate > 20 else 'warning' if missing_rate > 10 else 'success'
        status_stats.append(
            {
                'name': name,
                'missing_rate': missing_rate,
                'completeness': completeness,
                'total': total,
                'status_class': status_class,
            }
        )

    return status_stats


def calculate_field_missing_stats() -> list[dict]:
    total = QAR_Mask.objects.count() or 1
    parameter_fields = list(
        QAR_Parameter_Attribute.objects.filter(
            normalized_variance__gt=0.1,
            is_monitored=True,
        ).values_list('parameter_name', flat=True)
    )
    if not parameter_fields:
        return []

    index_map = get_mask_index_map()
    target_fields = [field for field in parameter_fields if field in index_map]
    if not target_fields:
        return []

    missing_counter = {field: 0 for field in target_fields}
    for row in QAR_Mask.objects.values('mask_list').iterator(chunk_size=1000):
        values = row.get('mask_list') or []
        for field in target_fields:
            idx = index_map[field]
            observed = bool(values[idx]) if idx < len(values) else False
            if not observed:
                missing_counter[field] += 1

    attrs = {
        item.parameter_name: item
        for item in QAR_Parameter_Attribute.objects.filter(parameter_name__in=target_fields)
    }

    field_stats = []
    for field_name in target_fields:
        attr = attrs.get(field_name)
        if not attr:
            continue

        missing = missing_counter[field_name]
        missing_rate = round((missing / total) * 100, 2) if total > 0 else 0.0
        completeness = 100 - missing_rate

        if missing_rate > 20:
            status_class = 'danger'
        elif missing_rate > 10:
            status_class = 'warning'
        elif missing_rate > 5:
            status_class = 'primary'
        else:
            status_class = 'success'

        field_stats.append(
            {
                'name': field_name,
                'verbose_name': attr.description or field_name,
                'missing_rate': missing_rate,
                'completeness': completeness,
                'missing_count': missing,
                'status_class': status_class,
                'variance': attr.variance,
                'unit': attr.unit,
            }
        )

    field_stats.sort(key=lambda x: x['missing_rate'], reverse=True)
    return field_stats
