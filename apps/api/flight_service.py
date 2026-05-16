from apps.core.models import QAR, QAR_Parameter_Attribute
from apps.core.parameter_metadata import PARAMETER_UNIT_MAP


DOWNSAMPLE_INTERVAL = 10


def safe_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def downsample_with_fixed_interval(values, interval=DOWNSAMPLE_INTERVAL):
    if not values:
        return []
    try:
        step = int(interval)
    except (TypeError, ValueError):
        step = 1
    step = max(1, step)
    if step == 1:
        return values

    return values[::step]


def downsample_series(values, max_points):
    if not values:
        return []

    # 先按固定间隔 10 下采样，再按 max_points 做二次压缩。
    values = downsample_with_fixed_interval(values)
    if len(values) <= max_points:
        return values

    step = max(1, len(values) // max_points)
    sampled = values[::step]
    if sampled[-1] != values[-1]:
        sampled.append(values[-1])
    return sampled


def build_chart_payload(rows, max_points, series_fields=None):
    time_label = [safe_float(r.get('dSimTime')) for r in rows]
    payload = {
        'time_label': downsample_series(time_label, max_points),
    }

    series_fields = list(series_fields or [])
    for field in series_fields:
        payload[field] = downsample_series([safe_float(r.get(field)) for r in rows], max_points)

    # Keep legacy aliases for existing UI cards and backward compatibility.
    alias_map = {
        'altitude_line': 'dASL',
        'speed_line': 'dTAS',
        'vertical_speed_line': 'dWkg',
        'roll_angle_line': 'dPhi',
        'pitch_angle_line': 'dTheta',
    }
    for alias, source_field in alias_map.items():
        if alias in payload:
            continue
        payload[alias] = downsample_series([safe_float(r.get(source_field)) for r in rows], max_points)

    return payload


def build_trajectory_payload(rows, max_points):
    if not rows:
        return []

    sampled_rows = downsample_with_fixed_interval(rows)
    if len(sampled_rows) > max_points:
        sampled_rows = sampled_rows[::max(1, len(sampled_rows) // max_points)]
    if sampled_rows[-1] != rows[-1]:
        sampled_rows.append(rows[-1])

    payload = []
    for row in sampled_rows:
        payload.append({
            't': safe_float(row.get('dSimTime')),
            'lon': safe_float(row.get('dLongitude')),
            'lat': safe_float(row.get('dLatitude')),
            'asl': safe_float(row.get('dASL')),
        })
    return payload


def build_replay_payload(rows, max_points):
    if not rows:
        return []

    sampled_rows = downsample_with_fixed_interval(rows)
    if len(sampled_rows) > max_points:
        sampled_rows = sampled_rows[::max(1, len(sampled_rows) // max_points)]
    if sampled_rows[-1] != rows[-1]:
        sampled_rows.append(rows[-1])

    payload = []
    for row in sampled_rows:
        payload.append(
            {
                't': safe_float(row.get('dSimTime')),
                'lon': safe_float(row.get('dLongitude')),
                'lat': safe_float(row.get('dLatitude')),
                'asl': safe_float(row.get('dASL')),
                'tas': safe_float(row.get('dTAS')),
                'heading': safe_float(row.get('dTrueHeading')),
                'roll': safe_float(row.get('dPhi')),
                'pitch': safe_float(row.get('dTheta')),
            }
        )
    return payload


def build_stats(rows):
    if not rows:
        return {
            'duration': 0,
            'fuel_consumed': 0,
            'max_altitude': 0,
            'min_altitude': 0,
            'avg_altitude': 0,
            'max_speed': 0,
            'min_speed': 0,
            'avg_speed': 0,
            'max_vertical_speed': 0,
            'min_vertical_speed': 0,
            'avg_vertical_speed': 0,
            'max_mach': 0,
            'min_mach': 0,
            'avg_mach': 0,
            'max_roll_angle': 0,
            'min_roll_angle': 0,
            'avg_roll_angle': 0,
            'max_pitch_angle': 0,
            'min_pitch_angle': 0,
            'avg_pitch_angle': 0,
            'max_climb_rate': 0,
            'max_descent_rate': 0,
            'max_g_force': 0,
            'min_g_force': 0,
        }

    def col(name):
        return [safe_float(r[name]) for r in rows if r.get(name) is not None]

    def avg(values):
        return sum(values) / len(values) if values else 0.0

    sim_time = col('dSimTime')
    fuel = col('gfuel')
    asl = col('dASL')
    tas = col('dTAS')
    wkg = col('dWkg')
    mach = col('dMach')
    phi = col('dPhi')
    theta = col('dTheta')
    gamma = col('dGamma')
    nx = col('dNx')
    ny = col('dNy')
    nz = col('dNz')

    max_g_candidates = []
    min_g_candidates = []
    for series in [nx, ny, nz]:
        if series:
            max_g_candidates.append(max(series))
            min_g_candidates.append(min(series))

    return {
        'duration': round((max(sim_time) - min(sim_time)) if sim_time else 0, 2),
        'fuel_consumed': round((fuel[0] - fuel[-1]) if len(fuel) >= 2 else 0, 2),
        'max_altitude': round(max(asl) if asl else 0, 2),
        'min_altitude': round(min(asl) if asl else 0, 2),
        'avg_altitude': round(avg(asl), 2),
        'max_speed': round(max(tas) if tas else 0, 2),
        'min_speed': round(min(tas) if tas else 0, 2),
        'avg_speed': round(avg(tas), 2),
        'max_vertical_speed': round(max(wkg) if wkg else 0, 2),
        'min_vertical_speed': round(min(wkg) if wkg else 0, 2),
        'avg_vertical_speed': round(avg(wkg), 2),
        'max_mach': round(max(mach) if mach else 0, 2),
        'min_mach': round(min(mach) if mach else 0, 2),
        'avg_mach': round(avg(mach), 2),
        'max_roll_angle': round(max(phi) if phi else 0, 2),
        'min_roll_angle': round(min(phi) if phi else 0, 2),
        'avg_roll_angle': round(avg(phi), 2),
        'max_pitch_angle': round(max(theta) if theta else 0, 2),
        'min_pitch_angle': round(min(theta) if theta else 0, 2),
        'avg_pitch_angle': round(avg(theta), 2),
        'max_climb_rate': round(max(gamma) if gamma else 0, 2),
        'max_descent_rate': round(min(gamma) if gamma else 0, 2),
        'max_g_force': round(max(max_g_candidates) if max_g_candidates else 0, 2),
        'min_g_force': round(min(min_g_candidates) if min_g_candidates else 0, 2),
    }


def get_default_qar_id():
    return QAR.objects.values_list('qar_id', flat=True).order_by('qar_id').first()


def get_available_qar_ids(limit=200):
    return list(
        QAR.objects.exclude(qar_id__isnull=True)
        .exclude(qar_id='')
        .values_list('qar_id', flat=True)
        .distinct()
        .order_by('qar_id')[:limit]
    )


def get_threshold_items(monitored_only=False):
    queryset = QAR_Parameter_Attribute.objects.all().order_by('parameter_name')
    if monitored_only:
        queryset = queryset.filter(is_monitored=True)
    rows = list(
        queryset.values(
            'parameter_name',
            'description',
            'unit',
            'is_monitored',
            'warning_lower',
            'warning_upper',
            'critical_lower',
            'critical_upper',

            'normalized_variance',
        )
    )

    for row in rows:
        row['unit'] = row.get('unit') or PARAMETER_UNIT_MAP.get(row.get('parameter_name'), '')
        for key in ('warning_lower', 'warning_upper', 'critical_lower', 'critical_upper'):
            value = row.get(key)
            if value is not None:
                row[key] = round(float(value), 2)

    return rows
