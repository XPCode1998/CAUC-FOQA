# CAUC FOQA 飞行数据存储管理及可视化分析系统

## 1. 项目定位

CAUC FOQA 是一个面向飞行运行质量保障场景的前后端分离系统，覆盖飞行数据接入、数据治理、可视化分析、风险识别与插补建模等关键环节。

系统强调三件事：
- 数据全流程可追踪：上传、预览、监测、修复都有统一入口。
- 风险分析可解释：通过阈值策略与超限区间输出定位风险来源。
- 模型能力可落地：支持插补训练、流式训练反馈、修复结果回写。

### 1.1 设计目标

为保证系统从原型走向可落地工程，设计目标定义如下：

- 业务目标：围绕 QAR 数据管理、可视化、风险识别、质量治理形成闭环，支撑飞行运行质量保障场景。
- 数据目标：建立“原始数据-治理数据-应用数据”分层机制，确保数据可追溯、可审计、可回溯。
- 功能目标：统一完成数据上传、预览编辑、参数配置、风险分析、风险预警、缺失值插补与训练管理。
- 架构目标：采用前后端分离与服务分层，降低模块耦合，支持独立演进和按需扩展。
- 可解释性目标：风险结论可回溯到具体参数、阈值、时间区间与超限持续时长。
- 可靠性目标：关键流程具备失败重试、备份恢复、恢复后健康校验能力，保障运行连续性。
- 安全性目标：通过认证鉴权、访问控制、操作日志等机制确保数据与操作安全。

### 1.2 验收指标（建议）

以下指标可作为课程设计/项目验收阶段的量化参考：

- 可用性：核心业务链路（上传->分析->预警->修复）可端到端跑通。
- 性能：中等规模数据集可在可接受时延内完成上传、查询与图形渲染。
- 正确性：风险分析结果与阈值策略一致，关键统计结果可复核。
- 可追踪性：关键数据处理步骤可查询来源、处理时间与处理责任。
- 稳定性：异常中断后可通过备份恢复机制回到可用状态。
- 可维护性：前后端模块边界清晰，新增页面或接口不破坏现有主流程。

## 2. 功能总览（按前端页面目录划分）

### 2.1 认证入口（LoginView）
- 页面文件：frontend/src/views/LoginView.vue
- 路由：/login、/register、/reset-password
- 功能：统一登录页承载注册、登录、重置密码，并在登录后恢复用户会话。

### 2.2 QAR 数据管理目录

#### 数据管理（DataUploadView）
- 页面文件：frontend/src/views/DataUploadView.vue
- 路由：/data-upload
- 功能：原始数据上传、上传后确认入库与数据管理入口汇总。

#### 数据预览（DataPreviewView）
- 页面文件：frontend/src/views/DataPreviewView.vue
- 路由：/data-preview
- 功能：按 QAR 分页预览数据，支持字段级编辑并同步更新关联统计。

#### 参数管理（ThresholdConfigView）
- 页面文件：frontend/src/views/ThresholdConfigView.vue
- 路由：/threshold-config
- 功能：维护参数阈值与参数维度配置，支撑监测与风险判定。

### 2.3 QAR 数据可视化目录

#### 飞行参数可视化（FlightPreviewView）
- 页面文件：frontend/src/views/FlightPreviewView.vue
- 路由：/flight-preview
- 功能：展示飞行参数曲线、关键统计和轨迹信息。

#### 飞行过程回放（FlightReplayView）
- 页面文件：frontend/src/views/FlightReplayView.vue
- 路由：/flight-replay
- 功能：按时间序列回放飞行过程，辅助复盘异常片段。

### 2.4 飞行风险监测目录

#### QAR 超限分析（FlightRiskView）
- 页面文件：frontend/src/views/FlightRiskView.vue
- 路由：/flight-risk-overlimit
- 功能：按阈值策略输出超限区间、严重级别与持续时长。

#### 飞行风险预警（FlightRiskWarningView）
- 页面文件：frontend/src/views/FlightRiskWarningView.vue
- 路由：/flight-risk-warning
- 功能：展示流式风险识别结果，用于实时风险预警与处置。

### 2.5 QAR 质量管理目录

#### 模型训练管理（ModelTrainingView）
- 页面文件：frontend/src/views/ModelTrainingView.vue
- 路由：/model-training
- 功能：插补模型训练、训练流式反馈、训练停止控制。

#### QAR 缺失值填充（DataImputationView）
- 页面文件：frontend/src/views/DataImputationView.vue
- 路由：/data-imputation
- 功能：缺失值插补预览、修复执行与修复流式反馈。

#### 数据监测（DataMonitorView）
- 页面文件：frontend/src/views/DataMonitorView.vue
- 路由：/data-monitor
- 功能：缺失率与飞行状态统计监测，用于质量诊断。

### 2.6 系统可靠性与运维保障目录

#### 系统可靠性与运维保障（SystemMetricsView）
- 页面文件：frontend/src/views/SystemMetricsView.vue
- 路由：/system-metrics
- 功能：集中展示测评指标（查询/可视化/上传性能）折线图、备份版本列表、即时备份、恢复到指定版本、恢复前健康检查、恢复后自动探活校验、操作日志。

