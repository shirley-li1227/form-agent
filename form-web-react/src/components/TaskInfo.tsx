import { Button, Card, Space, Tag, Typography } from 'antd';
import type { RunInfo } from '../types';
import FormPreview from './FormPreview';

const STATUS_META: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '生成中' },
  pending_approval: { color: 'orange', text: '待人工审批' },
  auto_passed: { color: 'green', text: '自动通过' },
  approved: { color: 'green', text: '已通过' },
  rejected: { color: 'red', text: '已驳回' },
};

interface Props {
  run: RunInfo;
  onApprove: (approved: boolean) => void;
}

export default function TaskInfo({ run, onApprove }: Props) {
  const meta = STATUS_META[run.status] ?? { color: 'blue', text: run.status };

  return (
    <Card title={`任务 ID：${run.run_id}`} style={{ marginTop: 16 }}>
      <Space wrap>
        <Tag color={meta.color}>{meta.text}</Tag>
        <Typography.Text type="secondary">
          重试次数：{run.retries}
        </Typography.Text>
        {run.message && (
          <Typography.Text type="secondary">{run.message}</Typography.Text>
        )}
      </Space>

      {run.form_schema && <FormPreview schema={run.form_schema} />}

      {run.status === 'pending_approval' && (
        <Space style={{ marginTop: 16 }}>
          <Button type="primary" onClick={() => onApprove(true)}>
            通过
          </Button>
          <Button danger onClick={() => onApprove(false)}>
            驳回
          </Button>
        </Space>
      )}
    </Card>
  );
}
