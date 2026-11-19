import operator
from typing import Annotated, Optional, TypedDict

from app.models import FormSchema


class GraphState(TypedDict, total=False):
    """LangGraph 流转状态。"""

    run_id: str
    requirement: str
    context: str
    schema: Optional[FormSchema]
    retries: int
    # 节点执行轨迹：各节点返回增量片段，由 add reducer 累加成完整链路
    steps: Annotated[list, operator.add]
    need_approval: bool
    pass_check: bool
    approved: Optional[bool]
    comment: Optional[str]
    status: str
    message: str
