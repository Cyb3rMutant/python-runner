import subprocess

from .models import GithubResult

REPO_DIR = "/app"


def commit_and_push(message: str) -> GithubResult:
    subprocess.run(["git", "add", "."], cwd=REPO_DIR, check=True)

    nothing_staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR
    ).returncode == 0
    if nothing_staged:
        return GithubResult(pushed=False, detail="nothing to commit")

    subprocess.run(["git", "commit", "-m", message], cwd=REPO_DIR, check=True)
    subprocess.run(["git", "push"], cwd=REPO_DIR, check=True)

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    return GithubResult(pushed=True, commit=sha, detail=message)
