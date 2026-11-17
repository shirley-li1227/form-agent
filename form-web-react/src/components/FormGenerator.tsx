import { useEffect, useRef, useState } from 'react';
import { Button, Card, Input, Space, Switch, Typography, message } from 'antd';
import { approval, errorText, generateForm, getRun } from '../api';
import type { RunInfo } from '../types';
import TaskInfo from './TaskInfo';

const { TextArea } = Input;

/** 到达这些状态后不再轮询，等人工动作。 */
const SETTLED_STATUS = ['pending_approval', 'auto_passed', 'approved', 'rejected'];

export default function FormGenerator() {
  const [requirement, setRequirement] = useState(
    '用户注册表单，包含姓名、手机号、收货地址',
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
      message.warning('请先描述你想要的表单');
      return;
    }
    setLoading(true);
    try {
      const res = await generateForm(requirement, needApproval);
      setRunInfo(res.data);
      startPolling(res.data.run_id);
    } catch (err) {
      message.error(errorText(err, '生成失败'));
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
      message.success(approved ? '已通过' : '已驳回');
    } catch (err) {
      message.error(errorText(err, '审批失败'));
    }
  };

  return (
    <Card title="AI 表单生成器">
      <TextArea
        rows={4}
        value={requirement}
        onChange={(e) => setRequirement(e.target.value)}
        placeholder="描述你想要的表单，例如：用户注册表单，包含姓名、手机号、收货地址"
      />
      <Space style={{ marginTop: 12 }} align="center">
        <Button type="primary" onClick={handleSubmit} loading={loading}>
          发起生成
        </Button>
        <Typography.Text type="secondary">需要人工审批</Typography.Text>
        <Switch checked={needApproval} onChange={setNeedApproval} size="small" />
      </Space>

      {runInfo && <TaskInfo run={runInfo} onApprove={handleApprove} />}
    </Card>
  );
}
