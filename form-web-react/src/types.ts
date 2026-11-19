export interface FormField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  placeholder?: string;
  options?: string[];
}

export interface FormSchema {
  title: string;
  fields: FormField[];
}

export interface RunStep {
  node: 'retrieve' | 'generate' | 'check' | 'approval';
  at: string;
  summary: string;
  ok?: boolean | null;
  round?: number | null;
}

export interface RunInfo {
  run_id: string;
  status: string;
  form_schema?: FormSchema;
  message: string;
  retries: number;
  steps: RunStep[];
}
