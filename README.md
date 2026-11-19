# 低代码表单生成 Agent（LangGraph + PydanticAI + LangChain + FastAPI）

一套三合一的 Agent 服务：根据自然语言需求，结合规范知识库（RAG）生成强类型表单 Schema，
规则校验不合格自动循环重生成，可选人工审批，全部由 FastAPI 对外封装成接口。

## 一、框架分工

| 框架           | 职责                                                                      | 代码位置                           |
| -------------- | ------------------------------------------------------------------------- | ---------------------------------- |
| **PydanticAI** | 单节点 Agent，输出经 Pydantic 强校验的 `FormSchema`，类型不合法会失败重试 | `app/agents/form_agent.py`         |
| **LangChain**  | 规范文档加载、检索上下文（Embeddings 向量 / 关键词回退）                  | `app/rag/retriever.py`             |
| **LangGraph**  | 状态机编排：检索→生成→校验→条件分支循环→审批节点                          | `app/graph/workflow.py`            |
| **FastAPI**    | 对外 HTTP 接口封装、请求响应模型                                          | `app/api/routes.py`、`app/main.py` |

## 二、流程

```
用户需求
  └─ retrieve（LangChain RAG 召回规范）
       └─ generate（PydanticAI 生成 FormSchema）
            └─ check（规则校验）
                 ├─ 不合格 & 未超上限 ──▶ 回到 generate（LangGraph 循环）
                 └─ 合格 ──▶ approval
                              ├─ 需审批 ──▶ pending_approval（等待人工接口）
                              └─ 免审批 ──▶ auto_passed
```

## 三、目录结构

```
form-agent/
├── requirements.txt
├── .env.example
├── data/specs/form-spec.md      # RAG 规范文档（可自行增补 .md/.txt）
└── app/
    ├── main.py                  # FastAPI 入口
    ├── config.py                # 环境变量配置
    ├── models.py                # Pydantic 模型 / 接口入参出参
    ├── agents/form_agent.py     # PydanticAI 节点
    ├── rag/retriever.py         # LangChain RAG 检索
    ├── graph/state.py          # LangGraph 状态定义
    ├── graph/workflow.py        # 节点 + 条件边 + 运行态 + 审批
    └── api/routes.py            # 接口封装
```

## 四、安装与启动

> 需要 **Python 3.10+**（`pydantic-ai` / `langchain` 新版已不支持 3.9）。
> 本机若只有系统 Python 3.9，可先用 `uv` 拉一个：`uv python install 3.12`。

```bash
# 1. 进入目录
cd form-agent

# 2. 建虚拟环境（用 uv 指定版本；本机已有 3.10+ 时也可用 python -m venv .venv）
uv venv --python 3.12 .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# 3. 安装依赖
uv pip install -r requirements.txt    # 未用 uv 时：pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env   # 填入 OPENAI_API_KEY；不填也能跑（走本地规则兜底）

# 5. 启动
uvicorn app.main:app --reload --port 8000
```

接口文档：`http://localhost:8000/docs`

### 4.1 接入 OpenAI 兼容网关

`OPENAI_BASE_URL` 决定实际调用的服务，除 OpenAI 外也可以指向国内兼容网关，例如智谱：

| 变量                     | 智谱取值                               |
| ------------------------ | -------------------------------------- |
| `OPENAI_BASE_URL`        | `https://open.bigmodel.cn/api/paas/v4` |
| `MODEL_NAME`             | `glm-4-flash`                          |
| `OPENAI_EMBEDDING_MODEL` | `embedding-3`                          |

RAG 的 embedding 默认复用同一组 key 与 `base_url`，换网关时只需改这三项。
`glm-4-flash` 有几处输出习惯差异（如把 `label` 写成 `title`、中文词间插空格），代码已做兼容，详见 [docs/prompt-spec.md](./docs/prompt-spec.md)。

## 五、接口一览

### 1. 生成表单

`POST /api/form/generate`

```json
{
  "requirement": "用户注册表单，包含姓名、手机号、城市",
  "need_approval": true
}
```

返回：

