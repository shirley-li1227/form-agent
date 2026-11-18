import { useEffect, useRef, useState } from "react";
import { Button, Card, Input, Switch, Typography, message } from "antd";
import { approval, errorText, generateForm, getRun } from "../api";
import type { RunInfo } from "../types";
import TaskInfo from "./TaskInfo";

const { TextArea } = Input;

/** 到达这些状态后不再轮询，等人工动作。 */
const SETTLED_STATUS = [
  "pending_approval",
  "auto_passed",
  "approved",
  "rejected",
];

export default function FormGenerator() {
  const [requirement, setRequirement] = useState(
    "活动报名表单，包含姓名（文本）、手机号、邮箱、登录密码、性别（单选：男/女）、" +
      "兴趣爱好（多选：阅读/运动/音乐/旅行）、出生日期（日期）、签到时间（时间，精确到时分）、" +
      "预约时间（日期时间）、年龄（数字）、所在城市（下拉：上海/北京/广州/深圳）、" +
      "详细地址（多行文本）、个人主页（网址）、证件照（附件上传）、是否同意参会协议（开关）",
  );
  const [needApproval, setNeedApproval] = useState(true);
  const [runInfo, setRunInfo] = useState<RunInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<number | null>(null);

  const stopPolling = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => stopPolling, []);

  const startPolling = (runId: string) => {
    stopPolling();
    timerRef.current = window.setInterval(async () => {
      try {
        const res = await getRun(runId);
        setRunInfo(res.data);
        if (SETTLED_STATUS.includes(res.data.status)) stopPolling();
      } catch {
        stopPolling();
      }
    }, 1500);
  };

  const handleSubmit = async () => {
    if (!requirement.trim()) {
      message.warning("请先描述你想要的表单");
      return;
    }
    setLoading(true);
    try {
      const res = await generateForm(requirement, needApproval);
      setRunInfo(res.data);
      startPolling(res.data.run_id);
    } catch (err) {
      message.error(errorText(err, "生成失败"));
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (approved: boolean) => {
    if (!runInfo) return;
    try {
      const res = await approval(runInfo.run_id, approved);
      setRunInfo(res.data);
      stopPolling();
      message.success(approved ? "已通过" : "已驳回");
    } catch (err) {
      message.error(errorText(err, "审批失败"));
    }
  };

  return (
    <Card title="AI 表单生成器">
      <TextArea
        rows={3}
        value={requirement}
        onChange={(e) => setRequirement(e.target.value)}
        placeholder="描述你想要的表单，例如：报名表单，包含姓名、手机号、性别、参加日期、上传证件"
      />

      <div className="form-actions" style={{ marginTop: 12 }}>
        <Button type="primary" onClick={handleSubmit} loading={loading}>
          发起生成
        </Button>
        <div className="switch-row">
          <Typography.Text type="secondary">需要人工审批</Typography.Text>
          <Switch
            checked={needApproval}
            onChange={setNeedApproval}
            size="small"
          />
        </div>
      </div>

      {runInfo && <TaskInfo run={runInfo} onApprove={handleApprove} />}
    </Card>
  );
}
