import { FolderOpenIcon, PlusIcon } from "../components/icons/Icons";
import { PageContent } from "../components/layout/PageLayout";
import { Button } from "../components/ui/Button";
import "./pages.css";

export function ProjectsPage() {
  return (
    <PageContent narrow>
      <div className="empty-state">
        <div className="empty-state__icon">
          <FolderOpenIcon />
        </div>
        <h2 className="empty-state__title">No repositories yet</h2>
        <p className="empty-state__description">
          Add a local project to index its symbols, files, and relationships. Your repositories
          will appear here once connected in a future phase.
        </p>
        <Button variant="primary" size="md" icon={<PlusIcon width={16} height={16} />}>
          Add your first repository
        </Button>
      </div>
    </PageContent>
  );
}
