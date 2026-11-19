"""LangGraph 编排：检索 -> 生成 -> 校验循环 -> 人工审批。

- retrieve：LangChain RAG 召回规范上下文。
- generate：PydanticAI 节点生成强类型 FormSchema。
- check：规则校验；不合格且未超上限则循环回到 generate。
- approval：是否进入人工审批状态。

每个节点向 state["steps"] 追加一条轨迹（累加型 reducer），接口原样返回，
前端据此还原本轮实际走过的链路，包括校验失败后又重生成了几轮。

运行态保存在内存 store（可替换为 Redis / DB / LangGraph checkpointer）。
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from app.agents.form_agent import FormAgent
from app.config import Settings, get_settings
from app.graph.state import GraphState
from app.models import FormSchema, GenerateResponse, RunStep
from app.rag.retriever import Retriever

# 内存运行态：run_id -> state
_RUN_STORE: dict[str, GraphState] = {}

SOURCE_LABEL = {"llm": "LLM", "rule": "规则兜底"}


def _step(
    node: str,
    summary: str,
    ok: Optional[bool] = None,
    round_: Optional[int] = None,
) -> dict:
    """构造一条节点轨迹。"""
    return {
        "node": node,
        "at": time.strftime("%H:%M:%S"),
        "summary": summary,
        "ok": ok,
        "round": round_,
    }


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
        hits = self.retriever.retrieve_hits(state["requirement"])
        top = self.retriever.chunk_title(hits[0]) if hits else "无"
        return {
            "context": "\n".join(hits),
            "steps": [
                _step(
                    "retrieve",
                    f"{self.retriever.mode} 检索命中 {len(hits)} 条规范，最相关：{top}",
                )
            ],
        }

    def _generate_node(self, state: GraphState) -> dict:
        schema, source = self.form_agent.generate(
            state["requirement"], state.get("context", "")
        )
        rounds = state.get("retries", 0) + 1
        return {
            "schema": schema,
            "retries": rounds,
            "steps": [
                _step(
                    "generate",
                    f"第 {rounds} 轮生成（{SOURCE_LABEL[source]}）：{len(schema.fields)} 个字段",
                    round_=rounds,
                )
            ],
        }

    def _check_node(self, state: GraphState) -> dict:
        ok, msg = _validate(state.get("schema"), state["requirement"])
        rounds = state.get("retries", 0)
        return {
            "pass_check": ok,
            "message": msg,
            "steps": [_step("check", msg, ok, round_=rounds)],
        }

    def _approval_node(self, state: GraphState) -> dict:
        if not state.get("pass_check"):
            status, msg = "rejected", "超过最大重试次数仍未通过校验"
        elif state.get("need_approval"):
            status, msg = "pending_approval", "等待人工审批"
        else:
            status, msg = "auto_passed", "无需审批，自动通过"
        # 待审批不算通过也不算失败，用 None 让前端保持中性色
        ok = None if status == "pending_approval" else status != "rejected"
        return {
            "status": status,
            "message": msg,
            "steps": [_step("approval", msg, ok)],
        }

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
            "steps": [],
            "need_approval": need_approval,
            "status": "pending",
            "message": "",
        }
        final_state = self.graph.invoke(init_state)
        _RUN_STORE[run_id] = final_state

        return self._to_response(final_state)

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
        state.setdefault("steps", []).append(
            _step("approval", f"人工审批：{state['message']}", approved)
        )
        return self._to_response(state)

    @staticmethod
    def _to_response(state: GraphState) -> GenerateResponse:
        return GenerateResponse(
            run_id=state["run_id"],
            status=state.get("status", "pending"),
            form_schema=state.get("schema"),
            message=state.get("message", ""),
            # 图内 retries 记的是 generate 执行次数，对外语义是「重生成次数」= 轮次 - 1
            retries=max(state.get("retries", 0) - 1, 0),
            steps=[RunStep(**step) for step in state.get("steps", [])],
        )
