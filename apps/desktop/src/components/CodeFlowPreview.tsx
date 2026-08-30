import { CODE_FLOW_EXAMPLE } from "../content/codeFlowExample";
import { Badge } from "./ui/Badge";
import { Card } from "./ui/Card";
import { FlowArrowIcon } from "./icons/Icons";

export function CodeFlowPreview() {
  const { label, description, steps } = CODE_FLOW_EXAMPLE;

  return (
    <Card padding="md" elevated className="code-flow-card">
      <div className="code-flow-card__header">
        <div>
          <div className="code-flow-card__title-row">
            <h3 className="code-flow-card__title">Code flow preview</h3>
            <Badge variant="muted">{label}</Badge>
          </div>
          <p className="code-flow-card__description">{description}</p>
        </div>
      </div>

      <div className="code-flow">
        {steps.map((step, index) => (
          <div key={step}>
            <div className="code-flow__step">
              <div className="code-flow__node">{step}</div>
            </div>
            {index < steps.length - 1 ? (
              <div className="code-flow__arrow-row" aria-hidden="true">
                <FlowArrowIcon />
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </Card>
  );
}
