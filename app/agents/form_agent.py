"""PydanticAI 封装：负责单节点的强类型结构化表单生成。

- 配置了 LLM：返回 FormSchema，由 Pydantic 做类型校验。
- 未配置 OPENAI_API_KEY 时，走本地规则兜底（mock），保证无密钥也能跑通整条链路演示。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.config import Settings, get_settings
from app.models import FormField, FormSchema

logger = logging.getLogger(__name__)

# 部分模型（如 glm-4-flash）会在中文词之间插入空格（半角/全角/不换行/零宽），如「活 动报名表单」
_CJK_SPACE = re.compile(
    r"(?<=[\u4e00-\u9fff])[\s\u00a0\u200b\u200c\u200d\u2060\ufeff]+(?=[\u4e00-\u9fff])"
)


class FormAgent:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._agent = None
        self._init_agent()

    def _init_agent(self) -> None:
        """延迟初始化 PydanticAI Agent；没有密钥时不构造，避免导入/连接报错。"""
        if not self.settings.openai_api_key:
            return
        try:
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            provider = OpenAIProvider(
                base_url=self.settings.openai_base_url,
                api_key=self.settings.openai_api_key,
            )
            model = OpenAIChatModel(self.settings.model_name, provider=provider)
            self._agent = Agent(
                model,
                output_type=FormSchema,
                retries=3,
                system_prompt=(
                    "你是低代码表单生成助手。根据用户需求与规范上下文，"
                    "输出符合 FormSchema 结构的标准表单 JSON；"
                    "每个字段必须给出 label 字段存放中文标签，"
                    "严禁用 title 代替 label（title 只属于表单级标题）；字段标识 name 用蛇形命名，"
                    "类型只能是 text/tel/email/password/textarea/select/radio/checkbox/"
                    "switch/number/date/time/datetime/upload/url；"
                    "其中 select、radio、checkbox 必须给出 options 字符串数组；"
                    "switch 表示布尔开关（如同意协议）；upload 表示附件上传。"
                    "必须逐个覆盖用户需求中列出的每一个字段，不得遗漏或合并；"
                    "“是否 xx”这类二值项用 switch；“参加场次/选择 xx”这类选项项用 select 并补全 options。"
                ),
            )
        except Exception:
            # 依赖未安装或初始化失败时，静默降级到本地兜底逻辑
            logger.warning("PydanticAI Agent 初始化失败，降级规则生成", exc_info=True)
            self._agent = None

    # ---------- 对外主方法 ----------

    def generate(self, requirement: str, context: str = "") -> FormSchema:
        if self._agent is not None:
            prompt = f"用户需求：{requirement}\n规范上下文：{context}\n请生成表单 Schema。"
            try:
                result = self._agent.run_sync(prompt)
                return self._clean_schema(
                    self._merge_missing_fields(result.output, requirement)
                )
            except Exception:
                # 模型调用失败（网络/额度/兼容性问题）时降级规则生成，不中断链路
                logger.warning("LLM 生成失败，降级规则兜底", exc_info=True)
        return self._clean_schema(self._fallback_generate(requirement))

    def _merge_missing_fields(self, schema: FormSchema, requirement: str) -> FormSchema:
        """模型常漏字段：用规则识别结果补齐需求里明确提到、但模型没给的字段。

        模型给的 label 常与规则文案不同（如「所在城市」vs「城市」），
        因此再用生成该字段的规则去匹配已有 label，避免同一需求被补成两个字段。
        """
        existing = {item.name for item in schema.fields}
        existing_labels = {item.label for item in schema.fields}
        patterns: dict[str, str] = {}
        extra: list[FormField] = []
        for item in self._fallback_generate(requirement, patterns).fields:
            if item.name in existing or item.label in existing_labels:
                continue
            pattern = patterns.get(item.name)
            if pattern and any(re.search(pattern, label) for label in existing_labels):
                continue
            extra.append(item)
        if not extra:
            return schema
        logger.info("模型漏字段，规则补齐: %s", [item.name for item in extra])
        return FormSchema(title=schema.title, fields=[*schema.fields, *extra])

    @staticmethod
    def _clean_schema(schema: FormSchema) -> FormSchema:
        """清理模型在中文之间插入的多余空格。"""

        def clean(text: Optional[str]) -> Optional[str]:
            return _CJK_SPACE.sub("", text) if text else text

        fields = [
            field.model_copy(
                update={
                    "label": clean(field.label) or field.label,
                    "placeholder": clean(field.placeholder),
                    "options": [clean(opt) or opt for opt in field.options]
                    if field.options
                    else field.options,
                }
            )
            for field in schema.fields
        ]
        return FormSchema(title=clean(schema.title) or schema.title, fields=fields)

    # ---------- 本地兜底（无 LLM 时的规则生成） ----------

    @staticmethod
    def _fallback_generate(
        requirement: str, patterns: Optional[dict[str, str]] = None
    ) -> FormSchema:
        """本地规则生成；传入 patterns 时回填「字段名 → 命中规则」，供合并时去重。"""
        fields: list[FormField] = []
        positions: dict[str, int] = {}

        def add(pattern: str, **kwargs) -> None:
            match = re.search(pattern, requirement)
            if match is None:
                return
            name = kwargs["name"]
            if any(item.name == name for item in fields):
                return
            positions[name] = match.start()
            if patterns is not None:
                patterns[name] = pattern
            fields.append(FormField(**kwargs))

        add(r"姓名|名字", name="name", label="姓名", type="text", required=True, placeholder="请输入姓名")
        add(r"手机|电话|联系方式", name="phone", label="手机号", type="tel", required=True, placeholder="请输入11位手机号")
        add(
            r"场次|时段|班次|上午|下午",
            name="session",
            label="参加场次",
            type="select",
            required=False,
            options=["上午", "下午"],
        )
        add(r"是否携伴|是否带人|是否同行|携伴|同行人数", name="with_partner", label="是否携伴", type="switch", required=False)
        add(r"邮箱|邮件", name="email", label="邮箱", type="email", required=False, placeholder="请输入邮箱")
        add(r"密码", name="password", label="密码", type="password", required=True, placeholder="请输入密码")
        add(r"性别", name="gender", label="性别", type="radio", required=True, options=["男", "女"])
        add(
            r"爱好|兴趣|技能|多选",
            name="hobbies",
            label="兴趣爱好",
            type="checkbox",
            required=False,
            options=["阅读", "运动", "音乐", "旅行"],
        )
        add(r"同意|协议|条款|隐私", name="agree", label="我已阅读并同意相关条款", type="switch", required=True)
        add(r"地址|住址", name="address", label="地址", type="textarea", required=False, placeholder="请输入详细地址")
        add(
            r"城市|地区",
            name="city",
            label="城市",
            type="select",
            required=False,
            options=["上海", "北京", "广州", "深圳"],
        )

        # 日期/时间类各自独立判断，同一表单可以同时出现多个日期类字段
        add(r"开始日期|起始日期", name="start_date", label="开始日期", type="date", required=False)
        add(r"结束日期|截止日期", name="end_date", label="结束日期", type="date", required=False)
        add(r"生日|出生", name="birthday", label="出生日期", type="date", required=False)
        add(r"参加日期|活动日期|报名日期", name="event_date", label="参加日期", type="date", required=False)
        add(r"预约|日期时间|具体时间|时间点|日程", name="appoint_at", label="预约时间", type="datetime", required=False)
        # 纯时间点单独识别：否则下面「无日期类才补 time」的兜底会因已有 date/datetime 而跳过
        add(
            r"签到时间|入场时间|打卡时间|到店时间",
            name="checkin_time",
            label="签到时间",
            type="time",
            required=False,
        )
        if not any(item.type == "date" for item in fields):
            add(r"日期|哪天", name="date", label="日期", type="date", required=False)
        if not any(item.type in ("date", "time", "datetime") for item in fields):
            add(r"时间", name="time", label="时间", type="time", required=False)

        add(r"附件|上传|照片|图片|截图|证件", name="attachment", label="附件", type="upload", required=False)
        add(r"网址|链接|主页|官网", name="website", label="网址", type="url", required=False, placeholder="https://")
        add(r"年龄", name="age", label="年龄", type="number", required=False)
        add(r"人数|数量|次数|金额", name="count", label="数量", type="number", required=False)
        add(r"备注|说明|补充", name="remark", label="备注", type="textarea", required=False, placeholder="请输入备注")

        if not fields:
            fields.append(
                FormField(
                    name="remark",
                    label="备注",
                    type="textarea",
                    required=False,
                    placeholder="请输入备注",
                )
            )

        # 字段顺序跟随提示词中首次出现的顺序
        fields.sort(key=lambda item: positions.get(item.name, 10**6))

        # 标题取需求的第一句，避免从中间截断
        first_sentence = re.split(r"[，,。；;\n]", requirement.strip())[0].strip()
        title = first_sentence[:18] if first_sentence else "未命名表单"
        return FormSchema(title=title, fields=fields)
