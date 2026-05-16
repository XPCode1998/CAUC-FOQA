import pandas as pd
import numpy as np

from apps.core.mask_codec import get_mask_index_map
from apps.core.models import QAR
from apps.core.models import QAR_Mask


IMPUTATION_DOWNSAMPLE_INTERVAL = 10


def _downsample_rows_by_interval(rows, interval=IMPUTATION_DOWNSAMPLE_INTERVAL):
    if not rows:
        return []
    try:
        step = int(interval)
    except (TypeError, ValueError):
        step = 1
    step = max(1, step)
    # Fixed-interval sampling only: 1st, 11th, 21st... (do not append tail row).
    return rows[::step]


def _normalize_mask_values(mask_value):
    if mask_value is None:
        return []
    if isinstance(mask_value, list):
        return mask_value
    if isinstance(mask_value, tuple):
        return list(mask_value)
    if isinstance(mask_value, str):
        # Support compact bit-string persisted in historical data, e.g. "101001...".
        return list(mask_value.strip())
    return []


def _is_observed_mask_bit(value):
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


def _df_to_rows(df):
    if df.empty:
        return []

    def _sanitize_cell(value):
        if value is None:
            return None

        # pd.NA / NaN / NaT -> None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        if isinstance(value, (float, np.floating)):
            return float(value) if np.isfinite(value) else None

        if isinstance(value, np.integer):
            return int(value)

        return value

    rows = df.to_dict(orient='records')
    sanitized_rows = []
    for row in rows:
        sanitized_row = {k: _sanitize_cell(v) for k, v in row.items()}
        sanitized_rows.append(sanitized_row)
    return sanitized_rows


def get_imputation_page(qar_id, page, page_size):
    field_names = [field.name for field in QAR._meta.fields]
    raw_rows = list(QAR.objects.filter(qar_id=qar_id).order_by('id').values(*field_names))
    sampled_rows = _downsample_rows_by_interval(raw_rows)

    total = len(sampled_rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = sampled_rows[start:end]
    df = pd.DataFrame(page_rows, columns=field_names)

    return field_names, total, start, end, df


def preview_imputation(qar_id, page, page_size):
    field_names, total, start, end, df = get_imputation_page(qar_id, page, page_size)
    if df.empty:
        return field_names, total, [], [], []

    exclude_fields = {'id', 'qar_id', 'label'}
    index_map = get_mask_index_map()
    target_fields = [name for name in field_names if name not in exclude_fields and name in index_map]
    if not target_fields:
        return field_names, total, _df_to_rows(df), [], []

    sim_times = [item for item in df['dSimTime'].tolist() if item is not None]
    if not sim_times:
        return field_names, total, _df_to_rows(df), [], []

    mask_rows = QAR_Mask.objects.filter(qar_id=qar_id, dSimTime__in=sim_times).values('dSimTime', 'mask_list')
    mask_map = {item.get('dSimTime'): _normalize_mask_values(item.get('mask_list')) for item in mask_rows}

    page_missing_mask = []

    for idx in df.index:
        sim_time = df.at[idx, 'dSimTime']
        row_mask = mask_map.get(sim_time) or []
        row_missing_bits = []

        for field in target_fields:
            mask_idx = index_map[field]
            if row_mask and mask_idx < len(row_mask):
                observed = _is_observed_mask_bit(row_mask[mask_idx])
            else:
                observed = not pd.isna(df.at[idx, field])
            row_missing_bits.append(1 if observed else 0)
            if not observed:
                df.at[idx, field] = None

        page_missing_mask.append(row_missing_bits)

    return field_names, total, _df_to_rows(df), target_fields, page_missing_mask