## 3. 设计架构

### 3.1 技术栈
- 后端：Django 5.1、Django REST framework、SimpleJWT。
- 前端：Vue 3、Vite、Vue Router、Pinia、Element Plus。
- 可视化：ECharts、ECharts GL、Cesium。
- 数据与算法：Pandas、NumPy、PyTorch。

### 3.2 分层设计

```text
浏览器
	-> Vue3 前端（页面路由、状态管理、图形可视化）
	-> Django API 网关层（/api/v1）
	-> 业务服务层（飞行分析 / 数据管理 / 插补代理）
	-> 数据模型层（QAR、QAR_Summary、QAR_Mask 等）
	-> 数据存储
```

### 3.3 后端模块划分

```text
apps/
	api/                # API 入口与服务编排
	core/               # 核心模型、缺失掩码与监测策略
	authentication/     # 认证相关模型
config/               # Django settings/urls/asgi/wsgi
```

### 3.4 前端模块划分

```text
frontend/src/
	api/                # Axios 请求封装与接口调用
	stores/             # Pinia 状态管理（认证、QAR 上下文）
	router/             # 路由与登录守卫
	views/              # 业务页面
	components/         # 通用组件
	services/           # 流式训练等业务服务
```

### 3.5 路由与部署策略
- API 前缀统一为 /api/v1。
- Django 仅提供 API 与 /admin 管理入口。
- 非 /api 与 /admin 请求由 Django 重定向至前端地址，便于前后端独立部署并保持单页应用路由可达。

## 4. 代码结构

```text
CAUC_FOQA/
├─ apps/
├─ config/
├─ frontend/
├─ manage.py
├─ requirements.txt
├─ start_backend.sh
├─ start_frontend.sh
├─ stop_frontend_backend.sh
└─ README_FRONTEND_BACKEND_SPLIT.md
```

## 5. 快速使用

### 5.1 环境要求
- Python 3.10 及以上。
- Node.js 18 及以上，npm 9 及以上。
- Linux/macOS（Windows 建议 WSL）。
- Conda 可选（启动脚本默认支持 conda 环境激活）。

### 5.2 后端启动

方式一：使用脚本（推荐）

```bash
bash start_backend.sh
```

可覆盖默认参数：

```bash
CONDA_SH=/home/ubuntu/anaconda3/etc/profile.d/conda.sh \
CONDA_ENV=pytorch_django_env \
BACKEND_HOST=0.0.0.0 \
BACKEND_PORT=8000 \
bash start_backend.sh
```

方式二：手动启动

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### 5.3 前端启动

方式一：使用脚本（推荐）

```bash
bash start_frontend.sh
```

可覆盖默认参数：

```bash
FRONTEND_HOST=0.0.0.0 FRONTEND_PORT=5173 bash start_frontend.sh
```

方式二：手动启动

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 5.4 停止服务

```bash
bash stop_frontend_backend.sh
```

默认按端口关闭：
- 后端 8000
- 前端 5173

### 5.5 访问地址
- 前端开发地址：http://127.0.0.1:5173
- 后端 API 基址：http://127.0.0.1:8000/api/v1
- Django 管理后台：http://127.0.0.1:8000/admin

### 5.6 使用 Nginx 统一反向代理（推荐）

项目已提供 Nginx 配置模板：`nginx/cauc_foqa.conf`。

1. 启动前后端服务（维持当前端口）

```bash
bash start_backend.sh
bash start_frontend.sh
```

2. 复制配置到 Nginx 站点目录

```bash
sudo cp nginx/cauc_foqa.conf /etc/nginx/conf.d/cauc_foqa.conf
```

3. 校验并重载 Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

4. 通过 Nginx 访问

- 站点入口：http://服务器IP/
- API 基址：http://服务器IP/api/v1

说明：
- 配置已包含 `/api/`、`/admin/`、`/static/`、`/media/` 反向代理。
- 配置已兼容 Vite HMR（WebSocket）与流式接口（SSE，关闭代理缓冲）。

## 6. 页面与业务流

### 6.1 已实现页面
- 登录页（含注册、重置密码入口）。
- 数据上传页。
- 数据预览页。
- 数据监测页。
- 飞行预览页。
- 飞行回放页。
- 风险超限页。
- 风险预警页。
- 阈值配置页。
- 数据插补页。
- 模型训练页。
- 系统可靠性与运维保障页。

### 6.2 推荐操作流程
1. 登录系统。
2. 在数据上传页导入原始数据。
3. 在数据预览页检查并按需修正字段。
4. 在数据监测页查看缺失与状态统计。
5. 在阈值配置页维护监测区间。
6. 在飞行预览/回放/风险页面开展分析。
7. 在数据插补与模型训练页面执行修复与训练。
8. 在系统可靠性与运维保障页面查看测评结果并执行备份/恢复演示。

## 7. API 概览

### 7.1 认证类
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/auth/reset-password
- POST /api/v1/auth/refresh
- GET /api/v1/auth/me

