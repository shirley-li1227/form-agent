# 提示词规范（form-agent）

本文件约束 `app/agents/form_agent.py` 中 `system_prompt` 的编写与修改。
提示词可以调整，但**不得偏离 `app/models.py` 定义的结构化输出契约**，否则 Pydantic 校验失败会直接降级到规则生成。

## 一、输出契约

### 1. 顶层结构

```json
{
  "title": "活动报名表单",
  "fields": [
    {
      "name": "phone",
      "label": "手机号",
      "type": "tel",
      "required": true,
      "placeholder": "请输入11位手机号",
      "options": null
    }
  ]
}
```

由 `FormSchema` 定义：`title`（表单标题）+ `fields`（字段列表，不可为空）。

### 2. 字段属性

| 属性          | 规则                                                          |
| ------------- | ------------------------------------------------------------- |
| `name`        | 必填。英文蛇形命名，同一表单内唯一，如 `phone`、`event_date`  |
| `label`       | 必填。中文标签，如「手机号」。**禁止用 `title` 充当 `label`** |
| `type`        | 必填。只能取下方白名单中的值                                  |
| `required`    | 布尔，默认 `false`                                            |
| `placeholder` | 可选，输入提示文案                                            |
| `options`     | `select` / `radio` / `checkbox` 必填，字符串数组              |

### 3. type 白名单（15 种，不得自造）

`text` `tel` `email` `password` `textarea` `select` `radio` `checkbox` `switch` `number` `date` `time` `datetime` `upload` `url`

### 4. 类型选择映射

| 需求描述                 | 应选 type                      |
| ------------------------ | ------------------------------ |
| 姓名、普通文本           | `text`                         |
| 手机、电话、联系方式     | `tel`                          |
| 邮箱                     | `email`                        |
| 密码                     | `password`                     |
| 地址、备注、多行说明     | `textarea`                     |
| 场次、城市、部门等枚举   | `select`（必须补 `options`）   |
| 性别等单选               | `radio`（必须补 `options`）    |
| 爱好、兴趣等多选         | `checkbox`（必须补 `options`） |
| 「是否 XX」二值项        | `switch`（不要用 select 模拟） |
| 年龄、数量、金额         | `number`                       |
| 日期 / 时间点 / 日期时间 | `date` / `time` / `datetime`   |
| 附件、照片、证件         | `upload`                       |
| 网址、主页               | `url`                          |

## 二、提示词必须保留的约束

修改 `system_prompt` 时，以下几条**不能删**：

1. 必须逐个覆盖用户需求中列出的每一个字段，不得遗漏或合并；
2. 每个字段必须给出 `label`，严禁用 `title` 代替（`title` 只属于表单级标题）；
3. `name` 使用蛇形命名；
4. `type` 只能取白名单值；
5. `select` / `radio` / `checkbox` 必须给出 `options` 字符串数组；
6. `switch` 表示布尔开关（如同意协议）；
7. 「是否 XX」用 `switch`，「参加场次 / 选择 XX」用 `select` 并补全选项。

## 三、已知模型差异与代码兜底

当前默认模型是智谱 `glm-4-flash`（OpenAI 兼容接口）。它有几处与 OpenAI 模型不同的输出习惯，代码里已做兜底，但**兜底存在不等于可以放松提示词**。

| 现象                                                  | 代码兜底                                                             | 位置            |
| ----------------------------------------------------- | -------------------------------------------------------------------- | --------------- |
| 字段标签输出成 `title` 而非 `label`                   | `FormField` 的 `model_validator` 将 `title`/`name_cn` 映射为 `label` | `app/models.py` |
| 结构化输出偶发不合规                                  | `Agent(retries=3)` 提高输出重试次数                                  | `form_agent.py` |
| 中文词之间插入空格（「活 动」「上 午」，含全角/零宽） | `_clean_schema` 清理 `title`/`label`/`placeholder`/`options`         | `form_agent.py` |
| 漏掉需求中的部分字段                                  | `_merge_missing_fields` 用规则补齐，按 `name` 和 `label` 双重去重    | `form_agent.py` |
| 调用失败（401/额度/网络）                             | 降级本地规则生成，不中断链路，仅记 warning                           | `form_agent.py` |

## 四、修改提示词后的验证清单

1. 保存文件（`RELOAD=1` 启动时 agent 会自动重载，否则重启进程）；
2. 覆盖四类需求各跑一次 `POST /api/form/generate`：
   - 基础字段：`姓名、手机号、邮箱`
   - 枚举字段：`参加场次（上午/下午）`
   - 二值字段：`是否携带家属`
   - 其他类型：`生日、附件、备注`
3. 逐项检查返回：
   - HTTP `201`，`status=pending_approval`
   - 字段数量覆盖需求，无遗漏、无同义重复
   - `label` 是中文，没有被 `title` 冒充
   - `select` 类字段带 `options`
   - 文案中没有中文词间空格
4. 查看 agent 日志：**不出现** `LLM 生成失败，降级规则兜底` 才算真正走通模型；若出现，先看异常类型（401 是 Key、400 是请求体、ValidationError 是输出不合规）。

## 五、相关文件索引

| 文件                       | 职责                                                                            |
| -------------------------- | ------------------------------------------------------------------------------- |
| `app/agents/form_agent.py` | `system_prompt`、`_clean_schema`、`_merge_missing_fields`、`_fallback_generate` |
| `app/models.py`            | `FormSchema` / `FormField` 输出契约与兼容映射                                   |
| `app/graph/workflow.py`    | 检索 → 生成 → 校验循环 → 审批的状态机                                           |
| `data/specs/form-spec.md`  | RAG 语料，检索后会作为「规范上下文」拼进 prompt                                 |

## 六、变更记录

| 日期       | 变更                                                                                                        |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| 2026-11-18 | 切换到智谱 `glm-4-flash`；新增 `label`/`title` 兼容映射、中文空格清理、输出重试 3 次、补齐字段按 label 去重 |
