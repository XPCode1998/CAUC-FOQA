import json

import requests
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.api.utils import ok, fail
from apps.core.models import QAR, QAR_Parameter_Attribute
from apps.api.flight_service import (
    build_stats,
    build_chart_payload,
    build_trajectory_payload,
    build_replay_payload,
    downsample_with_fixed_interval,
    get_available_qar_ids,
    get_default_qar_id,
)


def _normalize_risk_seq_len(model_name, raw_seq_len, default=10):
    try:
        seq_len = int(raw_seq_len)
    except (TypeError, ValueError):
        seq_len = default

    if str(model_name or '').strip() == 'iTransformer':
        return 300

    return seq_len


RISK_STREAM_JSON_FEATURE_COLUMNS = [
    "dAlpha",
    "dAlphaRad",
    "dSinAlpha",
    "dCosAlpha",
    "dBeta",
    "dBetaRad",
    "dSinBeta",
    "dPhi",
    "dTheta",
    "dPsi",
    "dChi",
    "dGamma",
    "dGroundspeed",
    "dTAS",
    "dMach",
    "dUk",
    "dVk",
    "dWk",
    "dU",
    "dV",
    "dUkgDot",
    "dVkgDot",
    "dUkg",
    "dVkg",
    "dWkg",
    "pe_t1",
    "pe_t2",
]


def _risk_stream_print(message):
    print(f"[flight-risk-stream] {message}")


def _normalize_stream_json_rows(rows):
    normalized = []
    for row in rows:
        item = {}
        for field in RISK_STREAM_JSON_FEATURE_COLUMNS:
            value = row.get(field)
            if value is None:
                item[field] = 0.0
                continue
            try:
                item[field] = float(value)
            except (TypeError, ValueError):
                item[field] = 0.0
        normalized.append(item)
    return normalized


def _build_sse_response(upstream, trace_label=""):
    def event_stream():
        _risk_stream_print(f"stream opened {trace_label}".strip())
        try:
            for line in upstream.iter_lines(chunk_size=1024, decode_unicode=True):
                if line is None:
                    continue

                # Some upstream implementations may return escaped newlines ("\\n\\n")
                # inside a single line; normalize them back to real SSE frame separators.
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
                        if part.startswith("data:"):
                            _risk_stream_print(f"result {trace_label} {part}".strip())
                        yield f"{part}\n"
                    continue

                if line.startswith("data:"):
                    _risk_stream_print(f"result {trace_label} {line}".strip())
                yield f"{line}\n"
        except requests.exceptions.ChunkedEncodingError:
            err = {"event": "error", "message": "upstream stream ended prematurely"}
            _risk_stream_print(f"stream chunked error {trace_label}: {err['message']}".strip())
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except requests.RequestException as exc:
            err = {"event": "error", "message": f"upstream request error: {str(exc)}"}
            _risk_stream_print(f"stream request error {trace_label}: {err['message']}".strip())
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        finally:
            upstream.close()
            _risk_stream_print(f"stream closed {trace_label}".strip())

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class FlightOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qar_id = (request.GET.get("qar_id") or "").strip()
        if not qar_id:
            qar_id = QAR.objects.values_list("qar_id", flat=True).order_by("qar_id").first()
            if not qar_id:
                return fail("暂无飞行数据", status_code=404)

        rows = list(
            QAR.objects.filter(qar_id=qar_id)
            .order_by("dSimTime")
            .values(
                "dSimTime",
                "gfuel",
                "dASL",
                "dTAS",
                "dWkg",
                "dMach",
                "dPhi",
                "dTheta",
                "dGamma",
                "dNx",
                "dNy",
                "dNz",
            )
        )
        if not rows:
            return fail("未找到对应飞行数据", status_code=404)

        return ok(
            {
                "qar_id": qar_id,
                "stats": build_stats(rows),
                "total_points": len(rows),
            }
        )


class FlightChartsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qar_id = (request.GET.get("qar_id") or "").strip()
        if not qar_id:
            return fail("缺少 qar_id 参数", status_code=400)

        max_points = request.GET.get("max_points")
        try:
            max_points_int = int(max_points) if max_points else 1200
        except ValueError:
            max_points_int = 1200
        max_points_int = min(max(200, max_points_int), 3000)

        requested_fields = [
            item.strip()
            for item in (request.GET.get("fields") or "").split(",")
            if item.strip()
        ]
        valid_fields = set(QAR.get_fields())
        default_fields = ["dASL", "dTAS", "dWkg", "dPhi", "dTheta"]
        series_fields = [f for f in requested_fields if f in valid_fields] or default_fields

        value_fields = ["dSimTime"]
        for field in series_fields:
            if field not in value_fields:
                value_fields.append(field)

        rows = list(
            QAR.objects.filter(qar_id=qar_id)
            .order_by("dSimTime")
            .values(*value_fields)
        )
        if not rows:
            return fail("未找到对应飞行数据", status_code=404)

        payload = build_chart_payload(rows, max_points_int, series_fields)
        return ok(
            {
                "qar_id": qar_id,
                "charts": payload,
                "sample_points": len(payload["time_label"]),
                "total_points": len(rows),
            }
        )


class FlightTrajectoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qar_id = (request.GET.get("qar_id") or "").strip()
        if not qar_id:
            return fail("缺少 qar_id 参数", status_code=400)

        max_points = request.GET.get("max_points")
        try:
            max_points_int = int(max_points) if max_points else 2000
        except ValueError:
            max_points_int = 2000
        max_points_int = min(max(300, max_points_int), 5000)

        rows = list(
            QAR.objects.filter(qar_id=qar_id)
            .order_by("dSimTime")
            .values("dSimTime", "dLongitude", "dLatitude", "dASL")
        )
        if not rows:
            return fail("未找到对应航迹数据", status_code=404)

        trajectory = build_trajectory_payload(rows, max_points_int)
        return ok(
            {
                "qar_id": qar_id,
                "trajectory": trajectory,
                "sample_points": len(trajectory),
                "total_points": len(rows),
            }
        )


class FlightRiskOverlimitAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qar_id = (request.GET.get("qar_id") or "").strip()
        if not qar_id:
            return fail("缺少 qar_id 参数", status_code=400)

        monitored_attrs = {
            p.parameter_name: p
            for p in QAR_Parameter_Attribute.objects.filter(is_monitored=True)
        }
        monitored_fields = [field for field in QAR.get_fields() if field in monitored_attrs]
        if not monitored_fields:
            return ok({"qar_id": qar_id, "exceeded_records": []})

        value_fields = ["dSimTime", *monitored_fields]
        flight_rows = list(
            QAR.objects.filter(qar_id=qar_id)
            .order_by("dSimTime")
            .values(*value_fields)
        )
        if not flight_rows:
            return fail("未找到对应飞行数据", status_code=404)

        # 风险预警按固定间隔 10 下采样，统一与可视化/回放/插补策略。
        flight_rows = downsample_with_fixed_interval(flight_rows)

        exceeded_records = []

        def classify_exceed(value, attr):
            if value is None:
                return None
            if attr.critical_lower is not None and value < attr.critical_lower:
                return "严重下限", "高"
            if attr.critical_upper is not None and value > attr.critical_upper:
                return "严重上限", "高"
            if attr.warning_lower is not None and value < attr.warning_lower:
                return "警告下限", "中"
            if attr.warning_upper is not None and value > attr.warning_upper:
                return "警告上限", "中"
            return None

        def to_time_value(raw_time, fallback_index):
            if raw_time is None:
                return float(fallback_index)
            try:
                return float(raw_time)
            except (TypeError, ValueError):
                return float(fallback_index)

        def finalize_interval(interval):
            duration = max(0.0, interval["end_time"] - interval["start_time"])
            return {
                "parameter": interval["parameter"],
                "parameter_name": interval["parameter_name"],
                "unit": interval["unit"],
                "thresholds": interval["thresholds"],
                "exceed_type": interval["exceed_type"],
                "severity": interval["severity"],
                "start_time": round(interval["start_time"], 3),
                "end_time": round(interval["end_time"], 3),
                "duration": round(duration, 3),
                "start_value": interval["start_value"],
                "end_value": interval["end_value"],
                "peak_value": interval["peak_value"],
                "sample_count": interval["sample_count"],
                "value": interval["peak_value"],
            }

        for field in monitored_fields:
            attr = monitored_attrs[field]
            threshold_low = attr.warning_lower if attr.warning_lower is not None else attr.critical_lower
            threshold_high = attr.warning_upper if attr.warning_upper is not None else attr.critical_upper
            thresholds = f"{threshold_low} ~ {threshold_high}"

            current_interval = None

            for idx, row in enumerate(flight_rows):
                current_time = to_time_value(row.get("dSimTime"), idx)
                current_value = row.get(field)
                state = classify_exceed(current_value, attr)

                if state is None:
                    if current_interval is not None:
                        exceeded_records.append(finalize_interval(current_interval))
                        current_interval = None
                    continue

                exceed_type, severity = state
                if (
                    current_interval is not None
                    and current_interval["exceed_type"] == exceed_type
                    and current_interval["severity"] == severity
                ):
                    current_interval["end_time"] = current_time
                    current_interval["end_value"] = current_value
                    current_interval["sample_count"] += 1
                    if current_value is not None:
                        if "下限" in exceed_type:
                            current_interval["peak_value"] = min(current_interval["peak_value"], current_value)
                        else:
                            current_interval["peak_value"] = max(current_interval["peak_value"], current_value)
                    continue

                if current_interval is not None:
                    exceeded_records.append(finalize_interval(current_interval))

                current_interval = {
                    "parameter": field,
                    "parameter_name": attr.description or field,
                    "unit": attr.unit or "",
                    "thresholds": thresholds,
                    "exceed_type": exceed_type,
                    "severity": severity,
                    "start_time": current_time,
                    "end_time": current_time,
                    "start_value": current_value,
                    "end_value": current_value,
                    "peak_value": current_value,
                    "sample_count": 1,
                }

            if current_interval is not None:
                exceeded_records.append(finalize_interval(current_interval))

        exceeded_records.sort(key=lambda item: (item.get("start_time", 0), item.get("parameter", "")))

        return ok({"qar_id": qar_id, "exceeded_records": exceeded_records})


class FlightReplayAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qar_id = (request.GET.get("qar_id") or "").strip()
        if not qar_id:
            qar_id = get_default_qar_id()
            if not qar_id:
                return fail("暂无可回放飞行数据", status_code=404)

        max_points = request.GET.get("max_points")
        try:
            max_points_int = int(max_points) if max_points else 30000
        except ValueError:
            max_points_int = 30000
        max_points_int = min(max(1000, max_points_int), 60000)

        rows = list(
            QAR.objects.filter(qar_id=qar_id)
            .order_by("dSimTime")
            .values("dSimTime", "dLongitude", "dLatitude", "dASL", "dTAS", "dTrueHeading", "dPhi", "dTheta")
        )
        if not rows:
            return fail("未找到对应回放数据", status_code=404)

        replay = build_replay_payload(rows, max_points_int)
        if not replay:
            return fail("回放数据为空", status_code=404)

        duration = max(0.0, replay[-1]["t"] - replay[0]["t"])
        return ok(
            {
                "qar_id": qar_id,
                "available_qar_ids": get_available_qar_ids(),
                "replay": replay,
                "sample_points": len(replay),
                "total_points": len(rows),
                "duration": round(duration, 2),
            }
        )


class FlightRiskOverlimitStreamProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return fail("缺少 file 文件", status_code=400)

        upstream_url = getattr(
            settings,
            "FLIGHT_RISK_STREAM_UPSTREAM_URL",
            "http://127.0.0.1:8001/api/v1/flight-risk/stream",
        )

        model_name = request.data.get("model_name", "CNN")
        seq_len = _normalize_risk_seq_len(model_name, request.data.get("seq_len", "10"))
        auto_select = request.data.get("auto_select", "1")
        manual_select = request.data.get("manual_select", "1")

        files = {
            "file": (upload.name, upload.read(), upload.content_type or "text/plain"),
        }
        data = {
            "model_name": model_name,
            "seq_len": seq_len,
            "auto_select": auto_select,
            "manual_select": manual_select,
        }

        trace_label = f"source=file file={upload.name} model={model_name} seq_len={seq_len}"
        _risk_stream_print(f"request start {trace_label}")

        try:
            upstream = requests.post(
                upstream_url,
                files=files,
                data=data,
                stream=True,
                timeout=(10, 1800),
                headers={"Accept": "text/event-stream"},
            )
        except requests.RequestException as exc:
            _risk_stream_print(f"request failed {trace_label}: {exc}")
            return fail(f"上游风险服务连接失败: {exc}", status_code=502)

        _risk_stream_print(f"upstream status {trace_label}: {upstream.status_code}")

        if upstream.status_code != 200:
            try:
                payload = upstream.json()
                detail = payload if isinstance(payload, dict) else {"detail": payload}
            except Exception:
                detail = {"detail": upstream.text}
            _risk_stream_print(f"upstream error body {trace_label}: {detail}")
            upstream.close()
            return JsonResponse(detail, status=upstream.status_code)

        return _build_sse_response(upstream, trace_label=trace_label)


class FlightRiskOverlimitStreamByQarProxyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        qar_id = (request.data.get("qar_id") or "").strip()
        if not qar_id:
            return fail("缺少 qar_id 参数", status_code=400)

        upstream_url = getattr(
            settings,
            "FLIGHT_RISK_STREAM_JSON_UPSTREAM_URL",
            "http://127.0.0.1:8001/api/v1/flight-risk/stream-json",
        )

        model_name = request.data.get("model_name", "CNN")
        seq_len = _normalize_risk_seq_len(model_name, request.data.get("seq_len", "10"))

        value_fields = ["dSimTime", *RISK_STREAM_JSON_FEATURE_COLUMNS]
        rows = list(
            QAR.objects.filter(qar_id=qar_id)
            .order_by("dSimTime", "id")
            .values(*value_fields)
        )
        if not rows:
            return fail("未找到对应 QAR 数据", status_code=404)

        rows = downsample_with_fixed_interval(rows)

        payload = {
            "model_name": model_name,
            "seq_len": seq_len,
            "rows": _normalize_stream_json_rows(rows),
        }

        trace_label = f"source=qar qar_id={qar_id} rows={len(rows)} model={model_name} seq_len={seq_len}"
        _risk_stream_print(f"request start {trace_label}")

        try:
            upstream = requests.post(
                upstream_url,
                json=payload,
                stream=True,
                timeout=(10, 1800),
                headers={"Accept": "text/event-stream"},
            )
        except requests.RequestException as exc:
            _risk_stream_print(f"request failed {trace_label}: {exc}")
            return fail(f"上游风险服务连接失败: {exc}", status_code=502)

        _risk_stream_print(f"upstream status {trace_label}: {upstream.status_code}")

        if upstream.status_code != 200:
            try:
                payload = upstream.json()
                detail = payload if isinstance(payload, dict) else {"detail": payload}
            except Exception:
                detail = {"detail": upstream.text}
            _risk_stream_print(f"upstream error body {trace_label}: {detail}")
            upstream.close()
            return JsonResponse(detail, status=upstream.status_code)

        return _build_sse_response(upstream, trace_label=trace_label)
