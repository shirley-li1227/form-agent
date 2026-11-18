import './styles.css';
import FormGenerator from './components/FormGenerator';

export default function App() {
  return (
    <div className="app-shell">
      <h2 className="app-title">AI 低代码表单 Agent</h2>
      <p className="app-subtitle">PydanticAI + LangGraph + LangChain</p>
      <FormGenerator />
    </div>
  );
}
