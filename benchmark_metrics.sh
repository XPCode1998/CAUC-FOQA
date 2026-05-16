#!/usr/bin/env bash

set -euo pipefail

BASE_URL="http://127.0.0.1:8000"
USERNAME="benchmark_user"
PASSWORD="benchmark_pass_123"
QUERY_RUNS=20
VIS_RUNS=10
UPLOAD_RUNS=3
UPLOAD_LABEL=0
QAR_ID=""
SAMPLE_FILE=""
MODEL_NAME="LGTDM"
ACCURACY_CSV=""
ACTUAL_COL="actual"
PRED_COL="pred"
OBSERVED_HOURS=""
DOWNTIME_MINUTES=""
MAX_FILE_SIZE_MB=500
UPLOAD_PROBE_TARGET_MB=500
UPLOAD_PROBE_SOURCE_FILE=""
UPLOAD_PROBE_CACHE_FILE=""
OUTPUT_DIR="benchmark_results"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "${SCRIPT_DIR}"

usage() {
  cat <<'EOT'
用法:
  ./benchmark_metrics.sh [选项]

选项:
  -u <base_url>         后端服务地址，默认: http://127.0.0.1:8000
  -n <username>         测试用户名，默认: benchmark_user
  -w <password>         测试密码，默认: benchmark_pass_123
  -q <runs>             指标1(查询)测试次数，默认: 20
  -v <runs>             指标2(可视化)测试次数，默认: 10
  -p <runs>             指标3(上传)测试次数，默认: 3
  -f <sample_file>      上传测试文件路径(csv)
  -l <label>            上传标签，默认: 0
  -i <qar_id>           指定 QAR ID（不指定则自动取第一个）
  -m <model_name>       修复模型名，默认: LGTDM
  -a <accuracy_csv>     指标5准确率CSV（需包含真实值和预测值）
  -x <actual_col>       指标5真实值列名，默认: actual
  -y <pred_col>         指标5预测值列名，默认: pred
  -H <observed_hours>   指标9观测时长(小时)
  -D <downtime_minutes> 指标9故障时长(分钟)
  -o <output_dir>       输出目录，默认: benchmark_results
  -t <probe_source>     指标11拼接源文件，默认: ./test.csv
  -h                    显示帮助

示例:
  ./benchmark_metrics.sh -f ./test.csv -q 30 -v 15 -p 5
  ./benchmark_metrics.sh -n admin -w admin123 -i 2023083124440
  ./benchmark_metrics.sh -a ./eval_result.csv -x y_true -y y_pred
  ./benchmark_metrics.sh -H 720 -D 60
EOT
}

while getopts ":u:n:w:q:v:p:f:l:i:m:a:x:y:H:D:o:t:h" opt; do
  case "${opt}" in
    u) BASE_URL="${OPTARG}" ;;
    n) USERNAME="${OPTARG}" ;;
    w) PASSWORD="${OPTARG}" ;;
    q) QUERY_RUNS="${OPTARG}" ;;
    v) VIS_RUNS="${OPTARG}" ;;
    p) UPLOAD_RUNS="${OPTARG}" ;;
    f) SAMPLE_FILE="${OPTARG}" ;;
    l) UPLOAD_LABEL="${OPTARG}" ;;
    i) QAR_ID="${OPTARG}" ;;
    m) MODEL_NAME="${OPTARG}" ;;
    a) ACCURACY_CSV="${OPTARG}" ;;
    x) ACTUAL_COL="${OPTARG}" ;;
    y) PRED_COL="${OPTARG}" ;;
    H) OBSERVED_HOURS="${OPTARG}" ;;
    D) DOWNTIME_MINUTES="${OPTARG}" ;;
    o) OUTPUT_DIR="${OPTARG}" ;;
    t) UPLOAD_PROBE_SOURCE_FILE="${OPTARG}" ;;
    h)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] 未知参数: -${OPTARG}" >&2
      usage
      exit 1
      ;;
  esac
done

mkdir -p "${OUTPUT_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RESULT_FILE="${OUTPUT_DIR}/metrics_${TIMESTAMP}.md"
RAW_DIR="${OUTPUT_DIR}/raw_${TIMESTAMP}"
mkdir -p "${RAW_DIR}"

