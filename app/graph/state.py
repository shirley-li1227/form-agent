from typing import Optional, TypedDict

from app.models import FormSchema


class GraphState(TypedDict, total=False):
    """LangGraph 流转状态。"""

    run_id: str
    requirement: str
    context: str
    schema: Optional[FormSchema]
    retries: int
    need_approval: bool
    pass_check: bool
    approved: Optional[bool]
    comment: Optional[str]
    status: str
    message: str
