"""PydanticAI 封装：负责单节点的强类型结构化表单生成。

- 配置了 LLM：返回 FormSchema，由 Pydantic 做类型校验。
- 未配置 OPENAI_API_KEY 时，走本地规则兜底（mock），保证无密钥也能跑通整条链路演示。
"""

from __future__ import annotations

import re
from typing import Optional

from app.config import Settings, get_settings
from app.models import FormField, FormSchema


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
            from pydantic_ai.models.openai import OpenAIModel

            model = OpenAIModel(
                self.settings.model_name,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )
            self._agent = Agent(
                model,
                result_type=FormSchema,
                system_prompt=(
                    "你是低代码表单生成助手。根据用户需求与规范上下文，"
                    "输出符合 FormSchema 结构的标准表单 JSON；字段标识用蛇形命名，"
                    "类型只能是 text/tel/email/textarea/select/number/date。"
                ),
            )
        except Exception:
            # 依赖未安装或初始化失败时，静默降级到本地兜底逻辑
            self._agent = None

    # ---------- 对外主方法 ----------

    def generate(self, requirement: str, context: str = "") -> FormSchema:
        if self._agent is not None:
            prompt = f"用户需求：{requirement}\n规范上下文：{context}\n请生成表单 Schema。"
            result = self._agent.run_sync(prompt)
            return result.data
        return self._fallback_generate(requirement)

    # ---------- 本地兜底（无 LLM 时的规则生成） ----------

    @staticmethod
    def _fallback_generate(requirement: str) -> FormSchema:
        fields: list[FormField] = []

        if re.search(r"姓名|名字", requirement):
            fields.append(
                FormField(name="name", label="姓名", type="text", required=True, placeholder="请输入姓名")
            )
        if re.search(r"手机|电话|联系方式", requirement):
            fields.append(
                FormField(name="phone", label="手机号", type="tel", required=True, placeholder="请输入11位手机号")
            )
        if re.search(r"邮箱|邮件", requirement):
            fields.append(
                FormField(name="email", label="邮箱", type="email", required=False, placeholder="请输入邮箱")
            )
        if re.search(r"地址|住址", requirement):
            fields.append(
                FormField(name="address", label="地址", type="textarea", required=False, placeholder="请输入详细地址")
            )
        if re.search(r"城市|地区", requirement):
            fields.append(
                FormField(
                    name="city",
                    label="城市",
                    type="select",
                    required=False,
                    options=["上海", "北京", "广州", "深圳"],
                )
            )
        if not fields:
            fields.append(
                FormField(name="remark", label="备注", type="textarea", required=False, placeholder="请输入备注")
            )

        title = requirement[:20] if requirement else "未命名表单"
        return FormSchema(title=title, fields=fields)
