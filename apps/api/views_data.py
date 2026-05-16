from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
import logging
import json
import math
from datetime import date, datetime, time
from collections import Counter
import pandas as pd
import numpy as np
import requests
from django.db import models
from django.db import transaction, connection
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.api.utils import ok, fail
from apps.core.models import QAR, QAR_Parameter_Attribute
from apps.core.models import QAR_Overview, QAR_Mask, QAR_PostProcess_Task
from apps.core.mask_codec import build_mask_list_from_instance, get_mask_fields, get_mask_index_map
from apps.api.imputation_service import preview_imputation
from apps.api.flight_service import get_threshold_items
from apps.core.monitoring_policy import MONITORED_PARAMETER_SET, apply_monitoring_policy
from apps.api.summary_service import rebuild_all_qar_summaries, rebuild_qar_summary
from apps.api.upload_async import enqueue_qar_post_process, enqueue_qar_delete_post_process


logger = logging.getLogger(__name__)

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


def _bulk_insert_qar_rows(rows, columns, chunk_size=1000):
    """Use multi-values SQL insert for high-throughput QAR writes.

    Returns: (inserted_rows, min_insert_id, max_insert_id)
    """
    if not rows or not columns:
        return 0, None, None

    table_name = connection.ops.quote_name(QAR._meta.db_table)
    quoted_columns = ', '.join(connection.ops.quote_name(col) for col in columns)
    row_placeholder = f"({', '.join(['%s'] * len(columns))})"

    inserted_rows = 0
    min_insert_id = None
    max_insert_id = None

    with connection.cursor() as cursor:
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            if not chunk:
                continue

            placeholders = ', '.join([row_placeholder] * len(chunk))
            sql = f"INSERT INTO {table_name} ({quoted_columns}) VALUES {placeholders}"

            flat_params = []
            for row in chunk:
                flat_params.extend(row)

            cursor.execute(sql, flat_params)

            inserted_rows += len(chunk)
            first_id = getattr(cursor, 'lastrowid', None)
            if first_id:
                chunk_min_id = int(first_id)
                chunk_max_id = chunk_min_id + len(chunk) - 1
                min_insert_id = chunk_min_id if min_insert_id is None else min(min_insert_id, chunk_min_id)
                max_insert_id = chunk_max_id if max_insert_id is None else max(max_insert_id, chunk_max_id)

    return inserted_rows, min_insert_id, max_insert_id


def _to_json_safe(value):
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_to_json_safe(v) for v in value]

    if value is None:
        return None

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.integer):
        return int(value)

    return value


def _get_ground_truth_rows(qar_id):
    full_field_names = [field.name for field in QAR._meta.fields]
    rows = list(
        QAR.objects.filter(qar_id=qar_id)
        .order_by("dSimTime", "id")
        .values(*full_field_names)
    )
    return _downsample_rows_by_interval(rows)


class DataPreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # 字段级编辑白名单：仅允许业务参数字段编辑，排除 id/qar_id/label/时间字段等元字段。
    EDITABLE_FIELDS = set(QAR.get_fields())

    def get(self, request):
        qar_id = (request.GET.get("qar_id") or "").strip()
        page = max(int(request.GET.get("page", 1)), 1)
        page_size = min(max(int(request.GET.get("page_size", 50)), 1), 500)

        queryset = QAR.objects.all().order_by("id")
        if qar_id:
            queryset = queryset.filter(qar_id=qar_id)

        if qar_id:
            overview_total = (
                QAR_Overview.objects.filter(qar_id=qar_id)
                .values_list("record_count", flat=True)
                .first()
            )
            total = int(overview_total) if overview_total is not None else queryset.count()
        else:
            total = queryset.count()

        start = (page - 1) * page_size
        end = start + page_size

        fields = [field.name for field in QAR._meta.fields]
        rows = list(queryset.values(*fields)[start:end])

        return ok(
            {
                "total": total,
                "page": page,
                "page_size": page_size,
                "fields": fields,
                "readonly_fields": ["id"],
                "editable_fields": sorted(self.EDITABLE_FIELDS),
                "rows": rows,
            }
        )

    def put(self, request):
        row_id = request.data.get("id")
        updates = request.data.get("updates") or {}

        if row_id is None:
            return fail("缺少 id 参数", status_code=400)
        if not isinstance(updates, dict):
            return fail("updates 必须是对象", status_code=400)

        try:
            row_id = int(row_id)
        except (TypeError, ValueError):
            return fail("id 必须是整数", status_code=400)

        try:
            qar_obj = QAR.objects.get(id=row_id)
        except QAR.DoesNotExist:
            return fail("记录不存在", status_code=404)

        editable_field_names = set(self.EDITABLE_FIELDS)

        invalid_fields = [key for key in updates.keys() if key not in editable_field_names]
        if invalid_fields:
            return fail(f"包含不可编辑字段: {', '.join(invalid_fields)}", status_code=400)

        old_qar_id = qar_obj.qar_id
        old_dsim_time = qar_obj.dSimTime
        changed_fields = []

        try:
            with transaction.atomic():
                for field_name, raw_value in updates.items():
                    model_field = QAR._meta.get_field(field_name)
                    cleaned_value = self._coerce_field_value(model_field, raw_value)
                    setattr(qar_obj, field_name, cleaned_value)
                    changed_fields.append(field_name)

                if changed_fields:
                    qar_obj.save(update_fields=changed_fields)

                    # 同步缺失掩码行（紧凑格式：qar_id + dSimTime + mask_list）
                    mask_fields = get_mask_fields()
                    mask_defaults = {
                        "mask_list": build_mask_list_from_instance(qar_obj, mask_fields)
                    }
                    QAR_Mask.objects.update_or_create(
                        qar_id=qar_obj.qar_id,
                        dSimTime=qar_obj.dSimTime,
                        defaults=mask_defaults,
                    )

                    if old_qar_id != qar_obj.qar_id or old_dsim_time != qar_obj.dSimTime:
                        QAR_Mask.objects.filter(qar_id=old_qar_id, dSimTime=old_dsim_time).delete()

            if changed_fields:
                rebuild_qar_summary(old_qar_id)
                if qar_obj.qar_id != old_qar_id:
                    rebuild_qar_summary(qar_obj.qar_id)

            fields = [field.name for field in QAR._meta.fields]
            return ok({"row": QAR.objects.filter(id=qar_obj.id).values(*fields).first()}, message="更新成功")
        except ValueError as exc:
            return fail(str(exc), status_code=400)
        except Exception as exc:
            return fail(f"更新失败: {str(exc)}", status_code=500)

    @staticmethod
    def _coerce_field_value(model_field, raw_value):
        if raw_value == "":
            raw_value = None

        if raw_value is None:
            if getattr(model_field, "null", False):
                return None
            raise ValueError(f"字段 {model_field.name} 不允许为空")

        if isinstance(model_field, models.FloatField):
            try:
                return float(raw_value)
            except (TypeError, ValueError):
                raise ValueError(f"字段 {model_field.name} 需要数字")

        if isinstance(model_field, models.IntegerField):
            try:
                return int(raw_value)
            except (TypeError, ValueError):
                raise ValueError(f"字段 {model_field.name} 需要整数")

        if isinstance(model_field, models.DateTimeField):
            if hasattr(raw_value, "tzinfo"):
                return raw_value
            dt = parse_datetime(str(raw_value))
            if dt is None:
                raise ValueError(f"字段 {model_field.name} 需要日期时间格式")
            return dt

        if isinstance(model_field, models.CharField):
            return str(raw_value).strip()

        return raw_value


class DataQarIdListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        keyword = (request.GET.get("q") or "").strip()
        limit = min(max(int(request.GET.get("limit", 300)), 1), 2000)

        queryset = (
            QAR.objects.exclude(qar_id__isnull=True)
            .exclude(qar_id="")
            .values_list("qar_id", flat=True)
            .distinct()
            .order_by("qar_id")
        )
        if keyword:
            queryset = queryset.filter(qar_id__icontains=keyword)

        ids = list(queryset[:limit])
        return ok({"items": ids, "keyword": keyword, "count": len(ids)})


class DataQarManagementListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        keyword = (request.GET.get('q') or '').strip()
        page = max(int(request.GET.get('page', 1)), 1)
        page_size = min(max(int(request.GET.get('page_size', 20)), 1), 200)

        summary_qs = QAR_Overview.objects.all().order_by('qar_id')
        if keyword:
            summary_qs = summary_qs.filter(qar_id__icontains=keyword)

        total = summary_qs.count()

        if total <= 0 and QAR.objects.exists():
            rebuild_all_qar_summaries()
            summary_qs = QAR_Overview.objects.all().order_by('qar_id')
            if keyword:
                summary_qs = summary_qs.filter(qar_id__icontains=keyword)
            total = summary_qs.count()

        start = (page - 1) * page_size
        end = start + page_size
        items = list(
            summary_qs.values(
                'qar_id',
                'flight_duration',
                'parameter_dimension',
                'exceed_ratio',
                'missing_ratio',
                'risk_label',
                'record_count',
                'created_time',
                'updated_time',
            )[start:end]
        )

        qar_ids = [item.get('qar_id') for item in items if item.get('qar_id')]
        latest_tasks = {}
        if qar_ids:
            task_rows = list(
                QAR_PostProcess_Task.objects.filter(qar_id__in=qar_ids)
                .order_by('qar_id', '-created_time')
                .values('qar_id', 'status', 'attempt_count', 'last_error', 'updated_time')
            )
            for row in task_rows:
                qid = row.get('qar_id')
                if qid not in latest_tasks:
                    latest_tasks[qid] = row

        for item in items:
            task = latest_tasks.get(item.get('qar_id'))
            item['post_process_status'] = task.get('status') if task else 'unknown'
            item['post_process_attempt'] = task.get('attempt_count') if task else 0
            item['post_process_error'] = task.get('last_error') if task else ''
            item['post_process_updated_time'] = task.get('updated_time') if task else None

        return ok(
            {
                'items': items,
                'total': total,
                'page': page,
                'page_size': page_size,
                'keyword': keyword,
            }
        )


class ParameterDimensionConfigAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = list(
            QAR_Parameter_Attribute.objects.all()
            .order_by('parameter_name')
            .values(
                'parameter_name',
                'description',
                'unit',
                'is_monitored',
                'warning_lower',
                'warning_upper',
                'critical_lower',
                'critical_upper',
            )
        )
        return ok({'items': rows})

    def put(self, request):
        items = request.data.get('items') or []
        if not isinstance(items, list):
            return fail('items 必须是数组', status_code=400)

        updated = 0
        for item in items:
            name = (item.get('parameter_name') or '').strip()
            if not name:
                continue

            try:
                param = QAR_Parameter_Attribute.objects.get(parameter_name=name)
            except QAR_Parameter_Attribute.DoesNotExist:
                continue

            param.save()
            updated += 1

        if updated > 0:
            rebuild_all_qar_summaries()

        return ok({'updated': updated}, message='维度保存成功')


class DataUploadRawAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return fail('缺少上传文件 file', status_code=400)

        qar_id = request.data.get('qar_id', '').strip() or f"bench_{int(__import__('time').time() * 1000)}"
        skip_post_process = str(request.data.get('skip_post_process', '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
        try:
            flight_label = int(request.data.get('label', 0))
        except (TypeError, ValueError):
            return fail('label 必须是整数', status_code=400)

        import io
        import time
        import pandas as pd
        from django.db import transaction
        from apps.core.models import QAR

        try:
            uploaded_file.seek(0)
            file_content = uploaded_file.read()
            try:
                content_str = file_content.decode('utf-8')
            except UnicodeDecodeError:
                content_str = file_content.decode('latin1')

            df = pd.read_csv(
                io.StringIO(content_str),
                sep=None,
                engine='python',
                header=0,
                skipinitialspace=True,
                skip_blank_lines=True,
                on_bad_lines='warn'
            )

            # Tolerate UTF-8 BOM and accidental whitespace in CSV headers.
            df.columns = [str(col).replace('\ufeff', '').strip() for col in df.columns]

            if df.empty:
                return fail('上传的文件不包含任何数据', status_code=400)

            model_fields = QAR.get_fields()
            missing_fields = set(model_fields) - set(df.columns)
            if missing_fields:
                return fail(f"缺少必要字段: {', '.join(missing_fields)}", status_code=400)

            columns = ['qar_id', *model_fields]
            rows_to_insert = []
            error_lines = []

            for index, row in enumerate(df.itertuples(index=False), start=2):
                row_values = [qar_id]
                try:
                    for field in model_fields:
                        value = getattr(row, field)
                        if pd.isna(value):
                            row_values.append(None)
                        else:
                            model_field = QAR._meta.get_field(field)
                            if model_field.get_internal_type() in ['FloatField', 'IntegerField']:
                                row_values.append(float(value))
                            else:
                                row_values.append(str(value))
                    rows_to_insert.append(tuple(row_values))
                except Exception as row_error:
                    error_lines.append(f"行 {index}: {str(row_error)}")

            if error_lines:
                return fail('发现以下数据问题:\n' + '\n'.join(error_lines[:10]), status_code=400)

            with transaction.atomic():
                inserted_rows, min_inserted_id, max_inserted_id = _bulk_insert_qar_rows(
                    rows_to_insert,
                    columns,
                    chunk_size=1000,
                )
                now = timezone.now()
                QAR_Overview.objects.update_or_create(
                    qar_id=qar_id,
                    defaults={
                        'label': flight_label,
                        'created_time': now,
                        'updated_time': now,
                    },
                )

            post_process_started = False
            if not skip_post_process:
                post_process_started = enqueue_qar_post_process(
                    qar_id,
                    min_row_id=min_inserted_id,
                    max_row_id=max_inserted_id,
                )

            return ok(
                {
                    'status': 'success',
                    'title': '上传成功',
                    'message': f'成功导入 {inserted_rows} 条记录\nQAR ID: {qar_id}',
                    'qar_id': qar_id,
                    'inserted_rows': inserted_rows,
                    'post_process': {
                        'skip': skip_post_process,
                        'started': post_process_started,
                    },
                },
                message='上传成功，后台已开始异步处理' if not skip_post_process else '分片上传成功，等待合并后处理'
            )
        except Exception as exc:
            return fail(f'上传失败: {str(exc)}', status_code=500)


class DataUploadFinalizeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        qar_id = (request.data.get('qar_id') or '').strip()
        if not qar_id:
            return fail('缺少 qar_id 参数', status_code=400)

        started = enqueue_qar_post_process(qar_id)
        return ok(
            {
                'qar_id': qar_id,
                'post_process_started': started,
            },
            message='已触发后台异步处理' if started else '后台任务已在执行中'
        )


class DataQarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        qar_id = (request.data.get('qar_id') or request.query_params.get('qar_id') or '').strip()
        if not qar_id:
            return fail('缺少 qar_id 参数', status_code=400)

        try:
            from django.db import transaction

            with transaction.atomic():
                qar_queryset = QAR.objects.filter(qar_id=qar_id)
                qar_count = qar_queryset.count()
                if qar_count <= 0:
                    return fail('指定 QAR ID 不存在', status_code=404)

                summary_queryset = QAR_Overview.objects.filter(qar_id=qar_id)
                summary_count = summary_queryset.count()

                mask_queryset = QAR_Mask.objects.filter(qar_id=qar_id)
                mask_count = mask_queryset.count()

                deleted_qars, _ = qar_queryset.delete()
                deleted_summaries, _ = summary_queryset.delete()
                deleted_masks, _ = mask_queryset.delete()

            post_process_started = enqueue_qar_delete_post_process(qar_id)

            return ok(
                {
                    'qar_id': qar_id,
                    'deleted_rows': deleted_qars,
                    'deleted_summaries': deleted_summaries,
                    'deleted_masks': deleted_masks,
                    'planned_deleted': {
                        'qar_rows': qar_count,
                        'summary_rows': summary_count,
                        'mask_rows': mask_count,
                    },
                    'related_cleanup': ['QAR_Overview', 'QAR_Mask'],
                    'stats_refreshed': False,
                    'post_process_async': {
                        'started': post_process_started,
                    },
                },
                message='删除成功，统计信息将由后台异步刷新',
            )
        except Exception as exc:
            return fail(f'删除失败: {str(exc)}', status_code=500)


class ThresholdListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        apply_monitoring_policy()
        monitored_only = request.GET.get("monitored_only") in ["1", "true", "True"]
        rows = get_threshold_items(monitored_only=monitored_only)
        return ok({"items": rows})

    def put(self, request):
        items = request.data.get("items") or []
        if not isinstance(items, list):
            return fail("items 必须是数组", status_code=400)

        updated = 0
        for item in items:
            name = (item.get("parameter_name") or "").strip()
            if not name:
                continue

            try:
                param = QAR_Parameter_Attribute.objects.get(parameter_name=name)
            except QAR_Parameter_Attribute.DoesNotExist:
                continue

            for field in ["warning_lower", "warning_upper", "critical_lower", "critical_upper"]:
                value = item.get(field, None)
                if value in ["", None]:
                    setattr(param, field, None)
                else:
                    try:
                        setattr(param, field, round(float(value), 2))
                    except (TypeError, ValueError):
                        return fail(f"{name} 的 {field} 不是有效数字", status_code=400)

            if "is_monitored" in item:
                param.is_monitored = bool(item.get("is_monitored")) and (name in MONITORED_PARAMETER_SET)

            if not param.is_monitored:
                param.warning_lower = None
                param.warning_upper = None
                param.critical_lower = None
                param.critical_upper = None

            param.save()
            updated += 1

        return ok({"updated": updated}, message="阈值保存成功")


def _df_to_rows(df):
    if df.empty:
        return []
    converted = df.where(pd.notnull(df), None)
    return converted.to_dict(orient="records")


def _get_imputation_page(qar_id, page, page_size):
    field_names = [field.name for field in QAR._meta.fields]
    queryset = QAR.objects.filter(qar_id=qar_id).order_by("id").values(*field_names)
    total = queryset.count()

    start = (page - 1) * page_size
    end = start + page_size
    page_rows = list(queryset[start:end])
    df = pd.DataFrame(page_rows, columns=field_names)

    return field_names, total, start, end, df


class DataImputationPreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qar_id = (request.GET.get("qar_id") or "").strip()
        if not qar_id:
            qar_id = QAR.objects.values_list("qar_id", flat=True).order_by("qar_id").first() or ""
        if not qar_id:
            return fail("暂无可用 QAR 数据", status_code=404)

        page = max(int(request.GET.get("page", 1)), 1)
        page_size = min(max(int(request.GET.get("page_size", 150)), 1), 500)

        try:
            field_names, total, rows, mask_columns, missing_mask = preview_imputation(qar_id, page, page_size)
            payload = {
                "qar_id": qar_id,
                "page": page,
                "page_size": page_size,
                "total": total,
                "fields": field_names,
                "rows": rows,
                "mask_columns": mask_columns,
                "missing_mask": missing_mask,
            }
            return ok(_to_json_safe(payload))
        except Exception as exc:
            return fail(str(exc), status_code=400)


class DataImputationRepairAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        qar_id = (request.data.get("qar_id") or "").strip()
        if not qar_id:
            return fail("缺少 qar_id 参数", status_code=400)

        page = max(int(request.data.get("page", 1)), 1)
        page_size = min(max(int(request.data.get("page_size", 150)), 1), 500)
        model_name = str(request.data.get("model_name") or DEFAULT_IMPUTATION_MODEL)
        diff_steps = int(request.data.get("diff_steps", 30) or 30)
        max_rows_per_event = int(request.data.get("max_rows_per_event", 200) or 200)
        mask_missing_value = int(request.data.get("mask_missing_value", 0) or 0)
        model_path = (request.data.get("model_path") or "").strip() or None

        try:
            mask_columns_override = _parse_mask_columns_value(request.data.get("mask_columns"))
        except ValueError as exc:
            return fail(str(exc), status_code=400)

        try:
            repaired_rows = _repair_imputation_via_upstream(
                qar_id,
                model_name=model_name,
                diff_steps=diff_steps,
                max_rows_per_event=max_rows_per_event,
                mask_missing_value=mask_missing_value,
                model_path=model_path,
                mask_columns_override=mask_columns_override,
            )
            total = len(repaired_rows)
            start = (page - 1) * page_size
            end = start + page_size
            rows = repaired_rows[start:end]
            field_names = list(rows[0].keys()) if rows else [field.name for field in QAR._meta.fields]
            payload = {
                "qar_id": qar_id,
                "page": page,
                "page_size": page_size,
                "total": total,
                "fields": field_names,
                "rows": rows,
            }
            return ok(_to_json_safe(payload), message='插补完成')
        except Exception as exc:
            return fail(str(exc), status_code=400)


class DataImputationTrainAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        upstream_url = getattr(
            settings,
            "IMPUTATION_TRAIN_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/train",
        )

        payload = request.data if isinstance(request.data, dict) else {}

        try:
            upstream = requests.post(
                upstream_url,
                json=payload,
                timeout=(10, 7200),
            )
        except requests.RequestException as exc:
            return fail(f"上游训练服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                detail = upstream.json()
                if not isinstance(detail, dict):
                    detail = {"detail": detail}
            except Exception:
                detail = {"detail": upstream.text}
            return JsonResponse(detail, status=upstream.status_code)

        try:
            data = upstream.json()
        except Exception:
            return fail("上游训练服务返回非 JSON 数据", status_code=502)

        return ok(data, message="训练任务已执行")


class DataImputationTrainHyperparamsProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        upstream_url = getattr(
            settings,
            "IMPUTATION_TRAIN_HYPERPARAMS_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/train/hyperparams",
        )

        try:
            upstream = requests.get(upstream_url, timeout=(10, 30))
        except requests.RequestException as exc:
            return fail(f"上游训练配置服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                detail = upstream.json()
                if not isinstance(detail, dict):
                    detail = {"detail": detail}
            except Exception:
                detail = {"detail": upstream.text}
            return JsonResponse(detail, status=upstream.status_code)

        try:
            data = upstream.json()
        except Exception:
            return fail("上游训练配置服务返回非 JSON 数据", status_code=502)

        return ok(data, message="已获取训练默认参数")


class DataImputationModelsProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        upstream_url = getattr(
            settings,
            "IMPUTATION_MODELS_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/models",
        )

        model_name = (request.GET.get("model_name") or "").strip()
        params = {"model_name": model_name} if model_name else None

        try:
            upstream = requests.get(upstream_url, params=params, timeout=(10, 30))
        except requests.RequestException as exc:
            return fail(f"上游模型列表服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                detail = upstream.json()
                if not isinstance(detail, dict):
                    detail = {"detail": detail}
            except Exception:
                detail = {"detail": upstream.text}
            return JsonResponse(detail, status=upstream.status_code)

        try:
            data = upstream.json()
        except Exception:
            return fail("上游模型列表服务返回非 JSON 数据", status_code=502)

        return ok(data, message="已获取可用模型列表")


class DataImputationModelsProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        upstream_url = getattr(
            settings,
            "IMPUTATION_MODELS_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/models",
        )

        model_name = (request.GET.get("model_name") or "").strip()
        params = {"model_name": model_name} if model_name else None

        try:
            upstream = requests.get(upstream_url, params=params, timeout=(10, 30))
        except requests.RequestException as exc:
            return fail(f"上游模型列表服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                detail = upstream.json()
                if not isinstance(detail, dict):
                    detail = {"detail": detail}
            except Exception:
                detail = {"detail": upstream.text}
            return JsonResponse(detail, status=upstream.status_code)

        try:
            data = upstream.json()
        except Exception:
            return fail("上游模型列表服务返回非 JSON 数据", status_code=502)

        return ok(data, message="已获取可用模型列表")


LGTDM_INPUT_FIELDS = [
    "dAlpha", "dBeta", "dBetaRad", "dSinBeta", "dPhi", "dGroundspeed",
    "dTAS", "dPd", "dPs", "dUk", "dWk", "dVkDot",
    "dU", "dV", "dP", "dQ", "dPDot", "dQDot",
    "dUkgDot", "dVkgDot", "dUkg", "dWkg", "dASL", "dAGL",
    "dPosXg", "dtx", "dty", "dtz", "gfuel", "pe_t1",
    "pe_t2", "rot1", "rot2", "gfused", "dGfNormal", "dGFuel",
]

SUPPORTED_IMPUTATION_MODELS = {"LGTDM", "LGTDM-V1"}
DEFAULT_IMPUTATION_MODEL = "LGTDM-V1"
LGTDM_V1_REQUIRED_ROWS = 150
LGTDM_V1_REQUIRED_DIM = 36
# LGTDM-V1 采用固定 profile；此处固定 36 维特征顺序。
LGTDM_V1_INPUT_FIELDS = LGTDM_INPUT_FIELDS


def _build_field_normalization_specs(fields):
    if not fields:
        return {}

    attr_rows = list(
        QAR_Parameter_Attribute.objects.filter(parameter_name__in=fields).values(
            "parameter_name",
            "mean",
            "variance",
            "min_value",
            "max_value",
        )
    )
    attr_map = {item.get("parameter_name"): item for item in attr_rows}

    specs = {}
    for field in fields:
        attrs = attr_map.get(field) or {}
        mean_value = attrs.get("mean")
        variance = attrs.get("variance")
        min_value = attrs.get("min_value")
        max_value = attrs.get("max_value")

        try:
            mean_value = float(mean_value) if mean_value is not None else None
        except (TypeError, ValueError):
            mean_value = None

        try:
            variance = float(variance) if variance is not None else None
        except (TypeError, ValueError):
            variance = None

        try:
            min_value = float(min_value) if min_value is not None else None
        except (TypeError, ValueError):
            min_value = None

        try:
            max_value = float(max_value) if max_value is not None else None
        except (TypeError, ValueError):
            max_value = None

        if variance is not None and variance > 1e-12 and mean_value is not None:
            specs[field] = {
                "mode": "zscore",
                "mean": mean_value,
                "std": math.sqrt(variance),
            }
            continue

        if min_value is not None and max_value is not None and abs(max_value - min_value) > 1e-12:
            specs[field] = {
                "mode": "minmax",
                "min": min_value,
                "max": max_value,
            }

    return specs


def _normalize_value_with_spec(value, spec):
    if value is None or not spec:
        return value

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value

    mode = spec.get("mode")
    if mode == "zscore":
        std = float(spec.get("std") or 0)
        if std <= 1e-12:
            return numeric
        mean = float(spec.get("mean") or 0)
        return (numeric - mean) / std

    if mode == "minmax":
        lower = float(spec.get("min") or 0)
        upper = float(spec.get("max") or 0)
        span = upper - lower
        if abs(span) <= 1e-12:
            return numeric
        return (numeric - lower) / span

    return numeric


def _denormalize_value_with_spec(value, spec):
    if value is None or not spec:
        return value

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value

    mode = spec.get("mode")
    if mode == "zscore":
        std = float(spec.get("std") or 0)
        mean = float(spec.get("mean") or 0)
        if std <= 1e-12:
            return numeric
        return numeric * std + mean

    if mode == "minmax":
        lower = float(spec.get("min") or 0)
        upper = float(spec.get("max") or 0)
        span = upper - lower
        if abs(span) <= 1e-12:
            return numeric
        return numeric * span + lower

    return numeric


def _apply_normalization_to_rows(rows, missing_mask, mask_columns, normalization_specs):
    if not rows or not mask_columns or not normalization_specs:
        return

    is_batched = bool(rows and isinstance(rows[0], list))
    if is_batched:
        for batch_idx, batch_rows in enumerate(rows):
            batch_masks = missing_mask[batch_idx] if batch_idx < len(missing_mask) and isinstance(missing_mask[batch_idx], list) else []
            for row_idx, row in enumerate(batch_rows):
                if not isinstance(row, dict):
                    continue
                row_mask = batch_masks[row_idx] if row_idx < len(batch_masks) and isinstance(batch_masks[row_idx], list) else []
                for col_idx, field in enumerate(mask_columns):
                    spec = normalization_specs.get(field)
                    if not spec:
                        continue
                    if col_idx < len(row_mask) and row_mask[col_idx] == 0:
                        # 保持缺失位为 0，占位值不参与归一化。
                        row[field] = 0.0
                        continue
                    row[field] = _normalize_value_with_spec(row.get(field), spec)
        return

    for row_idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_mask = missing_mask[row_idx] if row_idx < len(missing_mask) and isinstance(missing_mask[row_idx], list) else []
        for col_idx, field in enumerate(mask_columns):
            spec = normalization_specs.get(field)
            if not spec:
                continue
            if col_idx < len(row_mask) and row_mask[col_idx] == 0:
                row[field] = 0.0
                continue
            row[field] = _normalize_value_with_spec(row.get(field), spec)


def _build_runtime_normalization_specs(rows, missing_mask, mask_columns, fallback_specs=None):
    if not rows or not mask_columns:
        return dict(fallback_specs or {})

    runtime_values = {field: [] for field in mask_columns}
    is_batched = bool(rows and isinstance(rows[0], list))

    if is_batched:
        for batch_idx, batch_rows in enumerate(rows):
            batch_masks = missing_mask[batch_idx] if batch_idx < len(missing_mask) and isinstance(missing_mask[batch_idx], list) else []
            for row_idx, row in enumerate(batch_rows):
                if not isinstance(row, dict):
                    continue
                row_mask = batch_masks[row_idx] if row_idx < len(batch_masks) and isinstance(batch_masks[row_idx], list) else []
                for col_idx, field in enumerate(mask_columns):
                    if col_idx < len(row_mask) and row_mask[col_idx] == 0:
                        continue
                    value = row.get(field)
                    try:
                        numeric = float(value)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(numeric):
                        runtime_values[field].append(numeric)
    else:
        for row_idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            row_mask = missing_mask[row_idx] if row_idx < len(missing_mask) and isinstance(missing_mask[row_idx], list) else []
            for col_idx, field in enumerate(mask_columns):
                if col_idx < len(row_mask) and row_mask[col_idx] == 0:
                    continue
                value = row.get(field)
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(numeric):
                    runtime_values[field].append(numeric)

    specs = {}
    fallback = fallback_specs or {}
    for field in mask_columns:
        values = runtime_values.get(field) or []
        if len(values) >= 2:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = math.sqrt(variance)
            if std > 1e-12:
                specs[field] = {
                    "mode": "zscore",
                    "mean": mean,
                    "std": std,
                }
                continue

            lower = min(values)
            upper = max(values)
            if abs(upper - lower) > 1e-12:
                specs[field] = {
                    "mode": "minmax",
                    "min": lower,
                    "max": upper,
                }
                continue

        if field in fallback:
            specs[field] = fallback[field]

    return specs


def _denormalize_row_patch_inplace(row, normalization_specs):
    if not isinstance(row, dict) or not normalization_specs:
        return row

    for field, spec in normalization_specs.items():
        if field not in row:
            continue
        row[field] = _denormalize_value_with_spec(row.get(field), spec)
    return row


def _parse_mask_columns_value(raw_value):
    if raw_value is None:
        return None

    items = None
    if isinstance(raw_value, (list, tuple)):
        items = list(raw_value)
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except Exception as exc:
                raise ValueError(f"mask_columns JSON 解析失败: {exc}")
            if not isinstance(parsed, list):
                raise ValueError("mask_columns 必须是字符串数组")
            items = parsed
        else:
            items = [part.strip() for part in text.split(",")]
    else:
        raise ValueError("mask_columns 参数类型不支持")

    cleaned = []
    seen = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        cleaned.append(value)
        seen.add(value)

    return cleaned or None


def _resolve_qar_level_label(qar_id):
    raw_label = QAR_Overview.objects.filter(qar_id=qar_id).values_list("label", flat=True).first()
    try:
        label = int(raw_label)
    except (TypeError, ValueError):
        return None
    if 0 <= label <= 4:
        return label
    return None


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


def _build_qar_rows_and_missing_mask(qar_id, model_name=DEFAULT_IMPUTATION_MODEL, mask_columns_override=None):
    model_name = str(model_name or DEFAULT_IMPUTATION_MODEL).strip() or DEFAULT_IMPUTATION_MODEL
    if model_name not in SUPPORTED_IMPUTATION_MODELS:
        raise ValueError(f"model_name 不支持: {model_name}，仅支持 LGTDM / LGTDM-V1")

    available_fields = set(QAR.get_fields())
    if mask_columns_override:
        mask_columns = [field for field in mask_columns_override if field in available_fields]
    elif model_name == "LGTDM-V1":
        mask_columns = [field for field in LGTDM_V1_INPUT_FIELDS if field in available_fields]
    else:
        mask_columns = [field for field in LGTDM_INPUT_FIELDS if field in available_fields]

    if not mask_columns:
        raise ValueError("未匹配到可用于插补的特征列")

    if model_name == "LGTDM-V1" and len(mask_columns) != LGTDM_V1_REQUIRED_DIM:
        raise ValueError(
            f"LGTDM-V1 需要 {LGTDM_V1_REQUIRED_DIM} 维特征，当前为 {len(mask_columns)} 维"
        )

    # 约定：
    # - missing_mask: 缺失位=0，观测位=1
    # - rows: 缺失位的数值先填 0.0，再交由 missing_mask 指示缺失语义
    # 这样可以和 LGTDM 服务端的 mask_missing_value=0 约定保持一致。

    query_fields = ["id", "dSimTime", *mask_columns]
    if "label" in available_fields:
        query_fields.append("label")

    raw_rows = list(
        QAR.objects.filter(qar_id=qar_id)
        .order_by("dSimTime", "id")
        .values(*query_fields)
    )
    sampled_raw_rows = _downsample_rows_by_interval(raw_rows)

    rows = []
    for row in sampled_raw_rows:
        copied = dict(row)
        copied.pop("id", None)
        copied.pop("dSimTime", None)
        rows.append(copied)
    if not rows:
        return [], mask_columns, []

    if model_name == "LGTDM-V1":
        if len(rows) < LGTDM_V1_REQUIRED_ROWS:
            raise ValueError(f"LGTDM-V1 需要至少 {LGTDM_V1_REQUIRED_ROWS} 行输入，当前仅 {len(rows)} 行")
        if len(rows) % LGTDM_V1_REQUIRED_ROWS != 0:
            raise ValueError(
                f"LGTDM-V1 需要行数为 {LGTDM_V1_REQUIRED_ROWS} 的整数倍，以构造 [N, {LGTDM_V1_REQUIRED_ROWS}, {LGTDM_V1_REQUIRED_DIM}]，当前为 {len(rows)} 行"
            )

        qar_level_label = _resolve_qar_level_label(qar_id)
        if qar_level_label is None:
            raise ValueError(f"LGTDM-V1 要求 label 在 [0,4]，但 qar_id={qar_id} 未找到有效标签")
        for row in rows:
            row["label"] = qar_level_label

    raw_mask_rows = list(
        QAR_Mask.objects.filter(qar_id=qar_id)
        .order_by("dSimTime", "id")
        .values("dSimTime", "mask_list")
    )
    sampled_mask_rows = _downsample_rows_by_interval(raw_mask_rows)
    mask_rows_by_time = {
        item.get("dSimTime"): (item.get("mask_list") or [])
        for item in sampled_mask_rows
    }
    mask_index_map = get_mask_index_map()

    missing_mask = []
    for row_idx, row in enumerate(rows):
        row_mask = []
        sim_time = sampled_raw_rows[row_idx].get("dSimTime") if row_idx < len(sampled_raw_rows) else None
        mask_row = mask_rows_by_time.get(sim_time, []) if sim_time is not None else []

        for field in mask_columns:
            raw_value = row.get(field)

            mask_idx = mask_index_map.get(field)
            if mask_idx is not None and mask_idx < len(mask_row):
                # QAR_Mask 中 1 表示观测到，0 表示缺失。
                is_missing = not _is_observed_mask_bit(mask_row[mask_idx])
            else:
                # 当掩码行不足或字段不存在时，回退到值本身判断。
                is_missing = raw_value is None

            # 掩码语义：缺失=0，观测=1。
            row_mask.append(0 if is_missing else 1)
            if is_missing:
                # 与 LGTDM 服务约定对齐：缺失位的输入值置 0.0，由 missing_mask 显式标识。
                row[field] = 0.0

        missing_mask.append(row_mask)

    if model_name == "LGTDM-V1":
        for idx, row in enumerate(rows):
            label_int = int(row.get("label"))
            if label_int < 0 or label_int > 4:
                raise ValueError(f"LGTDM-V1 要求 label 在 [0,4]，第 {idx + 1} 行为 {label_int}")
            row["label"] = label_int

        if len(mask_columns) != LGTDM_V1_REQUIRED_DIM:
            raise ValueError(f"LGTDM-V1 要求特征维度为 {LGTDM_V1_REQUIRED_DIM}")
        for row_mask in missing_mask:
            if len(row_mask) != LGTDM_V1_REQUIRED_DIM:
                raise ValueError(
                    f"LGTDM-V1 要求 missing_mask 单行维度为 {LGTDM_V1_REQUIRED_DIM}"
                )

        batch_count = len(rows) // LGTDM_V1_REQUIRED_ROWS
        rows = [
            rows[idx * LGTDM_V1_REQUIRED_ROWS:(idx + 1) * LGTDM_V1_REQUIRED_ROWS]
            for idx in range(batch_count)
        ]
        missing_mask = [
            missing_mask[idx * LGTDM_V1_REQUIRED_ROWS:(idx + 1) * LGTDM_V1_REQUIRED_ROWS]
            for idx in range(batch_count)
        ]

    return rows, mask_columns, missing_mask


def _build_repair_json_payload(
    qar_id,
    model_name=DEFAULT_IMPUTATION_MODEL,
    diff_steps=30,
    max_rows_per_event=200,
    mask_missing_value=0,
    model_path=None,
    mask_columns_override=None,
):
    ground_truth_rows = _get_ground_truth_rows(qar_id)
    rows, mask_columns, missing_mask = _build_qar_rows_and_missing_mask(
        qar_id,
        model_name=model_name,
        mask_columns_override=mask_columns_override,
    )
    if not rows:
        raise ValueError("未找到对应 QAR 数据")

    # 归一化与逆归一化都按属性表逐字段展开，避免运行时统计口径不一致。
    normalization_specs = _build_field_normalization_specs(mask_columns)
    _apply_normalization_to_rows(rows, missing_mask, mask_columns, normalization_specs)

    payload = {
        "model_name": model_name,
        "diff_steps": int(diff_steps),
        "max_rows_per_event": int(max_rows_per_event),
        "mask_missing_value": int(mask_missing_value),
        "mask_columns": mask_columns,
        "missing_mask": missing_mask,
        "rows": rows,
    }

    if model_path:
        payload["model_path"] = str(model_path).strip()

    rows_data = payload.get("rows") or []
    mask_data = payload.get("missing_mask") or []
    is_batched = bool(rows_data and isinstance(rows_data[0], list))

    sample_first_row = None
    sample_first_mask = None
    if is_batched:
        first_batch = rows_data[0] if rows_data else []
        if isinstance(first_batch, list) and first_batch:
            sample_first_row = first_batch[0]
        first_mask_batch = mask_data[0] if mask_data and isinstance(mask_data[0], list) else []
        if isinstance(first_mask_batch, list) and first_mask_batch:
            sample_first_mask = first_mask_batch[0]
    elif rows_data:
        sample_first_row = rows_data[0]
        if mask_data:
            sample_first_mask = mask_data[0]

    if is_batched:
        batch_size = len(rows_data[0] or [])
        mask_batch_size = len(mask_data[0] or []) if mask_data else 0
        mask_dim = len((mask_data[0][0] if mask_data and mask_data[0] else []) or [])
        logger.info(
            "imputation repair-json payload built: qar_id=%s model_name=%s model_path=%s rows_shape=%sx%s feature_dim=%s missing_mask_shape=%sx%sx%s",
            qar_id,
            payload.get("model_name"),
            payload.get("model_path", "<auto-select>"),
            len(rows_data),
            batch_size,
            len(payload.get("mask_columns") or []),
            len(mask_data),
            mask_batch_size,
            mask_dim,
        )
    else:
        logger.info(
            "imputation repair-json payload built: qar_id=%s model_name=%s model_path=%s rows=%s feature_dim=%s missing_mask_shape=%sx%s",
            qar_id,
            payload.get("model_name"),
            payload.get("model_path", "<auto-select>"),
            len(rows_data),
            len(payload.get("mask_columns") or []),
            len(mask_data),
            len((mask_data or [[None]])[0] or []),
        )

    return payload, normalization_specs, ground_truth_rows


def _repair_imputation_via_upstream(
    qar_id,
    model_name=DEFAULT_IMPUTATION_MODEL,
    diff_steps=30,
    max_rows_per_event=200,
    mask_missing_value=0,
    model_path=None,
    mask_columns_override=None,
):
    upstream_url = getattr(
        settings,
        "IMPUTATION_REPAIR_STREAM_JSON_UPSTREAM_URL",
        "http://127.0.0.1:8002/api/v1/imputation/stream/repair-json",
    )

    payload, normalization_specs, ground_truth_rows = _build_repair_json_payload(
        qar_id=qar_id,
        model_name=model_name,
        diff_steps=diff_steps,
        max_rows_per_event=max(max_rows_per_event, 1),
        mask_missing_value=mask_missing_value,
        model_path=model_path,
        mask_columns_override=mask_columns_override,
    )

    # 预加载完整行，避免上游仅返回掩码列时把其它列覆盖为 None。
    full_field_names = [field.name for field in QAR._meta.fields]
    full_rows = list(
        QAR.objects.filter(qar_id=qar_id)
        .order_by("dSimTime", "id")
        .values(*full_field_names)
    )
    full_rows = _downsample_rows_by_interval(full_rows)
    ground_truth_rows = ground_truth_rows or full_rows
    updatable_fields = set(payload.get("mask_columns") or LGTDM_INPUT_FIELDS)

    def _normalize_step_rows(value):
        if not isinstance(value, list):
            return []
        if value and isinstance(value[0], list):
            merged = []
            for batch in value:
                if isinstance(batch, list):
                    merged.extend(batch)
            return merged
        return value

    def _merge_rows_to_full_rows(event_payload, cursor):
        raw_rows = event_payload.get("rows")
        if not isinstance(raw_rows, list):
            raw_rows = event_payload.get("final_rows")
        incoming_rows = _normalize_step_rows(raw_rows)
        if not incoming_rows:
            return cursor, []

        start = event_payload.get("row_start")
        try:
            start_index = int(start)
            if start_index < 0 or start_index >= len(full_rows):
                start_index = cursor
        except (TypeError, ValueError):
            start_index = cursor

        if start_index < 0 or start_index >= len(full_rows):
            start_index = 0

        merged_rows = []
        for offset, incoming in enumerate(incoming_rows):
            row_index = start_index + offset
            base_row = {}
            if 0 <= row_index < len(full_rows):
                base_row = dict(full_rows[row_index])

            if isinstance(incoming, dict):
                _denormalize_row_patch_inplace(incoming, normalization_specs)
                for key, value in incoming.items():
                    if key not in updatable_fields:
                        continue
                    # 保护非缺失列：上游补丁中的 None 不覆盖原始观测值。
                    if value is None:
                        continue
                    base_row[key] = value

            if row_index < len(full_rows):
                full_rows[row_index] = base_row
            else:
                full_rows.append(base_row)

            merged_rows.append(base_row)

        return start_index + len(merged_rows), merged_rows

    def _slice_ground_truth_rows(start_index, count):
        if not ground_truth_rows:
            return []
        if start_index < 0:
            start_index = 0
        return [_to_json_safe(row) for row in ground_truth_rows[start_index:start_index + count]]

    def _sample_row_diffs(before_rows, after_rows, start_index, sample_limit=3, field_limit=5):
        if not isinstance(before_rows, list) or not isinstance(after_rows, list):
            return []

        max_rows = min(len(before_rows), len(after_rows))
        samples = []
        for offset in range(max_rows):
            before_row = before_rows[offset]
            after_row = after_rows[offset]
            if not isinstance(before_row, dict) or not isinstance(after_row, dict):
                continue

            changed_fields = []
            for key, after_value in after_row.items():
                before_value = before_row.get(key)
                if before_value != after_value:
                    changed_fields.append({
                        "field": key,
                        "before": before_value,
                        "after": after_value,
                    })
                if len(changed_fields) >= field_limit:
                    break

            if changed_fields:
                samples.append({
                    "row_index": start_index + offset,
                    "changes": changed_fields,
                })
            if len(samples) >= sample_limit:
                break

        return samples

    try:
        upstream = requests.post(
            upstream_url,
            data=json.dumps(payload, ensure_ascii=False, allow_nan=True),
            stream=True,
            timeout=(10, 3600),
            headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        raise ValueError(f"上游插补服务连接失败: {exc}")

    if upstream.status_code != 200:
        try:
            detail = upstream.json()
        except Exception:
            detail = {"detail": upstream.text}
        upstream.close()
        raise ValueError(detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False))

    latest_rows = []
    stream_cursor = 0
    try:
        for line in upstream.iter_lines(chunk_size=1024, decode_unicode=True):
            if line is None:
                continue
            if "\\n" in line:
                line = line.replace("\\r\\n", "\n").replace("\\n", "\n")

            parts = line.split("\n") if "\n" in line else [line]
            for part in parts:
                part = part.strip()
                if not part or not part.startswith("data:"):
                    continue
                text = part[5:].strip()
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except Exception:
                    continue

                event_name = data.get("event")
                has_rows = isinstance(data.get("rows"), list) or isinstance(data.get("final_rows"), list)
                if event_name in {"diffusion_step", "done"} and has_rows:
                    stream_cursor, merged_rows = _merge_rows_to_full_rows(data, stream_cursor)
                    if merged_rows:
                        data["ground_truth"] = _slice_ground_truth_rows(data.get("row_start", 0), len(merged_rows))
                        latest_rows = merged_rows
                if event_name == "done":
                    data["ground_truth"] = [_to_json_safe(row) for row in ground_truth_rows]
                    return full_rows if full_rows else latest_rows
                if event_name == "error":
                    raise ValueError(data.get("message") or "上游插补服务返回错误")
    finally:
        upstream.close()

    return full_rows if full_rows else latest_rows


def _build_imputation_sse_response_with_row_merge(
    upstream,
    qar_id,
    normalization_specs=None,
    ground_truth_rows=None,
    request_mask_columns=None,
    request_missing_mask=None,
):
    full_field_names = [field.name for field in QAR._meta.fields]
    full_rows = list(
        QAR.objects.filter(qar_id=qar_id)
        .order_by("dSimTime", "id")
        .values(*full_field_names)
    )
    full_rows = _downsample_rows_by_interval(full_rows)
    normalization_specs = dict(normalization_specs or {})
    ground_truth_rows = ground_truth_rows or full_rows
    # 仅允许插补目标列被流式补丁覆盖；其余列始终保留原始值。
    if isinstance(request_mask_columns, list) and request_mask_columns:
        updatable_fields = {str(field) for field in request_mask_columns}
    else:
        updatable_fields = set(LGTDM_INPUT_FIELDS)

    def _normalize_mask_rows(value):
        if not isinstance(value, list):
            return []
        if not value:
            return []
        first = value[0]
        if isinstance(first, list) and first and isinstance(first[0], list):
            merged = []
            for batch in value:
                if isinstance(batch, list):
                    merged.extend(batch)
            return merged
        return value

    flattened_request_missing_mask = _normalize_mask_rows(request_missing_mask)

    def _normalize_step_rows(value):
        if not isinstance(value, list):
            return []
        if value and isinstance(value[0], list):
            merged = []
            for batch in value:
                if isinstance(batch, list):
                    merged.extend(batch)
            return merged
        return value

    def _merge_stream_rows(event_payload, cursor):
        event_name = event_payload.get("event")
        if event_name not in {"diffusion_step", "done"}:
            return cursor, 0, []

        if isinstance(event_payload.get("rows"), list):
            key = "rows"
        elif isinstance(event_payload.get("final_rows"), list):
            key = "final_rows"
        else:
            return cursor, 0, []

        raw_rows = event_payload.get("rows")
        if not isinstance(raw_rows, list):
            raw_rows = event_payload.get("final_rows")
        incoming_rows = _normalize_step_rows(raw_rows)
        row_count = len(incoming_rows)
        if row_count <= 0:
            return cursor, 0, []

        start = event_payload.get("row_start")
        try:
            start_index = int(start)
            if start_index < 0 or start_index >= len(full_rows):
                start_index = cursor
        except (TypeError, ValueError):
            start_index = cursor

        if start_index < 0 or start_index >= len(full_rows):
            start_index = 0

        merged_rows = []
        for offset, incoming in enumerate(incoming_rows):
            row_index = start_index + offset

            base_row = {}
            if 0 <= row_index < len(full_rows):
                base_row = dict(full_rows[row_index])

            if isinstance(incoming, dict):
                incoming_row = dict(incoming)
                _denormalize_row_patch_inplace(incoming_row, normalization_specs)
                for field, value in incoming_row.items():
                    # 非目标列不刷新，保持原始行值。
                    if field not in updatable_fields:
                        continue
                    # 上游缺失占位 None 不覆盖原始观测值。
                    if value is None:
                        continue
                    base_row[field] = value

            if row_index < len(full_rows):
                full_rows[row_index] = base_row
            else:
                full_rows.append(base_row)

            merged_rows.append(_to_json_safe(base_row))

        event_payload[key] = merged_rows
        event_payload.pop("final_rows" if key == "rows" else "rows", None)
        event_payload["row_start"] = start_index

        next_cursor = start_index + len(merged_rows)
        return next_cursor, len(merged_rows), merged_rows

    def _sample_row_diffs(before_rows, after_rows, start_index, sample_limit=3, field_limit=5):
        if not isinstance(before_rows, list) or not isinstance(after_rows, list):
            return []

        max_rows = min(len(before_rows), len(after_rows))
        samples = []
        for offset in range(max_rows):
            before_row = before_rows[offset]
            after_row = after_rows[offset]
            if not isinstance(before_row, dict) or not isinstance(after_row, dict):
                continue

            changed_fields = []
            for key, after_value in after_row.items():
                before_value = before_row.get(key)
                if before_value != after_value:
                    changed_fields.append({
                        "field": key,
                        "before": before_value,
                        "after": after_value,
                    })
                if len(changed_fields) >= field_limit:
                    break

            if changed_fields:
                samples.append({
                    "row_index": start_index + offset,
                    "changes": changed_fields,
                })
            if len(samples) >= sample_limit:
                break

        return samples

    def _slice_ground_truth_rows(start_index, count):
        if not ground_truth_rows:
            return []
        if start_index < 0:
            start_index = 0
        return [_to_json_safe(row) for row in ground_truth_rows[start_index:start_index + count]]

    def event_stream():
        event_lines = []
        stream_cursor = 0
        previous_step_rows = None
        try:
            for raw_line in upstream.iter_lines(chunk_size=1024, decode_unicode=True):
                if raw_line is None:
                    continue

                line = raw_line
                if "\\n" in line:
                    line = line.replace("\\r\\n", "\n").replace("\\n", "\n")

                if line == "":
                    if not event_lines:
                        yield "\n"
                        continue

                    data_text = "".join(
                        part[5:].strip()
                        for part in event_lines
                        if part.startswith("data:")
                    )

                    if not data_text:
                        yield "\n\n"
                        event_lines = []
                        continue

                    try:
                        payload = json.loads(data_text)
                    except Exception:
                        for part in event_lines:
                            yield f"{part}\n"
                        yield "\n"
                        event_lines = []
                        continue

                    event_name = payload.get("event")
                    if event_name == "meta" and not normalization_specs:
                        normalization_specs.clear()
                        normalization_specs.update(
                            _build_field_normalization_specs(payload.get("target_columns") or payload.get("mask_columns") or [])
                        )
                    if event_name == "meta":
                        if isinstance(request_mask_columns, list) and request_mask_columns:
                            payload["mask_columns"] = request_mask_columns
                        if flattened_request_missing_mask:
                            payload["missing_mask"] = flattened_request_missing_mask
                    has_rows = isinstance(payload.get("rows"), list) or isinstance(payload.get("final_rows"), list)
                    if event_name in {"diffusion_step", "done"} and has_rows:
                        stream_cursor, row_count, merged_rows = _merge_stream_rows(payload, stream_cursor)
                        if row_count > 0:
                            start_index = int(payload.get("row_start", max(stream_cursor - row_count, 0)) or 0)
                            current_rows = merged_rows
                            if event_name == "diffusion_step" and previous_step_rows is not None:
                                previous_rows = previous_step_rows
                                step_diffs = _sample_row_diffs(previous_rows, current_rows, start_index)
                                logger.info(
                                    "imputation diffusion_step diff: qar_id=%s model_name=%s step=%s row_start=%s row_count=%s changed_rows=%s sample=%s",
                                    qar_id,
                                    payload.get("model_name"),
                                    payload.get("step"),
                                    start_index,
                                    row_count,
                                    len(step_diffs),
                                    json.dumps(step_diffs, ensure_ascii=False),
                                )
                            if event_name == "diffusion_step":
                                previous_step_rows = current_rows
                            payload["row_start"] = start_index
                            payload["row_end"] = payload.get("row_end", stream_cursor)
                            payload["ground_truth"] = _slice_ground_truth_rows(start_index, row_count)
                            if event_name == "done":
                                payload["ground_truth"] = [_to_json_safe(row) for row in ground_truth_rows]

                    yield f"data: {json.dumps(_to_json_safe(payload), ensure_ascii=False)}\n\n"
                    event_lines = []
                    continue

                if "\n" in line:
                    for part in line.split("\n"):
                        if part == "":
                            if event_lines:
                                data_text = "".join(
                                    item[5:].strip()
                                    for item in event_lines
                                    if item.startswith("data:")
                                )
                                if data_text:
                                    try:
                                        payload = json.loads(data_text)
                                        event_name = payload.get("event")
                                        if event_name == "meta" and not normalization_specs:
                                            normalization_specs.clear()
                                            normalization_specs.update(
                                                _build_field_normalization_specs(payload.get("target_columns") or payload.get("mask_columns") or [])
                                            )
                                        if event_name == "meta":
                                            if isinstance(request_mask_columns, list) and request_mask_columns:
                                                payload["mask_columns"] = request_mask_columns
                                            if flattened_request_missing_mask:
                                                payload["missing_mask"] = flattened_request_missing_mask
                                        has_rows = isinstance(payload.get("rows"), list) or isinstance(payload.get("final_rows"), list)
                                        if event_name in {"diffusion_step", "done"} and has_rows:
                                            stream_cursor, row_count, _ = _merge_stream_rows(payload, stream_cursor)
                                            if row_count > 0:
                                                start_index = int(payload.get("row_start", max(stream_cursor - row_count, 0)) or 0)
                                                payload["row_start"] = start_index
                                                payload["row_end"] = payload.get("row_end", stream_cursor)
                                                payload["ground_truth"] = _slice_ground_truth_rows(start_index, row_count)
                                                if event_name == "done":
                                                    payload["ground_truth"] = [_to_json_safe(row) for row in ground_truth_rows]
                                        yield f"data: {json.dumps(_to_json_safe(payload), ensure_ascii=False)}\n\n"
                                    except Exception:
                                        for item in event_lines:
                                            yield f"{item}\n"
                                        yield "\n"
                                else:
                                    for item in event_lines:
                                        yield f"{item}\n"
                                    yield "\n"
                                event_lines = []
                            else:
                                yield "\n"
                            continue
                        event_lines.append(part)
                    continue

                event_lines.append(line)

            if event_lines:
                data_text = "".join(
                    part[5:].strip()
                    for part in event_lines
                    if part.startswith("data:")
                )
                if data_text:
                    try:
                        payload = json.loads(data_text)
                        event_name = payload.get("event")
                        if event_name == "meta" and not normalization_specs:
                            normalization_specs.clear()
                            normalization_specs.update(
                                _build_field_normalization_specs(payload.get("target_columns") or payload.get("mask_columns") or [])
                            )
                        if event_name == "meta":
                            if isinstance(request_mask_columns, list) and request_mask_columns:
                                payload["mask_columns"] = request_mask_columns
                            if flattened_request_missing_mask:
                                payload["missing_mask"] = flattened_request_missing_mask
                        has_rows = isinstance(payload.get("rows"), list) or isinstance(payload.get("final_rows"), list)
                        if event_name in {"diffusion_step", "done"} and has_rows:
                            stream_cursor, row_count, _ = _merge_stream_rows(payload, stream_cursor)
                            if row_count > 0:
                                start_index = int(payload.get("row_start", max(stream_cursor - row_count, 0)) or 0)
                                payload["row_start"] = start_index
                                payload["row_end"] = payload.get("row_end", stream_cursor)
                                payload["ground_truth"] = _slice_ground_truth_rows(start_index, row_count)
                                if event_name == "done":
                                    payload["ground_truth"] = [_to_json_safe(row) for row in ground_truth_rows]
                        yield f"data: {json.dumps(_to_json_safe(payload), ensure_ascii=False)}\n\n"
                    except Exception:
                        for part in event_lines:
                            yield f"{part}\n"
                        yield "\n"
                else:
                    for part in event_lines:
                        yield f"{part}\n"
                    yield "\n"
        except requests.exceptions.ChunkedEncodingError:
            err = {"event": "error", "message": "upstream stream ended prematurely"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except requests.RequestException as exc:
            err = {"event": "error", "message": f"upstream request error: {str(exc)}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        finally:
            upstream.close()

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _build_imputation_sse_response(upstream):
    def event_stream():
        try:
            for line in upstream.iter_lines(chunk_size=1024, decode_unicode=True):
                if line is None:
                    continue
                if "\\n" in line:
                    line = line.replace("\\r\\n", "\n").replace("\\n", "\n")

                if line == "":
                    yield "\n"
                    continue

                if "\n" in line:
                    for part in line.split("\n"):
                        if part == "":
                            yield "\n"
                            continue
                        yield f"{part}\n"
                    continue

                yield f"{line}\n"
        except requests.exceptions.ChunkedEncodingError:
            err = {"event": "error", "message": "upstream stream ended prematurely"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except requests.RequestException as exc:
            err = {"event": "error", "message": f"upstream request error: {str(exc)}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        finally:
            upstream.close()

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class DataImputationTrainStreamProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        upstream_url = getattr(
            settings,
            "IMPUTATION_TRAIN_STREAM_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/train/stream",
        )

        payload = request.data if isinstance(request.data, dict) else {}
        try:
            upstream = requests.post(
                upstream_url,
                json=payload,
                stream=True,
                timeout=(10, 7200),
                headers={"Accept": "text/event-stream"},
            )
        except requests.RequestException as exc:
            return fail(f"上游训练服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                payload = upstream.json()
                detail = payload if isinstance(payload, dict) else {"detail": payload}
            except Exception:
                detail = {"detail": upstream.text}
            upstream.close()
            return JsonResponse(detail, status=upstream.status_code)

        return _build_imputation_sse_response(upstream)


class DataImputationTrainStopProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        upstream_url = getattr(
            settings,
            "IMPUTATION_TRAIN_STOP_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/train/stop",
        )

        try:
            upstream = requests.post(upstream_url, json={}, timeout=(10, 30))
        except requests.RequestException as exc:
            return fail(f"上游停止训练服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                payload = upstream.json()
                detail = payload if isinstance(payload, dict) else {"detail": payload}
            except Exception:
                detail = {"detail": upstream.text}
            return JsonResponse(detail, status=upstream.status_code)

        try:
            data = upstream.json()
        except Exception:
            return fail("上游停止训练服务返回非 JSON 数据", status_code=502)

        return ok(data, message="已转发停止训练请求")


class DataImputationRepairStreamProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return fail("缺少 file 文件", status_code=400)

        upstream_url = getattr(
            settings,
            "IMPUTATION_REPAIR_STREAM_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/stream/repair",
        )

        files = {
            "file": (upload.name, upload.read(), upload.content_type or "text/csv"),
        }
        data = {
            "model_name": request.data.get("model_name", DEFAULT_IMPUTATION_MODEL),
            "diff_steps": request.data.get("diff_steps", 30),
            "max_rows_per_event": request.data.get("max_rows_per_event", 200),
        }

        logger.info(
            "imputation repair-file request: model_name=%s diff_steps=%s max_rows_per_event=%s file=%s",
            data.get("model_name"),
            data.get("diff_steps"),
            data.get("max_rows_per_event"),
            upload.name,
        )

        try:
            upstream = requests.post(
                upstream_url,
                files=files,
                data=data,
                stream=True,
                timeout=(10, 3600),
                headers={"Accept": "text/event-stream"},
            )
        except requests.RequestException as exc:
            return fail(f"上游插补服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                payload = upstream.json()
                detail = payload if isinstance(payload, dict) else {"detail": payload}
            except Exception:
                detail = {"detail": upstream.text}
            upstream.close()
            return JsonResponse(detail, status=upstream.status_code)

        return _build_imputation_sse_response(upstream)


class DataImputationRepairStreamByQarProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        qar_id = (request.data.get("qar_id") or "").strip()
        if not qar_id:
            return fail("缺少 qar_id 参数", status_code=400)

        upstream_url = getattr(
            settings,
            "IMPUTATION_REPAIR_STREAM_JSON_UPSTREAM_URL",
            "http://127.0.0.1:8002/api/v1/imputation/stream/repair-json",
        )

        model_name = str(request.data.get("model_name") or DEFAULT_IMPUTATION_MODEL).strip() or DEFAULT_IMPUTATION_MODEL
        diff_steps = int(request.data.get("diff_steps", 30) or 30)
        max_rows_per_event = int(request.data.get("max_rows_per_event", 200) or 200)
        mask_missing_value = int(request.data.get("mask_missing_value", 0) or 0)
        model_path = (request.data.get("model_path") or "").strip() or None

        try:
            mask_columns_override = _parse_mask_columns_value(request.data.get("mask_columns"))
            payload, normalization_specs, ground_truth_rows = _build_repair_json_payload(
                qar_id=qar_id,
                model_name=model_name,
                diff_steps=diff_steps,
                max_rows_per_event=max_rows_per_event,
                mask_missing_value=mask_missing_value,
                model_path=model_path,
                mask_columns_override=mask_columns_override,
            )
        except ValueError as exc:
            return fail(str(exc), status_code=400)

        try:
            upstream = requests.post(
                upstream_url,
                data=json.dumps(payload, ensure_ascii=False, allow_nan=True),
                stream=True,
                timeout=(10, 3600),
                headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            return fail(f"上游插补服务连接失败: {exc}", status_code=502)

        if upstream.status_code != 200:
            try:
                payload = upstream.json()
                detail = payload if isinstance(payload, dict) else {"detail": payload}
            except Exception:
                detail = {"detail": upstream.text}
            upstream.close()
            return JsonResponse(detail, status=upstream.status_code)

        return _build_imputation_sse_response_with_row_merge(
            upstream,
            qar_id,
            normalization_specs=normalization_specs,
            ground_truth_rows=ground_truth_rows,
            request_mask_columns=payload.get("mask_columns"),
            request_missing_mask=payload.get("missing_mask"),
        )