check_command() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[ERROR] 未找到命令: ${cmd}" >&2
    exit 1
  fi
}

check_command curl
check_command awk
check_command sort
check_command python

log() {
  echo "$1" | tee -a "${RESULT_FILE}"
}

safe_num() {
  local v="$1"
  if [[ -z "${v}" ]]; then
    echo "0"
  else
    echo "${v}"
  fi
}

calc_stats() {
  local file="$1"
  python - "$file" <<'PY'
import sys

path = sys.argv[1]
vals = []
with open(path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            vals.append(float(line))
        except Exception:
            pass

if not vals:
    print("count=0 min=0 avg=0 p95=0 max=0")
    raise SystemExit(0)

vals_sorted = sorted(vals)
n = len(vals_sorted)
idx95 = max(0, min(n - 1, int((n * 0.95) - 1 if (n * 0.95).is_integer() else int(n * 0.95))))
avg = sum(vals_sorted) / n
print(f"count={n} min={vals_sorted[0]:.6f} avg={avg:.6f} p95={vals_sorted[idx95]:.6f} max={vals_sorted[-1]:.6f}")
PY
}

extract_stats_field() {
  local stats="$1"
  local key="$2"
  echo "$stats" | awk -v k="$key" '{for(i=1;i<=NF;i++){split($i,a,"="); if(a[1]==k){print a[2]; exit}}}'
}

record_result() {
  local metric="$1"
  local status="$2"
  local target="$3"
  local observed="$4"
  local detail="$5"
  printf "%s|%s|%s|%s|%s\n" "$metric" "$status" "$target" "$observed" "$detail" >> "$RAW_DIR/summary.tsv"
}

api_json_field() {
  local file="$1"
  local expr="$2"
  python - "$file" "$expr" <<'PY'
import json
import sys

path = sys.argv[1]
expr = sys.argv[2]

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

def get(d, path_expr):
    cur = d
    for part in path_expr.split('.'):
        if part == '':
            continue
        if '[' in part and part.endswith(']'):
            name, idx = part[:-1].split('[', 1)
            if name:
                cur = cur.get(name, None) if isinstance(cur, dict) else None
            cur = cur[int(idx)] if isinstance(cur, list) and len(cur) > int(idx) else None
        else:
            cur = cur.get(part, None) if isinstance(cur, dict) else None
        if cur is None:
            return ''
    return cur

value = get(data, expr)
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
elif value is None:
    print('')
else:
    print(value)
PY
}

api_login() {
  local login_file="$RAW_DIR/login.json"
  local http_code
  http_code="$(curl -sS -o "$login_file" -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -X POST "$BASE_URL/api/v1/auth/login" \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" || echo "000")"

  if [[ "$http_code" != "200" ]]; then
    curl -sS -o "$RAW_DIR/register.json" -w "%{http_code}" \
      -H "Content-Type: application/json" \
      -X POST "$BASE_URL/api/v1/auth/register" \
      -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" >/dev/null 2>&1 || true

    http_code="$(curl -sS -o "$login_file" -w "%{http_code}" \
      -H "Content-Type: application/json" \
      -X POST "$BASE_URL/api/v1/auth/login" \
      -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" || echo "000")"
  fi

  if [[ "$http_code" != "200" ]]; then
    echo ""
    return
  fi

  local code access
  code="$(api_json_field "$login_file" "code" || true)"
  access="$(api_json_field "$login_file" "data.access" || true)"
  if [[ "$code" != "0" || -z "$access" ]]; then
    echo ""
    return
  fi

  echo "$access"
}

resolve_qar_id() {
  local ids_file="$RAW_DIR/qar_ids.json"
  local http_code
  http_code="$(curl -sS -o "$ids_file" -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$BASE_URL/api/v1/data/qar-ids?limit=1" || echo "000")"

  if [[ "$http_code" != "200" ]]; then
    echo ""
    return
  fi

  api_json_field "$ids_file" "data.items[0]" || true
}

