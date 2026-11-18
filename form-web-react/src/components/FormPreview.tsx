import { useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Switch,
  TimePicker,
  Upload,
} from 'antd';
import type { Rule } from 'antd/es/form';
import type { FormField, FormSchema } from '../types';

const { TextArea } = Input;

function optionList(field: FormField) {
  const list = field.options?.length ? field.options : ['选项一', '选项二'];
  return list.map((item) => ({ label: item, value: item }));
}

function renderControl(field: FormField) {
  switch (field.type) {
    case 'password':
      return <Input.Password placeholder={field.placeholder} />;
    case 'textarea':
      return <TextArea rows={3} placeholder={field.placeholder} />;
    case 'number':
      return (
        <InputNumber style={{ width: '100%' }} placeholder={field.placeholder} />
      );
    case 'date':
      return (
        <DatePicker
          style={{ width: '100%' }}
          format="YYYY-MM-DD"
          placeholder="请选择日期"
        />
      );
    case 'time':
      return (
        <TimePicker style={{ width: '100%' }} format="HH:mm" placeholder="请选择时间" />
      );
    case 'datetime':
      return (
        <DatePicker
          style={{ width: '100%' }}
          showTime
          format="YYYY-MM-DD HH:mm"
          placeholder="请选择日期时间"
        />
      );
    case 'select':
      return <Select placeholder={field.placeholder} options={optionList(field)} />;
    case 'radio':
      return <Radio.Group options={optionList(field)} />;
    case 'checkbox':
      return <Checkbox.Group options={optionList(field)} />;
    case 'switch':
      return <Switch />;
    case 'upload':
      return (
        <Upload beforeUpload={() => false} maxCount={3}>
          <Button>选择文件</Button>
        </Upload>
      );
    default:
      return <Input placeholder={field.placeholder} />;
  }
}

function valueProps(field: FormField) {
  if (field.type === 'switch') return { valuePropName: 'checked' };
  if (field.type === 'upload') {
    return {
      valuePropName: 'fileList',
      getValueFromEvent: (event: { fileList?: unknown[] }) => event?.fileList,
    };
  }
  return {};
}

function requiredText(field: FormField) {
  if (field.type === 'switch') return `请确认${field.label}`;
  if (['select', 'radio', 'checkbox', 'date', 'time', 'datetime'].includes(field.type)) {
    return `请选择${field.label}`;
  }
  return `请填写${field.label}`;
}

function rulesOf(field: FormField): Rule[] {
  const rules: Rule[] = [];
  if (field.required) {
    rules.push({ required: true, message: requiredText(field) });
  }
  if (field.type === 'email') {
    rules.push({ type: 'email', message: '邮箱格式不正确' });
  }
  if (field.type === 'url') {
    rules.push({ type: 'url', message: '请输入含 http/https 的网址' });
  }
  if (field.type === 'tel') {
    rules.push({
      pattern: /^[0-9+\-\s]{7,20}$/,
      message: '请输入正确的电话号码',
    });
  }
  return rules;
}

/** 把 dayjs / 上传文件转换成可读值，避免直接序列化出奇怪结构。 */
function plainValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(plainValue);
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    if (typeof record.format === 'function') {
      return (record.format as (pattern: string) => string)('YYYY-MM-DD HH:mm');
    }
    if (typeof record.name === 'string') return record.name;
  }
  return value;
}

interface Props {
  schema: FormSchema;
}

export default function FormPreview({ schema }: Props) {
  const [form] = Form.useForm();
  const [result, setResult] = useState<string | null>(null);

  if (!schema.fields?.length) {
    return <Alert type="warning" showIcon message="该表单没有字段" />;
  }

  const handleValidate = async () => {
    try {
      const values = await form.validateFields();
      const plain = Object.fromEntries(
        Object.entries(values ?? {}).map(([key, value]) => [key, plainValue(value)]),
      );
      setResult(JSON.stringify(plain, null, 2));
    } catch {
      setResult(null);
    }
  };

  return (
    <div style={{ marginTop: 12 }}>
      <h3 className="preview-title">{schema.title}</h3>
      <Form form={form} layout="vertical" style={{ width: '100%', maxWidth: 560 }}>
        {schema.fields.map((field) => (
          <Form.Item
            key={field.name}
            name={field.name}
            label={field.label}
            rules={rulesOf(field)}
            {...valueProps(field)}
          >
            {renderControl(field)}
          </Form.Item>
        ))}
        <Form.Item style={{ marginBottom: 0 }}>
          <div className="form-actions">
            <Button type="primary" onClick={handleValidate}>
              校验表单
            </Button>
            <Button
              onClick={() => {
                form.resetFields();
                setResult(null);
              }}
            >
              重置
            </Button>
          </div>
        </Form.Item>
      </Form>

      {result && (
        <Alert
          style={{ marginTop: 12 }}
          type="success"
          showIcon
          message="校验通过，表单值如下"
          description={<pre className="value-dump">{result}</pre>}
        />
      )}
    </div>
  );
}
