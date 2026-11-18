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
                system_prompt=(
                    "你是低代码表单生成助手。根据用户需求与规范上下文，"
                    "输出符合 FormSchema 结构的标准表单 JSON；字段标识用蛇形命名，"
                    "类型只能是 text/tel/email/password/textarea/select/radio/checkbox/"
                    "switch/number/date/time/datetime/upload/url；"
                    "其中 select、radio、checkbox 必须给出 options 字符串数组；"
                    "switch 表示布尔开关（如同意协议）；upload 表示附件上传。"
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
                return result.output
            except Exception:
                # 模型调用失败（网络/额度/兼容性问题）时降级规则生成，不中断链路
                logger.warning("LLM 生成失败，降级规则兜底", exc_info=True)
        return self._fallback_generate(requirement)

    # ---------- 本地兜底（无 LLM 时的规则生成） ----------

    @staticmethod
    def _fallback_generate(requirement: str) -> FormSchema:
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
            fields.append(FormField(**kwargs))

        add(r"姓名|名字", name="name", label="姓名", type="text", required=True, placeholder="请输入姓名")
        add(r"手机|电话|联系方式", name="phone", label="手机号", type="tel", required=True, placeholder="请输入11位手机号")
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
