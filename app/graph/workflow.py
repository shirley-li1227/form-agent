"""LangGraph 编排：检索 -> 生成 -> 校验循环 -> 人工审批。

- retrieve：LangChain RAG 召回规范上下文。
- generate：PydanticAI 节点生成强类型 FormSchema。
- check：规则校验；不合格且未超上限则循环回到 generate。
- approval：是否进入人工审批状态。

运行态保存在内存 store（可替换为 Redis / DB / LangGraph checkpointer）。
"""

from __future__ import annotations

import uuid
from typing import Optional

from app.agents.form_agent import FormAgent
from app.config import Settings, get_settings
from app.graph.state import GraphState
from app.models import FormSchema, GenerateResponse
from app.rag.retriever import Retriever

# 内存运行态：run_id -> state
_RUN_STORE: dict[str, GraphState] = {}


def _validate(schema: Optional[FormSchema], requirement: str) -> tuple[bool, str]:
    """规则校验：标题/字段非空、字段名唯一、需求提到手机时必须有 phone。"""
    if schema is None:
        return False, "未生成有效表单"
    if not schema.title.strip():
        return False, "表单标题为空"
    if not schema.fields:
        return False, "字段列表为空"

    names = [f.name for f in schema.fields]
    if len(names) != len(set(names)):
        return False, "字段标识重复"

    import re

    if re.search(r"手机|电话|联系方式", requirement):
        if "phone" not in names:
            return False, "需求包含手机号，但缺少 phone 字段"
    return True, "校验通过"


class FormWorkflow:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.retriever = Retriever(self.settings)
        self.form_agent = FormAgent(self.settings)
        self.graph = self._build_graph()

    # ---------- 节点 ----------

    def _retrieve_node(self, state: GraphState) -> dict:
        context = self.retriever.retrieve(state["requirement"])
        return {"context": context}

    def _generate_node(self, state: GraphState) -> dict:
        schema = self.form_agent.generate(state["requirement"], state.get("context", ""))
        return {"schema": schema, "retries": state.get("retries", 0) + 1}

    def _check_node(self, state: GraphState) -> dict:
        ok, msg = _validate(state.get("schema"), state["requirement"])
        return {"pass_check": ok, "message": msg}

    def _approval_node(self, state: GraphState) -> dict:
        if not state.get("pass_check"):
            return {"status": "rejected", "message": "超过最大重试次数仍未通过校验"}
        if state.get("need_approval"):
            return {"status": "pending_approval", "message": "等待人工审批"}
        return {"status": "auto_passed", "message": "无需审批，自动通过"}

    # ---------- 条件路由 ----------

    def _route_after_check(self, state: GraphState) -> str:
        if state.get("pass_check"):
            return "approval"
        if state.get("retries", 0) < self.settings.max_retry:
            return "generate"
        return "approval"

    # ---------- 构建图 ----------

    def _build_graph(self):
        from langgraph.graph import END, StateGraph

        builder = StateGraph(GraphState)
        builder.add_node("retrieve", self._retrieve_node)
        builder.add_node("generate", self._generate_node)
        builder.add_node("check", self._check_node)
        builder.add_node("approval", self._approval_node)

        builder.set_entry_point("retrieve")
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", "check")
        builder.add_conditional_edges(
            "check",
            self._route_after_check,
            {"approval": "approval", "generate": "generate", END: END},
        )
        builder.add_edge("approval", END)
        return builder.compile()

    # ---------- 对外入口 ----------

    def run(self, requirement: str, need_approval: bool) -> GenerateResponse:
        run_id = uuid.uuid4().hex[:12]
        init_state: GraphState = {
            "run_id": run_id,
            "requirement": requirement,
            "retries": 0,
            "need_approval": need_approval,
            "status": "pending",
            "message": "",
        }
        final_state = self.graph.invoke(init_state)
        _RUN_STORE[run_id] = final_state

        return GenerateResponse(
            run_id=run_id,
            status=final_state.get("status", "pending"),
            form_schema=final_state.get("schema"),
            message=final_state.get("message", ""),
            retries=final_state.get("retries", 0),
        )

    def get_run(self, run_id: str) -> Optional[GenerateResponse]:
        state = _RUN_STORE.get(run_id)
        if state is None:
            return None
        return self._to_response(state)

    def approve(self, run_id: str, approved: bool, comment: Optional[str]) -> Optional[GenerateResponse]:
        state = _RUN_STORE.get(run_id)
        if state is None:
            return None
        state["approved"] = approved
        state["comment"] = comment
        state["status"] = "approved" if approved else "rejected"
        state["message"] = comment or ("审批通过" if approved else "审批驳回")
        return self._to_response(state)

    @staticmethod
    def _to_response(state: GraphState) -> GenerateResponse:
        return GenerateResponse(
            run_id=state["run_id"],
            status=state.get("status", "pending"),
            form_schema=state.get("schema"),
            message=state.get("message", ""),
            retries=state.get("retries", 0),
        )