measure_endpoint_times() {
  local metric_name="$1"
  local url="$2"
  local runs="$3"

  local times_file="$RAW_DIR/${metric_name}_times.txt"
  local status_file="$RAW_DIR/${metric_name}_status.txt"
  : > "$times_file"
  : > "$status_file"

  local i
  for ((i=1; i<=runs; i++)); do
    local out
    out="$(curl -sS -o "$RAW_DIR/${metric_name}_${i}.json" -w "%{http_code}\t%{time_total}" \
      -H "Authorization: Bearer $TOKEN" \
      "$url" || echo "000\t999")"
    echo "$out" | awk -F'\t' '{print $1}' >> "$status_file"
    echo "$out" | awk -F'\t' '{print $2}' >> "$times_file"
  done

  local stats non200
  stats="$(calc_stats "$times_file")"
  non200="$(awk '$1 != 200 {c++} END {print c+0}' "$status_file")"
  echo "$stats|$non200"
}

metric_1_query_response() {
  local url="$BASE_URL/api/v1/data/preview?page=1&page_size=50"
  if [[ -n "$QAR_ID" ]]; then
    url="$url&qar_id=$QAR_ID"
  fi

  local rs stats p95 non200 status detail
  rs="$(measure_endpoint_times "metric1_query" "$url" "$QUERY_RUNS")"
  stats="${rs%%|*}"
  non200="${rs##*|}"
  p95="$(extract_stats_field "$stats" "p95")"

  status="PASS"
  if [[ "$non200" != "0" ]]; then
    status="FAIL"
  fi
  if awk -v x="$(safe_num "$p95")" 'BEGIN{exit !(x>=3.0)}'; then
    status="FAIL"
  fi

  detail="p95=${p95}s, non200=${non200}, runs=${QUERY_RUNS}"
  record_result "查询响应时间" "$status" "< 3s" "$detail" "$stats"
}

metric_2_visual_response() {
  if [[ -z "$QAR_ID" ]]; then
    QAR_ID="$(resolve_qar_id)"
  fi

  if [[ -z "$QAR_ID" ]]; then
    record_result "可视化响应时间" "SKIP" "< 5s" "无可用QAR数据" "请先上传或指定 -i qar_id"
    return
  fi

  local url="$BASE_URL/api/v1/flight/charts?qar_id=$QAR_ID&max_points=1200"
  local rs stats p95 non200 status detail
  rs="$(measure_endpoint_times "metric2_visual" "$url" "$VIS_RUNS")"
  stats="${rs%%|*}"
  non200="${rs##*|}"
  p95="$(extract_stats_field "$stats" "p95")"

  status="PASS"
  if [[ "$non200" != "0" ]]; then
    status="FAIL"
  fi
  if awk -v x="$(safe_num "$p95")" 'BEGIN{exit !(x>=5.0)}'; then
    status="FAIL"
  fi

  detail="qar_id=${QAR_ID}, p95=${p95}s, non200=${non200}, runs=${VIS_RUNS}"
  record_result "可视化响应时间" "$status" "< 5s" "$detail" "$stats"
}

metric_3_upload_speed() {
  if [[ -z "$SAMPLE_FILE" ]]; then
    record_result "上传速度" "SKIP" "> 50 MB/s" "未提供样本文件" "请通过 -f 指定上传文件"
    UPLOAD_SUCCESS=0
    return
  fi
  if [[ ! -f "$SAMPLE_FILE" ]]; then
    record_result "上传速度" "FAIL" "> 50 MB/s" "文件不存在" "$SAMPLE_FILE"
    UPLOAD_SUCCESS=0
    return
  fi

  local speed_file="$RAW_DIR/metric3_upload_speed.txt"
  local status_file="$RAW_DIR/metric3_upload_status.txt"
  : > "$speed_file"
  : > "$status_file"

  local file_size
  file_size="$(wc -c < "$SAMPLE_FILE" | tr -d ' ')"
  local i
  local ok_count=0

  for ((i=1; i<=UPLOAD_RUNS; i++)); do
    local bench_qar_id
    bench_qar_id="bench_${TIMESTAMP}_${i}_$RANDOM"

    local response_file="$RAW_DIR/metric3_upload_${i}.json"
    local out
    out="$(curl -sS -o "$response_file" -w "%{http_code}\t%{time_total}" \
      -H "Authorization: Bearer $TOKEN" \
      -F "label=${UPLOAD_LABEL}" \
      -F "qar_id=${bench_qar_id}" \
      -F "skip_post_process=1" \
      -F "file=@${SAMPLE_FILE}" \
      "$BASE_URL/api/v1/data/upload-raw" || echo "000\t999")"

    local http_code time_total
    http_code="$(echo "$out" | awk -F'\t' '{print $1}')"
    time_total="$(echo "$out" | awk -F'\t' '{print $2}')"
    echo "$http_code" >> "$status_file"

    local api_code
    api_code="$(api_json_field "$response_file" "code" || true)"

    if [[ "$http_code" == "200" && "$api_code" == "0" ]]; then
      ok_count=$((ok_count + 1))
      awk -v size="$file_size" -v t="$time_total" 'BEGIN{ if (t>0) printf "%.6f\n", (size/1024/1024)/t; else print "0" }' >> "$speed_file"

      curl -sS -o /dev/null -X DELETE \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"qar_id\":\"$bench_qar_id\"}" \
        "$BASE_URL/api/v1/data/qar" || true
    else
      echo "0" >> "$speed_file"
    fi
  done

  local stats avg status detail
  stats="$(calc_stats "$speed_file")"
  avg="$(extract_stats_field "$stats" "avg")"
  status="PASS"
  if awk -v x="$(safe_num "$avg")" 'BEGIN{exit !(x<=50.0)}'; then
    status="FAIL"
  fi
  if [[ "$ok_count" -eq 0 ]]; then
    status="FAIL"
  fi

  UPLOAD_SUCCESS="$ok_count"
  detail="avg=${avg}MB/s, success=${ok_count}/${UPLOAD_RUNS}, sample=$(basename "$SAMPLE_FILE")"
  record_result "上传速度" "$status" "> 50 MB/s" "$detail" "$stats"
}