```json
{
  "run_id": "a1b2c3d4e5f6",
  "status": "pending_approval",
  "form_schema": {
    "title": "用户注册表单",
    "fields": [
      { "name": "name", "label": "姓名", "type": "text", "required": true },
      { "name": "phone", "label": "手机号", "type": "tel", "required": true }
    ]
  },
  "message": "等待人工审批",
  "retries": 0,
  "steps": [
    {
      "node": "retrieve",
      "at": "18:05:24",
      "summary": "vector 检索命中 3 条规范，最相关：可选字段类型（前端已全部支持）",
      "ok": null,
      "round": null
    },
    {
      "node": "generate",
      "at": "18:05:43",
      "summary": "第 1 轮生成（LLM）：15 个字段",
      "ok": null,
      "round": 1
    },
    {
      "node": "check",
      "at": "18:05:43",
      "summary": "校验通过",
      "ok": true,
      "round": 1
    },
    {
      "node": "approval",
      "at": "18:05:43",
      "summary": "等待人工审批",
      "ok": null,
      "round": null
    }
  ]
}
```

`retries` 是校验失败后重新生成的次数（一次通过为 0）；`steps` 按实际执行顺序记录每个节点的结论，校验失败回到 `generate` 时会多出第 2 轮的 `generate` / `check`。

### 2. 查询任务

`GET /api/form/run/{run_id}`

### 3. 人工审批

`POST /api/form/approval/{run_id}`

```json
{ "approved": true, "comment": "字段齐全，通过" }
```

### 4. 健康检查

`GET /health`

## 六、校验规则（可在 `workflow._validate` 扩展）

- 标题、字段列表非空；
- 字段标识唯一；
- 需求提到“手机/电话”时，必须包含 `phone` 字段；
- 不合格由 LangGraph 循环回到生成节点，上限 `MAX_RETRY`。

## 七、无 LLM 密钥说明

未配置 `OPENAI_API_KEY` 时，`FormAgent` 走本地关键词规则兜底生成，`Retriever` 走关键词检索，
整条链路（含循环、审批）仍可跑通，便于本地联调与演示；接入真实密钥后自动切换到 LLM 生成与向量检索。

## 八、可扩展点

- 运行态 `_RUN_STORE` 目前是内存字典，生产可换 Redis / DB / LangGraph Checkpointer 持久化断点；
- `_validate` 可接入更多业务规则、Schema 版本校验；
- RAG 文档可替换为企业知识库、向量数据库（FAISS / Milvus 等）；
- 审批节点可接入飞书/邮件通知与回调。

## 九、前后端分层（新增模块）

```
form-agent/           # 本目录：Python AI 服务（LangGraph 编排 + PydanticAI + LangChain），未改动
form-gateway-nest/    # 新增：NestJS 网关，统一对外入口、参数校验、转发到 AI 服务
form-web-react/       # 新增：React + Ant Design 前端，需求输入 / 任务状态 / 人工审批 / 表单预览
```

调用链：`React(5173) → NestJS 网关(3000，本机冲突时用 3111) → FastAPI Agent(8000)`

### 9.1 NestJS 网关（`form-gateway-nest`）

| 方法 | 路径                        | 转发到                             |
| ---- | --------------------------- | ---------------------------------- |
| POST | `/api/form/generate`        | `POST /api/form/generate`          |
| GET  | `/api/form/run/:runId`      | `GET /api/form/run/{run_id}`       |
| POST | `/api/form/approval/:runId` | `POST /api/form/approval/{run_id}` |

```bash
cd form-gateway-nest
npm install
cp .env.example .env        # AI_AGENT_BASE_URL 指向 Python 服务
npm run start:dev           # http://localhost:3000
```

- `src/form/form.service.ts` 统一转发并用 `HttpException` 包装上游错误，前端不会拿到裸 500；
- 网关当前不含鉴权，需要时在 `src/main.ts` 挂 Guard（JWT 等）即可；
- `ValidationPipe({ whitelist: true })` 会剔除未声明字段。

### 9.2 React 前端（`form-web-react`）

```bash
cd form-web-react
npm install
cp .env.example .env        # VITE_API_BASE_URL 指向网关
npm run dev                 # http://localhost:5173
```

