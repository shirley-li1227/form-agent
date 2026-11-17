# 部署指南（三服务原样保留，不改 NestJS）

> 验证范围：`docker-compose.yml` 结构已用 YAML 解析器校验、前端同源构建（`VITE_API_BASE_URL=""`）已跑通；
> **三个镜像未在开发机上实际构建**（本机无 Docker）。首次上线先在一台测试机 `docker compose up -d --build` 跑一遍再切正式环境。

## 一、先看这个项目对部署环境的硬要求

当前形态是 **三个常驻进程**：

```
浏览器 → web(nginx, 静态+反代) → gateway(NestJS, 3000) → agent(Python FastAPI, 8000) → LLM API
```

由此得出两条筛选条件：

1. **必须能跑常驻进程**：NestJS 是有路由和依赖注入的 HTTP 服务，Python 侧是 LangGraph 编排 + 进程内运行态，两者都不能塞进「一个函数一个入口」的云函数；
2. **agent 只能单进程**：`app/graph/workflow.py` 里的 `_RUN_STORE` 是**进程内内存字典**，一旦开多 worker 或多副本，`/api/form/run/{run_id}` 会打到别的实例上直接 404。所以部署时 `uvicorn --workers 1`、副本数固定为 1；要横向扩容必须先换 Redis/DB 存运行态。

## 二、方案对比

| 方案 | 能否直接跑现状 | 适合场景 | 成本/门槛 | 主要代价 |
|---|---|---|---|---|
| **A. 单台 Linux 服务器 + docker compose**（✅ 推荐） | 可以，零改动 | demo、个人项目、小流量 | 一台轻量服务器（建议 2C4G） | 自己要会基本的 docker/防火墙操作 |
| B. 云托管（CloudBase Run / 阿里云 SAE 等容器服务） | 可以（三个服务各建一个） | 不想碰服务器、想按量付费 | 需开通付费套餐；CloudBase **体验版不含云托管** | 计费不直观、冷启动、单副本限制同样存在、调试链路长 |
| C. PaaS（Railway / Render / Fly.io） | 可以（Dockerfile 直接用） | 想最快拿到公网地址 | 有免费/低价档 | 国内访问慢、免费档会休眠、LLM 长耗时请求容易超时 |
| D. 纯云函数 / 静态托管 | **不行**（除非重写 NestJS 和 Python） | — | 免费 | 与本项目形态冲突，不在「保持现状」范围内 |
| E. 本机 + 内网穿透（cloudflared / frp） | 可以 | 只给自己或同事看 demo | 几乎零成本 | 依赖本机开机、地址不固定 |

**结论：A 最贴合。** 三个服务塞进一台服务器的一个 compose 文件，单域名、无跨域、构建一次就能反复 `up -d`；以后想换云厂商，把同一份 `docker-compose.yml` 拷过去即可，不锁定平台。

## 三、方案 A 落地步骤

### 1. 准备机器

- 规格：**2C4G 起**（agent 镜像要装 langchain/langgraph/numpy，2G 机器上 `docker build` 可能被 OOM kill）；
- 系统：Ubuntu 22.04 / Debian 12；
- 安全组只放行 **22、80、443**（3000 和 8000 不对公网开放，只在 compose 内部互通）。

> 如果只有 2C2G：在本机或 CI 上 `docker build` 好镜像推到镜像仓库，服务器只做 `docker compose pull && up -d`，别在服务器上构建。

### 2. 装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
docker compose version   # 需要 v2
```

### 3. 上传项目

```bash
git clone <你的仓库> form-agent && cd form-agent
# 或本地 scp/rsync 上传整个目录（不要带 node_modules / dist / .venv）
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

`docker-compose.yml` 会自动读取根目录 `.env` 做变量替换，需要确认三项：

| 变量 | 说明 |
|---|---|
| `OPENAI_API_KEY` | 真实密钥才走 LLM；**想先跑本地规则兜底就留空**（别留 `sk-xxxxxx` 占位符，否则会被当成已配置，调用时报错） |
| `OPENAI_BASE_URL` / `MODEL_NAME` | 换成任何 OpenAI 兼容网关都行 |
| `WEB_PORT` | 前端对外端口，默认 80；用了别的反代可改成 8080 |

### 5. 构建并启动

```bash
docker compose up -d --build
docker compose ps          # agent/gateway/web 三个都该是 Up
docker compose logs -f agent
```

