import React, { useState } from 'react';
import './App.css';

interface IngestionResult {
  original_tokens: number;
  structured_tokens: number;
  reduction_percent: number;
  breakdown: Record<string, number>;
  stored_memory_ids: string[];
}

interface ContextResult {
  context_id: string;
  estimated_tokens: number;
  relevant_knowledge: any[];
  relevant_decisions: any[];
  constraints: string[];
}

interface Connection {
  id: string;
  name: string;
  kind: string;
  status: string;
  description: string;
  capabilities: string[];
}

function App() {
  const [step, setStep] = useState(0);
  const [conversation, setConversation] = useState('');
  const [projectId, setProjectId] = useState('demo-project-' + Date.now());
  const [ingestionResult, setIngestionResult] = useState<IngestionResult | null>(null);
  const [task, setTask] = useState('');
  const [contextResult, setContextResult] = useState<ContextResult | null>(null);
  const [, setConnections] = useState<Connection[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const callAPI = async (endpoint: string, options: RequestInit = {}): Promise<any> => {
    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
        },
        ...options,
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      throw err;
    }
  };

  const handleStart = () => {
    setStep(1);
    setError('');
  };

  const handleIngest = async () => {
    if (!conversation.trim()) {
      setError('Please paste a conversation');
      return;
    }
    setLoading(true);
    setError('');
    try {
      // First, ensure the project exists (create if not)
      try {
        await callAPI('/api/v1/projects', {
          method: 'POST',
          body: JSON.stringify({ project_id: projectId, name: 'Demo Project' }),
        });
      } catch (_e) {
        // Ignore if already exists
      }
      const result = await callAPI('/api/v1/ingest-conversation', {
        method: 'POST',
        body: JSON.stringify({
          project_id: projectId,
          content: conversation,
          store: true,
        }),
      });
      setIngestionResult(result);
      setStep(3);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handlePrepare = async () => {
    if (!task.trim()) {
      setError('Please describe what you are working on');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await callAPI('/api/v1/get-context', {
        method: 'POST',
        body: JSON.stringify({
          project_id: projectId,
          task: task,
          max_knowledge_items: 10,
        }),
      });
      setContextResult(result);
      setStep(7);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(contextResult, null, 2));
    alert('Context copied to clipboard');
  };

  const handleRestart = () => {
    setStep(0);
    setConversation('');
    setProjectId('demo-project-' + Date.now());
    setIngestionResult(null);
    setTask('');
    setContextResult(null);
    setError('');
  };

  // Load connections on mount
  React.useEffect(() => {
    callAPI('/api/v1/connections')
      .then(data => setConnections(data.connections))
      .catch(err => console.warn('Could not load connections', err));
  }, []);

  // Render based on step
  let content;
  switch (step) {
    case 0:
      content = (
        <div className="home">
          <div className="hero">
            <h1>Are Your AI Tokens Finishing Too Fast?</h1>
            <p>
              Your AI shouldn't have to reread everything every time. Overhaust remembers what
              matters so you can get more from the AI you already use.
            </p>
            <div className="cta">
              <button onClick={handleStart} className="primary">
                Try Overhaust
              </button>
              <button onClick={() => setStep(9)} className="secondary">
                See How It Works
              </button>
            </div>
          </div>
        </div>
      );
      break;
    case 1:
      content = (
        <div className="step">
          <h2>Add something for your AI to remember</h2>
          <p>
            Paste a conversation, upload a file, or add a project. For this demo, we'll use a
            conversation.
          </p>
          <textarea
            value={conversation}
            onChange={e => setConversation(e.target.value)}
            placeholder="Paste your conversation here..."
            rows={10}
            className="conversation-input"
          />
          <div className="actions">
            <button onClick={handleRestart}>Back</button>
            <button onClick={handleIngest} className="primary">
              Process Conversation
            </button>
          </div>
          {error && <div className="error">{error}</div>}
        </div>
      );
      break;
    case 2:
      content = (
        <div className="step">
          <h2>Processing your conversation...</h2>
          <div className="progress">
            <div>Reading your conversation...</div>
            <div>Finding what matters...</div>
            <div>Removing repetition...</div>
            <div>Remembering important information...</div>
            <div>Your AI memory is ready.</div>
          </div>
          {/* Simulate progress with a timeout */}
          {loading ? null : (
            <div className="actions">
              <button onClick={handleStart}>Back</button>
              <button onClick={() => setStep(3)} className="primary">
                Continue
              </button>
            </div>
          )}
        </div>
      );
      // Simulate processing delay
      if (!loading && step === 2) {
        setTimeout(() => setStep(3), 1500);
      }
      break;
    case 3:
      content = (
        <div className="step">
          <h2>Your AI doesn't need all of this anymore.</h2>
          <div className="comparison">
            <div className="original">
              <h3>Original conversation</h3>
              <p>{ingestionResult?.original_tokens} estimated tokens</p>
            </div>
            <div className="arrow">↓</div>
            <div className="overhaust">
              <h3>Overhaust remembered</h3>
              <p>{ingestionResult?.structured_tokens} estimated tokens</p>
            </div>
            <div className="arrow">↓</div>
            <div className="reduction">
              <h3>Potential reduction</h3>
              <p>
                {ingestionResult?.reduction_percent}% <span className="note">(Estimated)</span>
              </p>
            </div>
          </div>
          <div className="actions">
            <button onClick={handleRestart}>Back</button>
            <button onClick={() => setStep(4)} className="primary">
              Continue
            </button>
          </div>
          {error && <div className="error">{error}</div>}
        </div>
      );
      break;
    case 4:
      content = (
        <div className="step">
          <h2>What your AI now remembers</h2>
          <p>
            Instead of technical jargon, here's what Overhaust extracted in simple terms:
          </p>
          <div className="memory-types">
            {/* We'll show the top categories from the breakdown */}
            {ingestionResult?.breakdown && Object.entries(ingestionResult.breakdown).map(
              ([category, tokens]) => {
                // Map technical categories to simple language
                const simpleMap: Record<string, string> = {
                  permanent_knowledge: 'Project decisions and important information',
                  decision: 'Important decisions you made',
                  current_task: 'What you are currently working on',
                  open_issue: 'Open issues you are tracking',
                  resolved_issue: 'Problems you have already solved',
                  stale_info: 'Outdated information (no longer relevant)',
                  irrelevant: 'Greetings and repetitive discussion (removed)',
                };
                const simple = simpleMap[category] || category;
                return (
                  <div key={category} className="memory-type">
                    <strong>{simple}</strong>: {tokens} estimated tokens
                  </div>
                );
              }
            )}
          </div>
          <div className="actions">
            <button onClick={handleRestart}>Back</button>
            <button onClick={() => setStep(5)} className="primary">
              Continue
            </button>
          </div>
          {error && <div className="error">{error}</div>}
        </div>
      );
      break;
    case 5:
      content = (
        <div className="step">
          <h2>What are you working on now?</h2>
          <input
            value={task}
            onChange={e => setTask(e.target.value)}
            placeholder="e.g., Fix the payment issue in my project"
            className="task-input"
          />
          <div className="actions">
            <button onClick={handleRestart}>Back</button>
            <button onClick={handlePrepare} className="primary">
              Prepare My AI
            </button>
          </div>
          {error && <div className="error">{error}</div>}
        </div>
      );
      break;
    case 6:
      content = (
        <div className="step">
          <h2>Preparing relevant information...</h2>
          <div className="progress">
            <div>Searching your AI memory...</div>
            <div>Finding relevant knowledge...</div>
            <div>Filtering out what's not needed...</div>
            <div>Preparing your AI's context...</div>
          </div>
          {/* Simulate progress */}
          {loading ? null : (
            <div className="actions">
              <button onClick={handleRestart}>Back</button>
              <button onClick={() => setStep(7)} className="primary">
                Continue
              </button>
            </div>
          )}
        </div>
      );
      // Simulate processing delay
      if (!loading && step === 6) {
        setTimeout(() => setStep(7), 1200);
      }
      break;
    case 7:
      content = (
        <div className="step">
          <h2>Ready for your AI</h2>
          <p>
            We found the information your AI needs. Here's the optimized context:
          </p>
          <div className="context-box">
            <pre>{JSON.stringify(contextResult, null, 2)}</pre>
          </div>
          <div className="tokens">
            <div>
              <strong>Original:</strong> {ingestionResult?.original_tokens} estimated tokens
            </div>
            <div>
              <strong>Prepared:</strong> {contextResult?.estimated_tokens} estimated tokens
            </div>
            <div>
              {(() => {
                const orig = ingestionResult?.original_tokens || 0;
                const prep = contextResult?.estimated_tokens || 0;
                if (prep >= orig) {
                  return <span><strong>This input is already compact.</strong> <span className="note">(not enough repetition to optimize)</span></span>;
                }
                const pct = ((orig - prep) / orig * 100).toFixed(1);
                return <span><strong>Estimated context reduction:</strong> {pct}% <span className="note">(Estimated)</span></span>;
              })()}
            </div>
          </div>
          <div className="actions">
            <button onClick={handleCopy} className="primary">
              Copy for AI
            </button>
            <button onClick={() => setStep(8)} className="secondary">
              View Details
            </button>
            <button onClick={handleRestart} className="tertiary">
              Start Over
            </button>
          </div>
          {error && <div className="error">{error}</div>}
        </div>
      );
      break;
    case 8:
      content = (
        <div className="step">
          <h2>Your AI memory is saved</h2>
          <p>
            The knowledge you just added is now available in your AI Memory. You don't need to
            explain this to your AI again.
          </p>
          <div className="actions">
            <button onClick={handleRestart} className="primary">
              Start Over
            </button>
            <button onClick={() => setStep(9)} className="secondary">
              See How It Works
            </button>
          </div>
          {error && <div className="error">{error}</div>}
        </div>
      );
      break;
    case 9:
      content = (
        <div className="step">
          <h2>How Overhaust Works</h2>
          <div className="how-it-works">
            <div className="step">
              <h3>1. Remember</h3>
              <p>Overhaust ingests your conversations, projects, and notes, extracting what matters and storing it in your AI memory.</p>
            </div>
            <div className="step">
              <h3>2. Understand</h3>
              <p>When you tell it what you're working on, it understands your intent and finds the relevant knowledge.</p>
            </div>
            <div className="step">
              <h3>3. Prepare</h3>
              <p>It builds a small, focused context containing only what your AI needs.</p>
            </div>
            <div className="step">
              <h3>4. Use</h3>
              <p>You give this context to your AI, so it doesn't waste time rereading everything.</p>
            </div>
          </div>
          <div className="actions">
            <button onClick={handleRestart} className="primary">
              Try Overhaust Yourself
            </button>
          </div>
        </div>
      );
      break;
    default:
      content = <div>Loading...</div>;
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>Overhaust</h1>
        <nav>
          <a href="#/home">Home</a>
          <a href="#/memory">AI Memory</a>
          <a href="#/projects">Projects</a>
          <a href="#/usage">Usage</a>
          <a href="#/connections">Connections</a>
        </nav>
      </header>
      <main>{content}</main>
    </div>
  );
}

export default App;