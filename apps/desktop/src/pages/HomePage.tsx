import { ArrowRightIcon, PlusIcon } from "../components/icons/Icons";
import { CodeFlowPreview } from "../components/CodeFlowPreview";
import { PageContent } from "../components/layout/PageLayout";
import { Button } from "../components/ui/Button";
import "./pages.css";

export function HomePage() {
  return (
    <PageContent narrow>
      <div className="home-hero">
        <section className="home-hero__intro">
          <p className="home-hero__eyebrow">Local-first codebase intelligence</p>
          <h2 className="home-hero__headline">Understand your codebase.</h2>
          <p className="home-hero__subhead">
            Ask questions. Trace the code. See how everything connects.
          </p>
          <p className="home-hero__tagline">
            OverHaust helps you explore indexed repositories, follow execution paths, and
            build confidence in how your software actually works.
          </p>
          <div className="home-hero__actions">
            <Button variant="primary" size="lg" icon={<PlusIcon width={16} height={16} />}>
              Add a repository
            </Button>
            <Button
              variant="secondary"
              size="lg"
              icon={<ArrowRightIcon width={16} height={16} />}
              iconPosition="right"
            >
              Explore demo
            </Button>
          </div>
        </section>

        <div className="home-grid">
          <section className="home-feature-list" aria-label="Capabilities">
            <article className="home-feature">
              <h3 className="home-feature__title">Ask with context</h3>
              <p className="home-feature__text">
                Pose natural-language questions against indexed symbols, files, and project
                knowledge—without leaving your desktop workspace.
              </p>
            </article>
            <article className="home-feature">
              <h3 className="home-feature__title">Trace real paths</h3>
              <p className="home-feature__text">
                Follow code flow from entry points through calls and relationships, grounded in
                evidence from your indexed repository.
              </p>
            </article>
            <article className="home-feature">
              <h3 className="home-feature__title">Stay local</h3>
              <p className="home-feature__text">
                Built for local-first workflows. Your codebase stays on your machine while
                OverHaust surfaces structure and connections.
              </p>
            </article>
          </section>

          <CodeFlowPreview />
        </div>
      </div>
    </PageContent>
  );
}