首次构建 5–10 分钟（pip 装 langchain 最慢）。agent 带 healthcheck，网关会等它健康后再起。

### 6. 验证

```bash
# 1) agent 自身健康
docker compose exec agent python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"

# 2) 网关通了（返回 404 = 路由正常、任务不存在）
docker compose exec web wget -qO- http://gateway:3000/api/form/run/probe

# 3) 走完整链路（同源，经 nginx 反代）
curl -X POST http://<服务器IP>/api/form/generate \
  -H "Content-Type: application/json" \
  -d '{"requirement":"用户注册表单，包含姓名、手机号，需要收货地址","need_approval":true}'

# 4) 审批
curl -X POST http://<服务器IP>/api/form/approval/<run_id> \
  -H "Content-Type: application/json" \
  -d '{"approved":true,"comment":"字段齐全"}'
```

浏览器打开 `http://<服务器IP>/`，输入需求 → 看到表单预览 → 点通过/驳回。

### 7. 域名与 HTTPS（可选）

```bash
sudo apt install -y certbot python3-certbot-nginx
# 或者更省事：在 compose 前面再放一层 Caddy/宝塔，本机 80 只监听内网
```
最简做法：用云厂商的负载均衡/免费证书终止 TLS，回源到本机 80。

### 8. 更新与回滚

```bash
git pull && docker compose up -d --build   # 只重建有变化的服务
docker compose down                        # 停机（不删数据卷）
```

## 四、其他方案的关键差异

### B. 容器托管平台（云托管/SAE）

- 三个服务分别建：上下文分别是 `.`（agent）、`./form-gateway-nest`、`./form-web-react`；
- 端口：agent 8000、gateway 3000、web 80；
- 环境变量与 compose 里的一致，`AI_AGENT_BASE_URL` 填网关能访问到的 agent 内网地址；
- **副本数锁 1**（内存运行态），并关掉自动扩缩容，否则 `/run/{run_id}` 会丢任务。

### C. PaaS（Railway / Render）

- 直接填仓库 + Dockerfile 路径即可；前端建议单独走静态站点（Vercel/Netlify）并把 `VITE_API_BASE_URL` 指向网关公网地址；
- 注意平台默认请求超时（常见 30s），LLM 生成可能超时，需在平台上调大或改为异步任务轮询。

### D. 静态托管 + 后端一台机器（混合）

如果只想省掉 web 容器：

1. 本地 `npm run build`，把 `form-web-react/dist` 传到任意静态托管（对象存储 + CDN、CloudBase 静态托管、GitHub Pages 均可）；
2. 构建时把 `VITE_API_BASE_URL` 设为网关公网地址（如 `https://api.你的域名`）；
3. 网关的 `CORS` 已开启（`main.ts` 里 `app.enableCors()`），跨域可用；但要自己盯住这个域名，别把网关裸奔到公网。

## 五、容易踩的坑

| 现象 | 原因与处理 |
|---|---|
| 前端 404 / 空白页 | nginx 已配 `try_files ... /index.html`，若自己换 nginx 记得补这条 |
| 跨域报错 | 用 compose 的 web 反代就没有跨域；纯静态托管时必须开 CORS 并配好 `VITE_API_BASE_URL` |
| `run_id` 查不到 | agent 开了多 worker/多副本，运行态在各自内存里 → 固定单进程 |
| 生成请求 60s 超时 | nginx `proxy_read_timeout` 已设 60s；LLM 慢就调大，或把网关 `AI_AGENT_TIMEOUT_MS` 一起调大 |
| 502 无法连接 AI 服务 | 网关拿到的 `AI_AGENT_BASE_URL` 不对：compose 里是 `http://agent:8000`，容器托管里要换成实际内网地址 |
| 构建时内存不足 | 2G 机器别在服务器构建，改成本地构建推镜像 |
| 密钥泄露 | `.env` 已在 `.gitignore`/`.dockerignore` 范围外手动检查，切勿提交；容器里用环境变量注入 |

## 六、个人项目（自己用 / 给朋友看）怎么选

个人项目的判断标准是**低预算、低并发、自己能维护**，所以优先排除云托管/SAE 这类按量计费 + 控制台配置的平台，也排除免费 PaaS。

