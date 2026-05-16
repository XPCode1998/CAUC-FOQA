from django.db import models
import logging
import random

import numpy as np

from .models import QAR, QAR_Parameter_Attribute
from .monitoring_policy import MONITORED_PARAMETER_SET, apply_monitoring_policy
from .parameter_metadata import PARAMETER_UNIT_MAP

logger = logging.getLogger(__name__)

RESERVOIR_SIZE = 200000
ITERATOR_CHUNK_SIZE = 5000

# 阈值策略：总超限 5%，其中严重超限 2%，普通超限 3%。
# 采用双侧分位：
# - 严重阈值：1% / 99%（合计 2%）
# - 警告阈值：2.5% / 97.5%（合计 5%）
# 这样普通超限约为 5% - 2% = 3%。
CRITICAL_LOWER_PERCENTILE = 1.0
CRITICAL_UPPER_PERCENTILE = 99.0
WARNING_LOWER_PERCENTILE = 2.5
WARNING_UPPER_PERCENTILE = 97.5

# @receiver(post_save, sender=QAR)
# @receiver(post_delete, sender=QAR)
def update_qar_parameter_stats(sender, instance=None, **kwargs):
    """
    在QAR模型保存或删除后更新QAR_Parameter_Attribute中的统计信息
    自动设置阈值：严重超限约2%，普通超限约3%。
    """
    try:
        # 获取所有数值型字段
        numeric_fields = [
            field for field in QAR._meta.get_fields()
            if isinstance(field, (models.FloatField, models.IntegerField))
            and field.name in QAR.get_fields()
        ]

        if not numeric_fields:
            logger.info("QAR模型中没有找到数值型字段")
            return

        for field in numeric_fields:
            field_name = field.name

            # Streaming stats (Welford) + reservoir sample for percentile estimation.
            count = 0
            mean = 0.0
            m2 = 0.0
            min_val = None
            max_val = None
            reservoir = []

            queryset = QAR.objects.filter(**{f"{field_name}__isnull": False}).values_list(field_name, flat=True)
            for raw_value in queryset.iterator(chunk_size=ITERATOR_CHUNK_SIZE):
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue

                count += 1

                if min_val is None or value < min_val:
                    min_val = value
                if max_val is None or value > max_val:
                    max_val = value

                delta = value - mean
                mean += delta / count
                delta2 = value - mean
                m2 += delta * delta2

                if len(reservoir) < RESERVOIR_SIZE:
                    reservoir.append(value)
                else:
                    j = random.randint(1, count)
                    if j <= RESERVOIR_SIZE:
                        reservoir[j - 1] = value

            if count <= 0:
                QAR_Parameter_Attribute.objects.update_or_create(
                    parameter_name=field_name,
                    defaults={
                        'description': field.verbose_name,
                        'unit': PARAMETER_UNIT_MAP.get(field_name, ''),
                        'is_monitored': field_name in MONITORED_PARAMETER_SET,
                    }
                )
                logger.debug(f"字段 {field_name} 没有有效数据，已同步参数元数据")
                continue

            var_val = (m2 / count) if count > 0 else 0.0
            sample = np.asarray(reservoir, dtype=np.float64)
            stats = {
                'min_val': float(min_val),
                'max_val': float(max_val),
                'mean_val': float(mean),
                'var_val': float(var_val),
                'warning_lower': round(float(np.percentile(sample, WARNING_LOWER_PERCENTILE)), 2),
                'warning_upper': round(float(np.percentile(sample, WARNING_UPPER_PERCENTILE)), 2),
                'critical_lower': round(float(np.percentile(sample, CRITICAL_LOWER_PERCENTILE)), 2),
                'critical_upper': round(float(np.percentile(sample, CRITICAL_UPPER_PERCENTILE)), 2),
            }

            normalized_var = stats['var_val'] / stats['mean_val'] if stats['mean_val'] != 0 else 0
            QAR_Parameter_Attribute.objects.update_or_create(
                parameter_name=field_name,
                defaults={
                    'description': field.verbose_name,
                    'unit': PARAMETER_UNIT_MAP.get(field_name, ''),
                    'min_value': stats['min_val'],
                    'max_value': stats['max_val'],
                    'mean': stats['mean_val'],
                    'variance': stats['var_val'],
                    'normalized_variance': normalized_var,
                    'warning_lower': stats['warning_lower'],
                    'warning_upper': stats['warning_upper'],
                    'critical_lower': stats['critical_lower'],
                    'critical_upper': stats['critical_upper'],
                    'is_monitored': field_name in MONITORED_PARAMETER_SET,
                }
            )

            logger.info(f"成功更新字段 {field_name} 的统计信息和阈值设置")

        apply_monitoring_policy()
                
    except Exception as e:
        logger.error(f"更新QAR参数统计信息时出错: {str(e)}", exc_info=True)
        # 在实际应用中，可能需要添加错误通知机制