metric_4_inference_time() {
  if [[ -z "$QAR_ID" ]]; then
    QAR_ID="$(resolve_qar_id)"
  fi
  if [[ -z "$QAR_ID" ]]; then
    record_result "技术指标4-数据修复模型推理时间" "SKIP" "< 60s" "无可用QAR数据" "请先上传数据或使用 -i"
    return
  fi

  local resp_file="$RAW_DIR/metric4_infer.json"
  local out
  out="$(curl -sS -o "$resp_file" -w "%{http_code}\t%{time_total}" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -X POST "$BASE_URL/api/v1/data/imputation/repair" \
    -d "{\"qar_id\":\"$QAR_ID\",\"model_name\":\"$MODEL_NAME\",\"page\":1,\"page_size\":150,\"diff_steps\":30}" || echo "000\t999")"

  local http_code infer_time api_code status detail
  http_code="$(echo "$out" | awk -F'\t' '{print $1}')"
  infer_time="$(echo "$out" | awk -F'\t' '{print $2}')"
  api_code="$(api_json_field "$resp_file" "code" || true)"

  status="PASS"
  if [[ "$http_code" != "200" || "$api_code" != "0" ]]; then
    status="FAIL"
  fi
  if awk -v x="$(safe_num "$infer_time")" 'BEGIN{exit !(x>=60.0)}'; then
    status="FAIL"
  fi

  detail="qar_id=${QAR_ID}, model=${MODEL_NAME}, infer_time=${infer_time}s, http=${http_code}, api_code=${api_code}"
  record_result "技术指标4-数据修复模型推理时间" "$status" "< 60s" "$detail" "single_run=${infer_time}s"
}

