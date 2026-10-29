"""Small, bounded GitHub evidence reader. Never write credentials or signed URLs."""

import io
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY = "raw-labs/openclaw-enterprise"


def command(argv, *, env=None):
    result = subprocess.run(argv, env=env, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(
            f"{argv[0]} failed ({result.returncode}): {result.stderr[-3000:]}{result.stdout[-3000:]}"
        )
    return result.stdout


def api(path):
    return json.loads(command(["gh", "api", path]))


def pages(path, key):
    result = []
    for page in range(1, 101):
        data = api(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
        entries = data[key]
        result.extend(entries)
        if len(entries) < 100:
            return result
    raise RuntimeError("GitHub pagination exceeded the bounded reader")


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        return None


def artifact_location(artifact_id):
    # Authenticate only to api.github.com. The redirect contains a short-lived
    # signed artifact URL, which is never printed, persisted or passed to gh.
    token = command(["gh", "auth", "token"]).strip()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        urllib.request.build_opener(NoRedirect).open(request, timeout=60).close()
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise RuntimeError(
                f"Artifact download authorization failed: HTTP {error.code}"
            ) from None
        location = error.headers["Location"]
        if urlparse(location).scheme != "https":
            raise RuntimeError("Artifact redirect must use HTTPS") from None
        return location
    raise RuntimeError("Artifact service did not return a signed download redirect")


class RangeFile(io.RawIOBase):
    """ZipFile-compatible reader; rejects servers ignoring bounded byte ranges."""

    def __init__(self, url):
        self.url = url
        self.position = 0
        request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 206:
                raise RuntimeError("Artifact server must honor byte ranges")
            self.length = int(response.headers["Content-Range"].rsplit("/", 1)[1])
            if len(response.read(2)) != 1:
                raise RuntimeError("Invalid artifact byte-range response")

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (
            self.position if whence == 1 else self.length if whence == 2 else 0
        )
        if self.position < 0:
            raise RuntimeError("Invalid artifact seek")
        return self.position

    def read(self, size=-1):
        size = min(self.length - self.position, size if size >= 0 else self.length)
        if size <= 0:
            return b""
        if size > 2_000_000:
            raise RuntimeError("Artifact read exceeds 2 MB bound")
        start = self.position
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={start}-{start + size - 1}"}
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 206:
                raise RuntimeError("Artifact server ignored byte range")
            if (
                response.headers.get("Content-Range")
                != f"bytes {start}-{start + size - 1}/{self.length}"
            ):
                raise RuntimeError("Artifact returned an unexpected range")
            data = response.read(size + 1)
        if len(data) != size:
            raise RuntimeError("Truncated artifact range")
        self.position += size
        return data


def artifact_json(artifact, predicate, *, json_limit=1_000_000):
    result = []
    with zipfile.ZipFile(RangeFile(artifact_location(artifact["id"]))) as archive:
        for item in archive.infolist():
            if not predicate(item.filename):
                continue
            if item.file_size > json_limit or item.compress_size > 1_000_000:
                raise RuntimeError("JSON receipt exceeds its bounded size policy")
            result.append((item.filename, json.loads(archive.read(item))))
    return result


def workflow_run(workflow, sha, branch, state):
    def matching():
        runs = api(
            f"repos/{REPOSITORY}/actions/workflows/{workflow}/runs?head_sha={sha}&per_page=100"
        )["workflow_runs"]
        return [
            run
            for run in runs
            if run["head_sha"] == sha and run["head_branch"] == branch
        ]

    def reusable(run):
        return (
            run["head_sha"] == sha
            and run["status"] == "completed"
            and run["conclusion"] == "success"
            and run.get("event") == "workflow_dispatch"
            and run.get("head_repository", {}).get("full_name") == REPOSITORY
            and run.get("actor", {}).get("login") == "miguelbranco80"
            and re.fullmatch(
                r"codex/maintain/[0-9a-f]{32}", run.get("head_branch") or ""
            )
        )

    path = state / (workflow + ".json")
    record = json.loads(path.read_text()) if path.exists() else None
    if record and record.get("run_id"):
        found = api(f"repos/{REPOSITORY}/actions/runs/{record['run_id']}")
        recorded_branch = record.get("head_branch", branch)
        if found["head_sha"] != sha or found["head_branch"] != recorded_branch:
            raise RuntimeError("Recorded workflow run identity changed")
        if recorded_branch != branch and not reusable(found):
            raise RuntimeError("Recorded workflow reuse is no longer valid")
        return found

    candidates = matching()
    if not candidates and not record:
        # Qualification follows the exact code and workflow commit. A policy-only
        # revalidation can reuse one completed owner-dispatched run from another
        # Maintain branch; all source, lane, scenario and native receipts still gate it.
        prior = api(
            f"repos/{REPOSITORY}/actions/workflows/{workflow}/runs?head_sha={sha}&per_page=100"
        )["workflow_runs"]
        candidates = [run for run in prior if reusable(run)]
    if len(candidates) > 1:
        raise RuntimeError(
            "Multiple exact-source workflow runs need explicit inspection"
        )
    if candidates:
        save(
            path,
            {
                "source_sha": sha,
                "run_id": candidates[0]["id"],
                "head_branch": candidates[0]["head_branch"],
            },
        )
        return candidates[0]
    if record:
        # A POST may have succeeded without its response. Never repeat it blindly.
        raise RuntimeError(
            "Uncertain workflow dispatch: no exact-source run visible; inspect GitHub before retry"
        )
    if api(f"repos/{REPOSITORY}/git/ref/heads/{branch}")["object"]["sha"] != sha:
        raise RuntimeError("Candidate moved before dispatch")
    save(path, {"source_sha": sha, "dispatch_intent": True})
    command(["gh", "workflow", "run", workflow, "--repo", REPOSITORY, "--ref", branch])
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        candidates = matching()
        if len(candidates) == 1:
            save(path, {"source_sha": sha, "run_id": candidates[0]["id"]})
            return candidates[0]
        if len(candidates) > 1:
            break
        time.sleep(5)
    raise RuntimeError(
        "Dispatch outcome uncertain; saved intention prevents duplicate workflow runs"
    )


def wait_runs(runs, sha, state):
    pending = {run["id"]: run for run in runs}
    deadline = time.monotonic() + 10000
    while pending:
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Hosted workflow wait timed out; resume will observe the existing runs"
            )
        for run_id in list(pending):
            run = api(f"repos/{REPOSITORY}/actions/runs/{run_id}")
            if run["head_sha"] != sha:
                raise RuntimeError("Workflow source differs from the candidate")
            if run["status"] != "completed":
                continue
            save(state / f"run-{run_id}.json", run)
            if run["conclusion"] != "success":
                jobs = pages(
                    f"repos/{REPOSITORY}/actions/runs/{run_id}/jobs?filter=latest",
                    "jobs",
                )
                failed = [
                    job
                    for job in jobs
                    if job["conclusion"] not in ("success", "skipped", None)
                ]
                for job in failed:
                    log = state / f"job-{job['id']}.log"
                    result = subprocess.run(
                        [
                            "gh",
                            "run",
                            "view",
                            str(run_id),
                            "--repo",
                            REPOSITORY,
                            "--job",
                            str(job["id"]),
                            "--log",
                        ],
                        text=True,
                        capture_output=True,
                    )
                    log.write_text(
                        result.stdout if result.returncode == 0 else result.stderr
                    )
                raise RuntimeError(
                    f"Exact-source workflow failed: {run['html_url']}; leaf logs in {state}; "
                    + ", ".join(job["name"] for job in failed)
                )
            print(f"Passed {run['name']}: {run['html_url']}", flush=True)
            del pending[run_id]
        if pending:
            time.sleep(30)
    return [api(f"repos/{REPOSITORY}/actions/runs/{run['id']}") for run in runs]
