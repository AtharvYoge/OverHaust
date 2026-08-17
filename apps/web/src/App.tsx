import React, { useState } from 'react';
import './App.css';

function App() {
  const [projectId, setProjectId] = useState('test-project-001');
  const [task, setTask] = useState('How should we build the frontend?');
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchContext = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('http://localhost:8000/api/v1/get-context', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_id: projectId,
          task: task,
          max_knowledge_items: 10,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setContext(data);
    } catch (err) {
      setError(err.message);
      setContext(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Overhaust Demo</h1>
        <p>
          AI Memory and Efficiency System
        </p>
      </header>
      <main>
        <div className="card">
          <h2>Get Context for Task</h2>
          <div>
            <label>
              Project ID:
              <input
                type="text"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
              />
            </label>
          </div>
          <div>
            <label>
              Task:
              <input
                type="text"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                style={{ width: '100%' }}
              />
            </label>
          </div>
          <button onClick={fetchContext} disabled={loading}>
            {loading ? 'Fetching...' : 'Get Context'}
          </button>
          {error && <div className="error">Error: {error}</div>}
          {context && (
            <div className="results">
              <h3>Context Retrieved</h3>
              <p><strong>Context ID:</strong> {context.context_id}</p>
              <p><strong>Task:</strong> {context.task}</p>
              <p><strong>Estimated Tokens:</strong> {context.estimated_tokens}</p>
              
              <div>
                <h4>Relevant Knowledge ({context.relevant_knowledge.length})</h4>
                <ul>
                  {context.relevant_knowledge.map((k, idx) => (
                    <li key={idx}>
                      <strong>[{k.knowledge_type}]</strong> {k.content}
                    </li>
                  ))}
                </ul>
              </div>
              
              <div>
                <h4>Relevant Decisions ({context.relevant_decisions.length})</h4>
                <ul>
                  {context.relevant_decisions.map((d, idx) => (
                    <li key={idx}>
                      <strong>[{d.knowledge_type}]</strong> {d.content}
                    </li>
                  ))}
                </ul>
              </div>
              
              <div>
                <h4>Constraints</h4>
                <ul>
                  {context.constraints.map((c, idx) => (
                    <li key={idx}>{c}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
        
        <div className="card">
          <h2>Token Estimation Example</h2>
          <p>
            Overhaust can estimate token usage and show potential savings.
          </p>
          <button onClick={async () => {
            try {
              const response = await fetch('http://localhost:8000/api/v1/estimate-reduction', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                  original_text: 'This is a very long sentence that contains lots of information that might not be necessary for the AI to process. '.repeat(10),
                  optimized_text: 'This is a test.',
                  model: 'gpt-4',
                }),
              });
              const data = await response.json();
              alert(`Token reduction: ${data.reduction_analysis.reduction_percent}% saved`);
            } catch (err) {
              alert('Error: ' + err.message);
            }
          }}>
            Show Token Savings Example
          </button>
        </div>
      </main>
    </div>
  );
}

export default App;