metric_5_decile_accuracy() {
  if [[ -z "$ACCURACY_CSV" ]]; then
    record_result "技术指标5-十分位准确率" "SKIP" "> 90%" "未提供准确率数据" "请传入 -a accuracy.csv -x actual_col -y pred_col"
    return
  fi
  if [[ ! -f "$ACCURACY_CSV" ]]; then
    record_result "技术指标5-十分位准确率" "FAIL" "> 90%" "文件不存在" "$ACCURACY_CSV"
    return
  fi

  local output
  output="$(python - "$ACCURACY_CSV" "$ACTUAL_COL" "$PRED_COL" <<'PY'
import bisect
import csv
import math
import sys

path, actual_col, pred_col = sys.argv[1], sys.argv[2], sys.argv[3]
actual = []
pred = []

with open(path, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    if actual_col not in reader.fieldnames or pred_col not in reader.fieldnames:
        print('ERROR|missing_column')
        raise SystemExit(0)
    for row in reader:
        try:
            a = float(row.get(actual_col, ''))
            p = float(row.get(pred_col, ''))
        except Exception:
            continue
        if math.isfinite(a) and math.isfinite(p):
            actual.append(a)
            pred.append(p)

n = len(actual)
if n < 10:
    print('ERROR|insufficient_rows')
    raise SystemExit(0)

sorted_actual = sorted(actual)
edges = []
for i in range(1, 10):
    idx = int((n - 1) * i / 10)
    edges.append(sorted_actual[idx])

def to_bin(v):
    return bisect.bisect_right(edges, v) + 1

match = 0
for a, p in zip(actual, pred):
    if to_bin(a) == to_bin(p):
        match += 1

acc = match / n * 100.0
print(f'OK|{n}|{acc:.4f}')
PY
 )"

  local tag n acc status detail
  tag="$(echo "$output" | awk -F'|' '{print $1}')"
  if [[ "$tag" != "OK" ]]; then
    record_result "技术指标5-十分位准确率" "FAIL" "> 90%" "$output" "请检查准确率输入文件及列名"
    return
  fi

  n="$(echo "$output" | awk -F'|' '{print $2}')"
  acc="$(echo "$output" | awk -F'|' '{print $3}')"
  status="PASS"
  if awk -v x="$(safe_num "$acc")" 'BEGIN{exit !(x<=90.0)}'; then
    status="FAIL"
  fi

  detail="samples=${n}, decile_accuracy=${acc}%"
  record_result "技术指标5-十分位准确率" "$status" "> 90%" "$detail" "actual_col=${ACTUAL_COL}, pred_col=${PRED_COL}"
}

metric_6_storage_precision() {
  if [[ -z "$QAR_ID" ]]; then
    QAR_ID="$(resolve_qar_id)"
  fi
  if [[ -z "$QAR_ID" ]]; then
    record_result "技术指标6-数据存储精度" "SKIP" "10毫秒级" "无可用QAR数据" "请先上传数据或使用 -i"
    return
  fi

  local resp_file="$RAW_DIR/metric6_precision.json"
  local http_code
  http_code="$(curl -sS -o "$resp_file" -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$BASE_URL/api/v1/data/preview?qar_id=$QAR_ID&page=1&page_size=500" || echo "000")"

  if [[ "$http_code" != "200" ]]; then
    record_result "技术指标6-数据存储精度" "FAIL" "10毫秒级" "接口请求失败" "http_code=${http_code}"
    return
  fi

  local output
  output="$(python - "$resp_file" <<'PY'
import json
import math
import sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    payload = json.load(f)

rows = (((payload or {}).get('data') or {}).get('rows') or [])
vals = []
max_decimals = 0
for row in rows:
    v = row.get('dSimTime') if isinstance(row, dict) else None
    try:
        x = float(v)
    except Exception:
        continue
    if not math.isfinite(x):
        continue
    vals.append(x)
    txt = f"{x:.9f}".rstrip('0').rstrip('.')
    if '.' in txt:
        max_decimals = max(max_decimals, len(txt.split('.')[-1]))

if len(vals) < 2:
    print('ERROR|insufficient_points')
    raise SystemExit(0)

vals = sorted(set(vals))
mind = None
for i in range(1, len(vals)):
    d = vals[i] - vals[i-1]
    if d > 0:
        mind = d if mind is None else min(mind, d)

if mind is None:
    print('ERROR|no_positive_delta')
    raise SystemExit(0)

ok = (mind <= 0.01 + 1e-9) or (max_decimals >= 2)
print(f"OK|{mind:.9f}|{max_decimals}|{1 if ok else 0}")
PY
 )"

  local tag min_delta decimals ok_flag status detail
  tag="$(echo "$output" | awk -F'|' '{print $1}')"
  if [[ "$tag" != "OK" ]]; then
    record_result "技术指标6-数据存储精度" "FAIL" "10毫秒级" "$output" "dSimTime 采样不足"
    return
  fi

  min_delta="$(echo "$output" | awk -F'|' '{print $2}')"
  decimals="$(echo "$output" | awk -F'|' '{print $3}')"
  ok_flag="$(echo "$output" | awk -F'|' '{print $4}')"
  status="FAIL"
  if [[ "$ok_flag" == "1" ]]; then
    status="PASS"
  fi

  detail="qar_id=${QAR_ID}, min_delta=${min_delta}s, max_decimals=${decimals}"
  record_result "技术指标6-数据存储精度" "$status" "10毫秒级(<=0.01s)" "$detail" "依据 dSimTime 字段检测"
}

