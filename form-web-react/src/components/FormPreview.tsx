import { DatePicker, Form, Input, InputNumber, Select } from 'antd';
import type { FormField, FormSchema } from '../types';

const { TextArea } = Input;

function renderControl(field: FormField) {
  switch (field.type) {
    case 'textarea':
      return <TextArea rows={3} placeholder={field.placeholder} />;
    case 'number':
      return (
        <InputNumber style={{ width: '100%' }} placeholder={field.placeholder} />
      );
    case 'date':
      return <DatePicker style={{ width: '100%' }} />;
    case 'select':
      return (
        <Select
          placeholder={field.placeholder}
          options={(field.options ?? []).map((item) => ({
            label: item,
            value: item,
          }))}
        />
      );
    default:
      return <Input placeholder={field.placeholder} />;
  }
}

interface Props {
  schema: FormSchema;
}

export default function FormPreview({ schema }: Props) {
  const [form] = Form.useForm();

  return (
    <div style={{ marginTop: 16 }}>
      <h3>{schema.title}</h3>
      <Form form={form} layout="vertical" style={{ width: 500 }}>
        {schema.fields.map((field) => (
          <Form.Item
            key={field.name}
            name={field.name}
            label={field.label}
            rules={
              field.required
                ? [{ required: true, message: `${field.label}必填` }]
                : []
            }
          >
            {renderControl(field)}
          </Form.Item>
        ))}
      </Form>
    </div>
  );
}