### 7.2 飞行分析类
- GET /api/v1/flight/overview
- GET /api/v1/flight/charts
- GET /api/v1/flight/trajectory
- GET /api/v1/flight/replay
- GET /api/v1/flight/risk
- GET /api/v1/flight/risk/stream
- GET /api/v1/flight/risk/stream/by-qar

### 7.3 数据管理类
- GET /api/v1/data/qar-ids
- GET /api/v1/data/qar-management
- GET/PUT /api/v1/data/preview
- POST /api/v1/data/upload-raw
- POST /api/v1/data/upload-raw/finalize
- GET/DELETE /api/v1/data/qar
- GET/PUT /api/v1/data/thresholds
- GET/PUT /api/v1/data/parameter-dimensions

### 7.4 数据插补类
- GET /api/v1/data/imputation/preview
- POST /api/v1/data/imputation/repair
- GET /api/v1/data/imputation/train/hyperparams
- GET /api/v1/data/imputation/models
- POST /api/v1/data/imputation/train
- GET /api/v1/data/imputation/stream/train
- POST /api/v1/data/imputation/stream/train/stop
- GET /api/v1/data/imputation/stream/repair
- GET /api/v1/data/imputation/stream/repair/by-qar

### 7.5 系统可靠性与运维保障类
- GET /api/v1/system/metrics
- GET /api/v1/system/backup/list
- POST /api/v1/system/backup/run
- GET /api/v1/system/backup/precheck
- POST /api/v1/system/backup/restore
- GET /api/v1/system/ops/logs
- POST /api/v1/system/test/run
- GET /api/v1/system/test/status

## 8. 配置说明

### 8.1 后端启动脚本变量
- CONDA_SH：conda 初始化脚本路径。
- CONDA_ENV：conda 环境名。
- BACKEND_HOST：后端监听地址。
- BACKEND_PORT：后端监听端口。

### 8.2 前端启动脚本变量
- FRONTEND_HOST：前端监听地址。
- FRONTEND_PORT：前端监听端口。

### 8.3 停止脚本变量
- BACKEND_PORT：要关闭的后端端口。
- FRONTEND_PORT：要关闭的前端端口。

### 8.4 数据库备份与恢复 API 变量
- BACKUP_DIR：备份输出目录，默认值为 ./backups/db。
- RETENTION_DAYS：备份保留天数，默认值为 14。
- COMPRESS_BACKUP：是否压缩，1 为压缩（默认），0 为不压缩。
- BACKUP_GZIP_LEVEL：压缩级别，默认 6（取值 1-9）。
- BACKUP_TIMEOUT_SECONDS：备份超时时间（秒），默认 1800。
- RESTORE_TIMEOUT_SECONDS：恢复导入超时时间（秒），默认 3600。

说明：当前系统默认执行“仅数据（data-only）”备份，不包含建表等结构语句；恢复时会先清空现有数据，再导入备份数据。

### 8.5 系统测评页面依赖路径
- benchmark_results/raw_*/summary.tsv：性能指标页面读取测评结果来源（由 benchmark_metrics.sh 生成）。
- backups/db：备份文件目录（可通过 BACKUP_DIR 环境变量覆盖）。
- benchmark_results/system_ops.jsonl：备份/恢复操作日志文件（系统自动写入）。

## 9. 常见问题

### 9.1 找不到 conda 初始化脚本
使用 CONDA_SH 指定实际路径后再启动：

```bash
CONDA_SH=/your/path/to/conda.sh bash start_backend.sh
```

### 9.2 前端请求失败或跨域
- 确认后端已启动且地址可访问。
- 检查前端请求基址与后端 CORS 配置是否一致。

### 9.3 端口被占用

```bash
BACKEND_PORT=8001 bash start_backend.sh
FRONTEND_PORT=5174 bash start_frontend.sh
```

### 9.4 如何配置数据库定期备份
推荐通过系统 API 触发备份任务（`POST /api/v1/system/backup/run`），并通过任务状态 API 轮询进度（`GET /api/v1/system/backup/job/status`）。

可使用前端“系统可靠性与运维保障”页面点击“立即备份”，也可由调度系统定时调用该 API。

### 9.5 如何演示“系统可靠性与运维保障”页面
1. 先启动后端与前端。
2. 如需生成测评样本，执行：

```bash
./benchmark_metrics.sh -f ./test.csv
```

3. 打开前端菜单“系统可靠性与运维保障 -> 系统可靠性与运维保障”。
4. 点击“一键测试”，系统将通过 API 自动执行数据查询响应时间、数据可视化响应时间、数据上传速度多轮测试。
5. 在页面实时查看当前轮次、最新值、AVG、P95 和状态。
6. 测试完成后，页面自动刷新性能趋势图。
7. 点击“立即备份”验证自动备份能力。
8. 在“备份版本列表”选择任一版本，先执行“恢复前健康检查”。
9. 通过检查后输入 RESTORE 执行恢复（高风险操作）。
10. 在页面查看“恢复后自动探活校验”结果，并在“运维操作日志”核验备份与恢复记录。

## 10. 说明
- 当前仓库以工程说明和开发启动为主。
- 若用于生产部署，建议补充 Nginx/Gunicorn、静态资源发布与日志监控方案。