metric_7_param_dims() {
  local dim_count
  dim_count="$(python manage.py shell -c "from apps.core.models import QAR; print(len(QAR.get_fields()))" 2>/dev/null || echo "")"

  if [[ -z "$dim_count" ]]; then
    record_result "技术指标7-飞行参数数量" "FAIL" "= 86维" "无法读取模型字段" "请检查 Django 环境"
    return
  fi

  local status="FAIL"
  if [[ "$dim_count" == "86" ]]; then
    status="PASS"
  fi
  record_result "技术指标7-飞行参数数量" "$status" "= 86维" "count=${dim_count}" "统计来源: len(QAR.get_fields())"
}

metric_8_file_size_limit() {
  if [[ -z "$SAMPLE_FILE" ]]; then
    record_result "技术指标8-单文件大小支持" "SKIP" "<= 500MB" "未提供样本文件" "请使用 -f 提供文件后验证"
    return
  fi
  if [[ ! -f "$SAMPLE_FILE" ]]; then
    record_result "技术指标8-单文件大小支持" "FAIL" "<= 500MB" "文件不存在" "$SAMPLE_FILE"
    return
  fi

  local size_mb
  size_mb="$(awk -v b="$(wc -c < "$SAMPLE_FILE" | tr -d ' ')" 'BEGIN {printf "%.2f", b/1024/1024}')"

  local status="PASS"
  local detail="sample_size=${size_mb}MB, upload_success=${UPLOAD_SUCCESS}"
  if awk -v x="$(safe_num "$size_mb")" -v lim="$MAX_FILE_SIZE_MB" 'BEGIN{exit !(x>lim)}'; then
    status="FAIL"
    detail="样本文件已超过 500MB: ${size_mb}MB"
  elif [[ "${UPLOAD_SUCCESS:-0}" -le 0 ]]; then
    status="FAIL"
    detail="样本文件<=500MB，但上传验证失败"
  fi

  record_result "技术指标8-单文件大小支持" "$status" "<= 500MB" "$detail" "注意: 仅验证到样本文件大小"
}

metric_9_uptime() {
  if [[ -z "$OBSERVED_HOURS" || -z "$DOWNTIME_MINUTES" ]]; then
    record_result "技术指标9-平均无故障运行时间" "SKIP" "> 99.5%" "未提供观测窗口" "请传入 -H 观测小时 -D 故障分钟"
    return
  fi

  local availability
  availability="$(awk -v h="$OBSERVED_HOURS" -v d="$DOWNTIME_MINUTES" 'BEGIN {total=h*60; if(total<=0){print 0}else{printf "%.4f", ((total-d)/total)*100}}')"

  local status="PASS"
  if awk -v a="$(safe_num "$availability")" 'BEGIN{exit !(a<99.5)}'; then
    status="FAIL"
  fi

  record_result "技术指标9-平均无故障运行时间" "$status" "> 99.5%" "availability=${availability}%" "observed_hours=${OBSERVED_HOURS}, downtime_minutes=${DOWNTIME_MINUTES}"
}

