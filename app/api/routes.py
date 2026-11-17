"""FastAPI 路由：封装表单生成 Agent 的对外接口。"""

from fastapi import APIRouter, HTTPException

from app.graph.workflow import FormWorkflow
from app.models import ApprovalRequest, GenerateRequest, GenerateResponse

router = APIRouter(prefix="/api/form", tags=["form-agent"])

_workflow: FormWorkflow | None = None


def _get_workflow() -> FormWorkflow:
    global _workflow
    if _workflow is None:
        _workflow = FormWorkflow()
    return _workflow


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    """提交需求，跑完整编排：检索 -> 生成 -> 校验循环 -> 待审批/自动通过。"""
    if not req.requirement.strip():
        raise HTTPException(status_code=400, detail="requirement 不能为空")
    return _get_workflow().run(req.requirement, req.need_approval)


@router.get("/run/{run_id}", response_model=GenerateResponse)
def get_run(run_id: str) -> GenerateResponse:
    """查询某次生成任务的状态与 Schema。"""
    result = _get_workflow().get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result


@router.post("/approval/{run_id}", response_model=GenerateResponse)
def approval(run_id: str, req: ApprovalRequest) -> GenerateResponse:
    """人工审批：通过 / 驳回。"""
    result = _get_workflow().approve(run_id, req.approved, req.comment)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result
