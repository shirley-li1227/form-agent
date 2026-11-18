from typing import Optional

from pydantic import BaseModel, Field


class FormField(BaseModel):
    """单个表单字段（PydanticAI 结构化输出的最小单元）。"""

    name: str = Field(description="字段英文标识，蛇形命名，如 phone")
    label: str = Field(description="字段中文标签，如 手机号")
    type: str = Field(
        description=(
            "字段类型：text / tel / email / password / textarea / "
            "select / radio / checkbox / switch / number / "
            "date / time / datetime / upload / url"
        )
    )
    required: bool = Field(default=False, description="是否必填")
    placeholder: Optional[str] = Field(default=None, description="占位提示")
    options: Optional[list[str]] = Field(default=None, description="select 类型的选项")


class FormSchema(BaseModel):
    """完整表单 Schema，作为 Agent 的强类型输出。"""

    title: str = Field(description="表单标题")
    fields: list[FormField] = Field(description="字段列表")


# ---------- 接口入参 / 出参 ----------

class GenerateRequest(BaseModel):
    """前端提交的生成请求。"""

    requirement: str = Field(description="用户的表单需求描述")
    need_approval: bool = Field(default=True, description="是否需要人工审批环节")


class GenerateResponse(BaseModel):
    """生成接口返回。"""

    run_id: str = Field(description="本次任务 ID，用于后续审批查询")
    status: str = Field(description="pending_approval / approved / rejected / auto_passed")
    form_schema: Optional[FormSchema] = Field(default=None, description="生成的表单 Schema")
    message: str = Field(default="", description="状态说明")
    retries: int = Field(default=0, description="自动循环重生成次数")


class ApprovalRequest(BaseModel):
    """人工审批入参。"""

    approved: bool = Field(description="是否通过")
    comment: Optional[str] = Field(default=None, description="审批意见")
