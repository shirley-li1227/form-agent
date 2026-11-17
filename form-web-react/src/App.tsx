import FormGenerator from './components/FormGenerator';

export default function App() {
  return (
    <div style={{ padding: 24, maxWidth: 800, margin: '0 auto' }}>
      <h2>AI 低代码表单 Agent（PydanticAI + LangGraph + LangChain）</h2>
      <FormGenerator />
    </div>
  );
}
