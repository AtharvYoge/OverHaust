import { SparkIcon, SendIcon } from "../components/icons/Icons";
import { PageContent } from "../components/layout/PageLayout";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import "./pages.css";

const SUGGESTIONS = [
  "How does an order reach the kitchen?",
  "Where is the KOT generated?",
  "What calls buildKotText?",
];

export function ChatPage() {
  return (
    <PageContent narrow>
      <div className="chat-layout">
        <div className="chat-context">
          <span className="chat-context__label">Project context</span>
          <Badge variant="muted">No project selected</Badge>
        </div>

        <div className="chat-area">
          <div className="chat-messages">
            <div className="chat-empty">
              <div className="chat-empty__icon">
                <SparkIcon width={22} height={22} />
              </div>
              <h2 className="chat-empty__title">Start a conversation</h2>
              <p className="chat-empty__description">
                Ask about your codebase, trace flows, or explore how components connect. Responses
                will draw from indexed project knowledge.
              </p>
              <p className="chat-empty__hint">
                Future integration: search-knowledge and trace-code-flow endpoints.
              </p>
            </div>
          </div>

          <div className="chat-composer">
            <div className="chat-composer__inner">
              <textarea
                className="chat-composer__input"
                rows={1}
                placeholder="Ask about your codebase…"
                aria-label="Message composer"
                readOnly
              />
              <Button
                variant="primary"
                size="sm"
                icon={<SendIcon width={16} height={16} />}
                className="chat-composer__send"
                aria-label="Send message"
                disabled
              />
            </div>
            <div className="chat-suggestions" aria-label="Suggested prompts">
              {SUGGESTIONS.map((prompt) => (
                <button key={prompt} type="button" className="chat-suggestion" disabled>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </PageContent>
  );
}