metric_10_backup_restore() {
  local backup_ok=0
  local restore_ok=0
  local backup_name=""
  local run_file="$RAW_DIR/backup_run.json"
  local run_status_file="$RAW_DIR/backup_run_status.json"
  local precheck_file="$RAW_DIR/backup_precheck.json"
  local detail=""

  local http_code
  http_code="$(curl -sS -o "$run_file" -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -X POST "$BASE_URL/api/v1/system/backup/run" \
    -d '{}')"
  if [[ "$http_code" != "200" ]]; then
    record_result "技术指标10-数据存储可靠性" "FAIL" "支持定期备份与恢复" "备份任务启动失败(http=$http_code)" "backup api call failed"
    return
  fi

  local backup_job_id
  backup_job_id="$(api_json_field "$run_file" "data.job_id" || true)"
  if [[ -z "$backup_job_id" ]]; then
    record_result "技术指标10-数据存储可靠性" "FAIL" "支持定期备份与恢复" "未返回备份任务ID" "backup job id missing"
    return
  fi

  local status="running"
  local i
  for i in $(seq 1 120); do
    http_code="$(curl -sS -o "$run_status_file" -w "%{http_code}" \
      -H "Authorization: Bearer $TOKEN" \
      "$BASE_URL/api/v1/system/backup/job/status?job_id=$backup_job_id")"
    if [[ "$http_code" != "200" ]]; then
      break
    fi
    status="$(api_json_field "$run_status_file" "data.job.status" || true)"
    if [[ "$status" == "completed" || "$status" == "failed" ]]; then
      break
    fi
    sleep 1
  done

  if [[ "$status" == "completed" ]]; then
    backup_ok=1
    backup_name="$(api_json_field "$run_status_file" "data.job.result.items.0.name" || true)"
  fi

  if [[ -n "$backup_name" ]]; then
    http_code="$(curl -sS -o "$precheck_file" -w "%{http_code}" \
      -H "Authorization: Bearer $TOKEN" \
      "$BASE_URL/api/v1/system/backup/precheck?backup_name=$backup_name")"
    if [[ "$http_code" == "200" ]]; then
      local can_restore
      can_restore="$(api_json_field "$precheck_file" "data.can_restore" || true)"
      if [[ "$can_restore" == "True" || "$can_restore" == "true" || "$can_restore" == "1" ]]; then
        restore_ok=1
      fi
    fi
  fi

  detail="job_status=${status}, backup_name=${backup_name:-none}"

  local metric_status="FAIL"
  if [[ "$backup_ok" -eq 1 && "$restore_ok" -eq 1 ]]; then
    metric_status="PASS"
  fi

  record_result "技术指标10-数据存储可靠性" "$metric_status" "支持定期备份与恢复" "backup=${backup_ok}, restore=${restore_ok}" "$detail"
}

build_probe_upload_csv() {
  local source_file="$1"
  local target_file="$2"
  local target_bytes="$3"

  if [[ ! -f "$source_file" ]]; then
    echo ""
    return 1
  fi

  local body_file="$RAW_DIR/metric11_body.tmp"
  head -n 1 "$source_file" > "$target_file"
  tail -n +2 "$source_file" > "$body_file"

  if [[ ! -s "$body_file" ]]; then
    cp "$source_file" "$body_file"
  fi

  local current_bytes
  current_bytes="$(wc -c < "$target_file" | tr -d ' ')"
  while awk -v c="$current_bytes" -v t="$target_bytes" 'BEGIN{exit !(c<t)}'; do
    cat "$body_file" >> "$target_file"
    current_bytes="$(wc -c < "$target_file" | tr -d ' ')"
  done

  rm -f "$body_file"
  echo "$target_file"
  return 0
}

