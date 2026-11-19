import { Button, Card, Space, Tag, Timeline, Typography } from 'antd';
import type { RunInfo, RunStep } from '../types';
import FormPreview from './FormPreview';

const STATUS_META: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '生成中' },
  pending_approval: { color: 'orange', text: '待人工审批' },
  auto_passed: { color: 'green', text: '自动通过' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};

const NODE_LABEL: Record<RunStep['node'], string> = {
  retrieve: '检索规范',
  generate: '生成 Schema',
  check: '规则校验',
  approval: '审批',
};

/** 校验/审批失败标红，通过标绿；无判定含义（含等待人工审批）保持蓝色。 */
function stepColor(ok?: boolean | null): string {
  if (ok === false) return 'red';
  if (ok === true) return 'green';
  return 'blue';
}

interface Props {
  run: RunInfo;
  onApprove: (approved: boolean) => void;
}

export default function TaskInfo({ run, onApprove }: Props) {
  const meta = STATUS_META[run.status] ?? { color: 'blue', text: run.status };
  const rounds = run.steps.filter((step) => step.node === 'generate').length;

  return (
    <Card style={{ marginTop: 16 }}>
      <div className="task-head">
        <Typography.Text strong className="task-id">
          任务 ID：{run.run_id}
        </Typography.Text>
        <Space wrap size={8}>
          <Tag color={meta.color}>{meta.text}</Tag>
          <Typography.Text type="secondary">
            生成 {rounds} 轮 · 重试 {run.retries} 次
          </Typography.Text>
        </Space>
      </div>

      <Timeline
        className="run-steps"
        items={run.steps.map((step) => ({
          color: stepColor(step.ok),
          children: (
            <div className="step-body">
              <Typography.Text strong>{NODE_LABEL[step.node]}</Typography.Text>
              <Typography.Text type="secondary" className="step-time">
                {step.at}
              </Typography.Text>
              <div className="step-summary">{step.summary}</div>
            </div>
          ),
        }))}
      />

      {run.form_schema && <FormPreview schema={run.form_schema} />}

      {run.status === 'pending_approval' && (
        <div className="form-actions" style={{ marginTop: 16 }}>
          <Button type="primary" onClick={() => onApprove(true)}>
            通过
          </Button>
          <Button danger onClick={() => onApprove(false)}>
            驳回
          </Button>
        </div>
      )}
    </Card>
  );
}