- `FormGenerator`：需求输入 → 发起生成（接口同步返回终态）→ 每 1.5s 轮询仅作兜底刷新；
- `TaskInfo`：状态标签、生成轮次与重试次数、LangGraph 节点执行时间线（检索 / 生成 / 校验 / 审批，含每步结论）、审批按钮（通过 / 驳回）；
- `FormPreview`：按 `type` 渲染控件——`text / tel / email` 用 Input，`textarea`、`number`、`date`、`select`（读取 `options`）。

### 9.3 字段契约（已与 Python 服务对齐）

| 项          | 取值                                                                     |
| ----------- | ------------------------------------------------------------------------ |
| 生成入参    | `requirement`、`need_approval`                                           |
| 返回 Schema | `form_schema`（含 `title`、`fields[]`）                                  |
| 审批入参    | `approved`、`comment`                                                    |
| 状态        | `pending` / `pending_approval` / `auto_passed` / `approved` / `rejected` |

### 9.4 完整启动顺序

macOS 一键启动（推荐，自动串起三个服务并做健康检查）：

```bash
./scripts/start-local-mac.sh          # 普通模式，改代码需手动重启
RELOAD=1 ./scripts/start-local-mac.sh # 开发模式：agent --reload、网关 nest --watch
```

手动分别启动：

1. `uvicorn app.main:app --reload --port 8000`（本目录）
2. `cd form-gateway-nest && npm run start:dev`（3000）
3. `cd form-web-react && npm run dev`（5173，浏览器打开）

> 本机 3000 常被其他项目占用，启动脚本默认把网关起在 **3111**，并已同步改好 `form-web-react/vite.config.ts` 的 `/api` 代理；手动启动若改端口，记得一起改代理。

### 9.5 本轮补充的验证结果

| 模块                         | 验证方式                                                        | 结果                                                                                                                                                                    |
| ---------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `form-gateway-nest`          | `npm install` + `npm run build`（`nest build` → tsc）           | 通过，产出 `dist/main.js`                                                                                                                                               |
| `form-gateway-nest`          | 启动网关（端口 3010）+ 临时 stub 上游（8010）实测四个路径       | 通过：`generate` 返回 `form_schema`、`run` 查询、`approval` 通过/驳回、缺 `requirement` 与非法 `approved` 类型均返回 400                                                |
| `form-gateway-nest`          | 上游未启动时请求 `generate`                                     | 返回 502 且提示“无法连接 AI 服务”，不是裸 500                                                                                                                           |
| `form-web-react`             | `npm install` + `npm run build`（`tsc --noEmit && vite build`） | 通过，`dist` 产物可 `preview` 打开（HTTP 200）                                                                                                                          |
| Python AI 服务 ↔ 网关 ↔ 前端 | 端到端联调（本机三服务同源链路）                                | 通过：`POST /api/form/generate` 返回 201，需求中的 4 个字段全部生成；智谱 `glm-4-flash` 真实生成，`embedding-3` 向量检索生效（`/api/form/rag/status` 为 `mode=vector`） |

> `node_modules` 与 `dist` 为运行/构建产物，已在 `.gitignore` 中忽略；重新 `npm install` / `npm run build` 即可恢复。

## 十、部署

完整方案对比与落地步骤见 [DEPLOY.md](./DEPLOY.md)，仓库里已备好部署产物：

| 文件                                       | 用途                                    |
| ------------------------------------------ | --------------------------------------- |
| `Dockerfile`                               | Python agent 镜像（根目录即构建上下文） |
| `form-gateway-nest/Dockerfile`             | NestJS 网关镜像（多阶段构建）           |
| `form-web-react/Dockerfile` + `nginx.conf` | 前端构建 + nginx 托管并反代 `/api`      |
| `docker-compose.yml`                       | 三个服务一键起，仅 web 暴露 80          |

要点：三个服务都是常驻进程，云函数/纯静态托管无法承载；agent 的 `_RUN_STORE` 在进程内存里，
所以 **uvicorn 单 worker、副本数固定 1**，要扩容得先换 Redis/DB 存运行态。
推荐单台 2C4G Linux 服务器 + `docker compose up -d --build`，单域名同源无跨域。