| 阶段 | 做法 | 成本 | 适用 |
|---|---|---|---|
| ① 先跑通 | 本机 `docker compose up` + cloudflared 临时公网地址 | 0 | 自测、发给朋友试用 |
| ② 长期挂着（✅ 推荐） | 一台入门轻量服务器（2C2G / 2C4G）+ 本项目 compose | 几十元/月 | 想有个固定地址、随时能打开 |
| ③ 只公开前端 | 前端 `dist` 上 Vercel / Cloudflare Pages / 任意静态托管，后端留在服务器 | 前端 0 | 展示作品、后端不常开 |

**为什么不推荐免费 PaaS 跑后端**：Render/Fly 免费档内存一般 512MB，Python 侧装完 langchain + langgraph + numpy 后常驻就要 300–500MB，容易 OOM；实例会休眠，冷启动 30–60s；平台默认请求超时常见 30s，LLM 生成容易被打断。

### ① 零成本先验证

```bash
# Windows/macOS 本机，项目根目录
# 80 被占用时在 .env 里加 WEB_PORT=8080
docker compose up -d --build

# 另开一个终端，拿一个临时 https 地址（无需域名、无需备案）
cloudflared tunnel --url http://localhost:8080
# 没装的话：winget install Cloudflare.cloudflared / brew install cloudflared
```

把 cloudflared 打印出来的 `https://xxx.trycloudflare.com` 发给朋友就能用。

### ② 长期部署（推荐）

流程就是第三节的步骤，注意三条**个人服务器专属**事项：

1. **别在服务器上 `docker build`**（2G 内存常被 OOM）：本地构建后 `docker save` 传过去，或推到镜像仓库再 `pull`；
2. **加 swap**，避免 pip/npm 峰值把机器打崩：
   ```bash
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
3. **HTTPS 最省事的做法**是在 compose 前面加一个 Caddy 容器（自动申请证书），或直接用厂商免费证书 → 但个人项目用 IP + HTTP 也完全够，先不折腾。

预算再紧的话，2C2G 也够跑：agent 常驻约 400MB、网关约 100MB、nginx 十几 MB，剩下留给系统。

### 服务器选哪家 / 要多久 / 要不要数据库

**选哪家**（账号已实名的话，下单只要 5 分钟）：

| 选择 | 说明 |
|---|---|
| 腾讯云轻量应用服务器（cloud.tencent.com） | 你已有腾讯云账号，同账号下单最快，控制台和备案流程都熟 |
| 阿里云轻量应用服务器（aliyun.com） | 同类产品，促销力度不同，比价即可 |
| 华为云 / 京东云 | 同类，偶尔有更低价的新用户档 |
| Vultr / DigitalOcean / Linode | 免备案，适合不想走 ICP；按美元计费，国内访问一般 |

规格：**2C2G 起步**（如果坚持在服务器上构建就 2C4G）；系统选 Ubuntu 22.04；带宽选最低档即可。
价格以官网为准，入门档通常几十元/月，新用户/学生档更低。

**要多久**：

| 阶段 | 耗时 |
|---|---|
| 下单 + 拿到 IP | 5–10 分钟 |
| 装 Docker | 2 分钟 |
| 传代码 | 3–5 分钟 |
| 首次构建（本地构建后推镜像则更快） | 5–10 分钟 |
| 验证三条命令 + 浏览器打开 | 5 分钟 |
| **首次合计** | **30–60 分钟** |
| 之后每次更新 | 2–3 分钟 |

域名另算：国内服务器**只用 IP + HTTP 访问不需要备案**；一旦绑域名就必须 ICP 备案（个人可办，通常 1–3 周）。

**要不要数据库**：不需要。
运行态 `_RUN_STORE` 是进程内存，重启丢的是「进行中的任务」，已生成/已审批的结果也不落库；个人 demo 完全够用。
只有想要「重启不丢任务」或「多实例扩容」时才需要 Redis（LangGraph Checkpointer）或 PostgreSQL——那是改代码，不属于「保持现状」。

### ③ 只公开前端

本地 `npm run build` 前把 `VITE_API_BASE_URL` 设成网关公网地址，再把 `dist` 拖到静态托管即可；网关已开 CORS。这样服务器上还能省掉 web 容器，只跑 agent + gateway。

## 七、最小可用清单

- [ ] 一台 2C4G Linux 服务器，放行 80/443/22
- [ ] 装 docker + compose v2
- [ ] `cp .env.example .env` 填 `OPENAI_API_KEY`
- [ ] `docker compose up -d --build`
- [ ] 三条验证命令全过
- [ ] 需要对外就挂域名 + HTTPS
