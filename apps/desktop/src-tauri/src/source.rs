use serde::Serialize;
use std::path::{Component, Path, PathBuf};
use tauri::command;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SourceAvailabilityResponse {
    pub available: bool,
    pub display_path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SourceOpenResponse {
    pub opened: bool,
    pub line_navigation_applied: bool,
}

#[derive(Debug)]
enum SourceResolveError {
    InvalidRoot,
    InvalidFile,
    OutsideRoot,
    MissingFile,
    Io,
}

impl SourceResolveError {
    fn user_message(&self) -> &'static str {
        match self {
            SourceResolveError::InvalidRoot => "Project root is unavailable.",
            SourceResolveError::InvalidFile => "Source file path is invalid.",
            SourceResolveError::OutsideRoot => "Source file is outside the project root.",
            SourceResolveError::MissingFile => "Source unavailable",
            SourceResolveError::Io => "Couldn't open this source file.",
        }
    }
}

fn normalize_separators(path: &str) -> String {
    path.replace('\\', "/")
}

fn normalize_root(project_root: &str) -> Result<PathBuf, SourceResolveError> {
    let trimmed = project_root.trim();
    if trimmed.is_empty() || trimmed.contains('\0') {
        return Err(SourceResolveError::InvalidRoot);
    }

    let path = Path::new(trimmed);
    path.canonicalize()
        .map_err(|_| SourceResolveError::InvalidRoot)
}

fn is_absolute_input(file: &str) -> bool {
    let normalized = normalize_separators(file);
    normalized.starts_with('/') || normalized.chars().nth(1) == Some(':')
}

fn normalize_relative_segments(file: &str) -> Result<PathBuf, SourceResolveError> {
    let trimmed = file.trim();
    if trimmed.is_empty() || trimmed.contains('\0') {
        return Err(SourceResolveError::InvalidFile);
    }

    let path = Path::new(trimmed);
    let mut normalized = PathBuf::new();

    for component in path.components() {
        match component {
            Component::Normal(part) => normalized.push(part),
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    return Err(SourceResolveError::OutsideRoot);
                }
            }
            Component::RootDir | Component::Prefix(_) => {
                return Err(SourceResolveError::InvalidFile);
            }
        }
    }

    if normalized.as_os_str().is_empty() {
        return Err(SourceResolveError::InvalidFile);
    }

    Ok(normalized)
}

fn resolve_under_root(root: &Path, file: &str) -> Result<PathBuf, SourceResolveError> {
    let candidate = if is_absolute_input(file) {
        PathBuf::from(file.trim())
    } else {
        let relative = normalize_relative_segments(file)?;
        root.join(relative)
    };

    let canonical = candidate
        .canonicalize()
        .map_err(|_| SourceResolveError::MissingFile)?;

    if !canonical.starts_with(root) {
        return Err(SourceResolveError::OutsideRoot);
    }

    Ok(canonical)
}

fn display_relative_path(root: &Path, canonical: &Path) -> String {
    match canonical.strip_prefix(root) {
        Ok(relative) => {
            let value = normalize_separators(&relative.to_string_lossy());
            if value.is_empty() {
                normalize_separators(&canonical.to_string_lossy())
            } else {
                value
            }
        }
        Err(_) => normalize_separators(&canonical.to_string_lossy()),
    }
}

fn resolve_source_path(
    project_root: &str,
    file: &str,
    require_file: bool,
) -> Result<(PathBuf, PathBuf, String), SourceResolveError> {
    let root = normalize_root(project_root)?;
    let canonical = resolve_under_root(&root, file)?;

    if require_file && !canonical.is_file() {
        return Err(SourceResolveError::MissingFile);
    }

    let display_path = display_relative_path(&root, &canonical);
    Ok((root, canonical, display_path))
}

#[cfg(target_os = "macos")]
fn open_with_default_app(path: &Path) -> Result<(), SourceResolveError> {
    use std::process::Command;

    let status = Command::new("open")
        .arg(path)
        .status()
        .map_err(|error| {
            let _ = error;
            SourceResolveError::Io
        })?;

    if status.success() {
        Ok(())
    } else {
        Err(SourceResolveError::Io)
    }
}

#[cfg(not(target_os = "macos"))]
fn open_with_default_app(path: &Path) -> Result<(), SourceResolveError> {
    use std::process::Command;

    let status = Command::new("xdg-open")
        .arg(path)
        .status()
        .map_err(|error| {
            let _ = error;
            SourceResolveError::Io
        })?;

    if status.success() {
        Ok(())
    } else {
        Err(SourceResolveError::Io)
    }
}

#[command]
pub fn check_source_availability(
    project_root: String,
    file: String,
    line: Option<u32>,
) -> SourceAvailabilityResponse {
    let _ = line;

    match resolve_source_path(&project_root, &file, true) {
        Ok((_root, _canonical, display_path)) => SourceAvailabilityResponse {
            available: true,
            display_path,
            reason: None,
        },
        Err(error) => SourceAvailabilityResponse {
            available: false,
            display_path: normalize_separators(file.trim()),
            reason: Some(error.user_message().to_string()),
        },
    }
}

#[command]
pub fn open_source_file(
    project_root: String,
    file: String,
    line: Option<u32>,
) -> Result<SourceOpenResponse, String> {
    let _ = line;

    let (_root, canonical, _display_path) =
        resolve_source_path(&project_root, &file, true).map_err(|error| error.user_message().to_string())?;

    open_with_default_app(&canonical).map_err(|error| error.user_message().to_string())?;

    Ok(SourceOpenResponse {
        opened: true,
        line_navigation_applied: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    fn temp_project() -> (tempfile::TempDir, PathBuf, PathBuf) {
        let counter = TEST_COUNTER.fetch_add(1, Ordering::Relaxed);
        let dir = tempfile::tempdir().expect("tempdir");
        let root = dir.path().join(format!("project-{counter}"));
        fs::create_dir_all(&root).expect("create project root");
        let file = root.join("lib/services/order_service.dart");
        fs::create_dir_all(file.parent().expect("parent")).expect("create parent");
        fs::write(&file, "void main() {}\n").expect("write file");
        (dir, root, file)
    }

    #[test]
    fn resolves_repo_relative_path() {
        let (_dir, root, file) = temp_project();
        let root_str = root.to_string_lossy().to_string();
        let response = check_source_availability(
            root_str,
            "lib/services/order_service.dart".to_string(),
            Some(207),
        );
        assert!(response.available);
        assert_eq!(response.display_path, "lib/services/order_service.dart");
        assert!(file.exists());
    }

    #[test]
    fn rejects_path_escape() {
        let (_dir, root, _file) = temp_project();
        let root_str = root.to_string_lossy().to_string();
        let response = check_source_availability(
            root_str,
            "../../etc/passwd".to_string(),
            None,
        );
        assert!(!response.available);
    }

    #[test]
    fn rejects_missing_file() {
        let (_dir, root, _file) = temp_project();
        let root_str = root.to_string_lossy().to_string();
        let response = check_source_availability(
            root_str,
            "lib/services/missing.dart".to_string(),
            None,
        );
        assert!(!response.available);
    }

    #[test]
    fn rejects_absolute_path_outside_root() {
        let (_dir, root, _file) = temp_project();
        let root_str = root.to_string_lossy().to_string();
        let outside = "/etc/passwd".to_string();
        let response = check_source_availability(root_str, outside, None);
        assert!(!response.available);
    }
}
