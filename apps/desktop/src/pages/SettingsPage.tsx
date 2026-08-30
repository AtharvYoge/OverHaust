import { PageContent } from "../components/layout/PageLayout";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import "./pages.css";

function Toggle({ on, label }: { on: boolean; label: string }) {
  return (
    <button
      type="button"
      className={`settings-toggle${on ? " settings-toggle--on" : ""}`}
      aria-label={label}
      aria-pressed={on}
      disabled
    >
      <span className="settings-toggle__knob" />
    </button>
  );
}

export function SettingsPage() {
  return (
    <PageContent narrow>
      <Card padding="lg" elevated>
        <section className="settings-section">
          <h2 className="settings-section__title">Appearance</h2>
          <p className="settings-section__description">
            Customize how OverHaust looks on your desktop.
          </p>
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Use system appearance</div>
              <div className="settings-row__hint">Follow macOS light or dark mode.</div>
            </div>
            <Toggle on label="Use system appearance" />
          </div>
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Compact sidebar</div>
              <div className="settings-row__hint">Reduce navigation width for smaller windows.</div>
            </div>
            <Toggle on={false} label="Compact sidebar" />
          </div>
        </section>

        <section className="settings-section">
          <h2 className="settings-section__title">Workspace</h2>
          <p className="settings-section__description">
            Default folders and project preferences.
          </p>
          <Input
            label="Default projects folder"
            defaultValue="~/Projects"
            hint="Placeholder — not persisted in Phase 2."
            readOnly
          />
        </section>

        <section className="settings-section">
          <h2 className="settings-section__title">Backend</h2>
          <p className="settings-section__description">
            Connection to the local OverHaust Python API.
          </p>
          <Input
            label="API base URL"
            defaultValue="http://localhost:8000"
            hint="Backend connectivity arrives in a later phase."
            readOnly
          />
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Auto-start backend</div>
              <div className="settings-row__hint">
                Launch the Python sidecar when OverHaust opens.
              </div>
            </div>
            <Toggle on={false} label="Auto-start backend" />
          </div>
        </section>

        <section className="settings-section">
          <h2 className="settings-section__title">Privacy</h2>
          <p className="settings-section__description">
            Control how project data is handled locally.
          </p>
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Keep index data local</div>
              <div className="settings-row__hint">
                Indexed symbols and embeddings stay on this device.
              </div>
            </div>
            <Toggle on label="Keep index data local" />
          </div>
          <div className="settings-row">
            <div>
              <div className="settings-row__label">Clear conversation history on quit</div>
              <div className="settings-row__hint">Remove chat sessions when the app closes.</div>
            </div>
            <Toggle on={false} label="Clear conversation history on quit" />
          </div>
        </section>
      </Card>
    </PageContent>
  );
}