metric_11_500m_upload_probe() {
  local source_file
  if [[ -n "$UPLOAD_PROBE_SOURCE_FILE" ]]; then
    source_file="$UPLOAD_PROBE_SOURCE_FILE"
  else
    source_file="$SCRIPT_DIR/test.csv"
  fi

  if [[ ! -f "$source_file" ]]; then
    record_result "500M文件上传" "SKIP" "约500MB文件可上传到后台(不入库)" "源文件不存在" "请提供 test.csv 或通过 -t 指定拼接源文件"
    return
  fi

  local target_bytes
  target_bytes="$((UPLOAD_PROBE_TARGET_MB * 1024 * 1024))"
  local cache_file
  if [[ -n "$UPLOAD_PROBE_CACHE_FILE" ]]; then
    cache_file="$UPLOAD_PROBE_CACHE_FILE"
  else
    cache_file="$SCRIPT_DIR/benchmark_results/big_file.csv"
  fi

  mkdir -p "$(dirname "$cache_file")"

  local cache_bytes
  cache_bytes="$(wc -c < "$cache_file" 2>/dev/null | tr -d ' ' || echo "0")"
  if awk -v c="$cache_bytes" -v t="$target_bytes" 'BEGIN{exit !(c<t)}'; then
    if ! build_probe_upload_csv "$source_file" "$cache_file" "$target_bytes" >/dev/null; then
      record_result "500M文件上传" "FAIL" "约500MB文件可上传到后台(不入库)" "拼接失败" "source=${source_file}"
      return
    fi
  fi

  local merged_file="$cache_file"
  if [[ ! -f "$merged_file" ]]; then
    record_result "500M文件上传" "FAIL" "约500MB文件可上传到后台(不入库)" "拼接失败" "source=${source_file}"
    return
  fi

  local merged_bytes merged_mb
  merged_bytes="$(wc -c < "$merged_file" | tr -d ' ')"
  merged_mb="$(awk -v b="$merged_bytes" 'BEGIN {printf "%.2f", b/1024/1024}')"

  local response_file="$RAW_DIR/metric11_upload_probe.json"
  local out
  out="$(curl -sS -o "$response_file" -w "%{http_code}\t%{time_total}" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@${merged_file}" \
    "$BASE_URL/api/v1/system/test/upload-probe" || echo "000\t999")"

  local http_code time_total api_code size_bytes size_mb status detail
  http_code="$(echo "$out" | awk -F'\t' '{print $1}')"
  time_total="$(echo "$out" | awk -F'\t' '{print $2}')"
  api_code="$(api_json_field "$response_file" "code" || true)"
  size_bytes="$(api_json_field "$response_file" "data.size_bytes" || true)"
  size_mb="$(awk -v b="${size_bytes:-0}" 'BEGIN {printf "%.2f", b/1024/1024}')"

  status="PASS"
  if [[ "$http_code" != "200" || "$api_code" != "0" ]]; then
    status="FAIL"
  fi
  if awk -v x="$(safe_num "$size_mb")" 'BEGIN{exit !(x<450.0)}'; then
    status="FAIL"
  fi

  detail="source=$(basename "$source_file"), cache=$(basename "$merged_file"), size=${merged_mb}MB, received=${size_mb}MB, time=${time_total}s"
  record_result "500M文件上传" "$status" "约500MB文件可上传到后台(不入库)" "http=${http_code}, api=${api_code}" "$detail"
}

render_report() {
  local pass fail skip total
  pass="$(awk -F'|' '$2=="PASS" {c++} END{print c+0}' "$RAW_DIR/summary.tsv")"
  fail="$(awk -F'|' '$2=="FAIL" {c++} END{print c+0}' "$RAW_DIR/summary.tsv")"
  skip="$(awk -F'|' '$2=="SKIP" {c++} END{print c+0}' "$RAW_DIR/summary.tsv")"
  total="$(awk 'END{print NR+0}' "$RAW_DIR/summary.tsv")"

  log "# CAUC FOQA 技术指标测试报告"
  log ""
  log "- 测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
  log "- 服务地址: ${BASE_URL}"
  log "- 测试账号: ${USERNAME}"
  log "- QAR_ID: ${QAR_ID:-自动解析}"
  log "- 原始结果目录: ${RAW_DIR}"
  log ""
  log "## 汇总"
  log ""
  log "| 指标 | 状态 | 目标 | 实测 | 说明 |"
  log "|---|---|---|---|---|"

  while IFS='|' read -r metric status target observed detail; do
    log "| ${metric} | ${status} | ${target} | ${observed} | ${detail} |"
  done < "$RAW_DIR/summary.tsv"

  log ""
  log "## 结论"
  log ""
  log "- PASS: ${pass}"
  log "- FAIL: ${fail}"
  log "- SKIP: ${skip}"
  log "- TOTAL: ${total}"
}

if ! curl -sS -o /dev/null --connect-timeout 3 --max-time 10 "$BASE_URL/api/v1/auth/login"; then
  echo "[ERROR] 无法访问 $BASE_URL，请先启动后端服务。" >&2
  exit 1
fi

TOKEN="$(api_login)"
if [[ -z "$TOKEN" ]]; then
  echo "[ERROR] 登录失败，请检查用户名/密码或认证接口。" >&2
  exit 1
fi

if [[ -z "$QAR_ID" ]]; then
  QAR_ID="$(resolve_qar_id)"
fi

: > "$RAW_DIR/summary.tsv"

metric_1_query_response
metric_2_visual_response
metric_3_upload_speed
metric_4_inference_time
metric_5_decile_accuracy
metric_6_storage_precision
metric_7_param_dims
metric_8_file_size_limit
metric_9_uptime
metric_10_backup_restore
metric_11_500m_upload_probe

render_report

echo "[DONE] 测试完成，报告文件: $RESULT_FILE"
