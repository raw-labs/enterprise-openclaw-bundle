"""Curation evidence validation against synthetic receipts and a real HTTP server.

These are reader/rejection checks; they do not qualify OCE or native images.
"""

import contextlib
import copy
import http.server
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

CHECKS = Path(__file__).resolve().parents[2] / "curation/oce/checks"
sys.path.insert(0, str(CHECKS))
from catalog import fingerprint, validate_measurement  # noqa: E402
from hosted import validate_lane, validate_platforms  # noqa: E402
from local import check_prefix, validate_native_ci_input  # noqa: E402
from oce_evidence import RangeFile  # noqa: E402


class CurationEvidenceTests(unittest.TestCase):
    def test_native_receipts_require_complete_unique_exact_source_set(self):
        sha = "a" * 40
        receipts = [
            {
                "image": image,
                "platform": "linux/" + arch,
                "sourceSha": sha,
                "workflowSha": sha,
                "runId": "123",
                "native": True,
                "ciRunId": "123",
                "ciAttempt": "1",
                "nodeBaseImage": "tested-base",
                "digest": "sha256:" + "b" * 64,
            }
            for image in ("controller", "runtime")
            for arch in ("amd64", "arm64")
        ]
        validate_platforms(receipts, sha, 123, 1, "tested-base")
        for mutation in (
            "missing",
            "duplicate",
            "source",
            "workflow",
            "run",
            "native",
            "digest",
            "ci_run",
            "ci_attempt",
            "base",
        ):
            changed = copy.deepcopy(receipts)
            if mutation == "missing":
                changed.pop()
            elif mutation == "duplicate":
                changed[-1] = changed[0]
            else:
                changed[-1][
                    {
                        "source": "sourceSha",
                        "workflow": "workflowSha",
                        "run": "runId",
                        "native": "native",
                        "digest": "digest",
                        "ci_run": "ciRunId",
                        "ci_attempt": "ciAttempt",
                        "base": "nodeBaseImage",
                    }[mutation]
                ] = "wrong"
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                validate_platforms(changed, sha, 123, 1, "tested-base")

    def test_ci_native_preflight_refuses_stale_variable_without_disabling_checks(self):
        workflow = """jobs:
  native-images:
    uses: ./.github/workflows/container-check.yml
    with:
      node_base_image: ${{ vars.CONTAINER_NODE_BASE_IMAGE }}
  static-checks:
    runs-on: ubuntu-24.04
"""
        validate_native_ci_input(workflow, "reviewed-base", "reviewed-base")
        with self.assertRaisesRegex(RuntimeError, "stale repository Node-base"):
            validate_native_ci_input(workflow, "reviewed-base", "old-variable")
        source_output = workflow.replace(
            "vars.CONTAINER_NODE_BASE_IMAGE", "needs.impact.outputs.node_base_image"
        )
        validate_native_ci_input(source_output, "reviewed-base", "old-variable")
        with self.assertRaisesRegex(RuntimeError, "changed workflow ownership"):
            validate_native_ci_input("jobs: {}", "reviewed-base", "old-variable")

    def test_lane_rejects_skip_wrong_source_and_failed_cleanup(self):
        lane = {
            "lane": "postgres",
            "sourceSha": "a" * 40,
            "status": "passed",
            "exitCode": 0,
            "issues": [],
            "counts": {"skipped": 0, "todo": 0},
            "files": [
                {
                    "path": "real.test.mjs",
                    "status": "passed",
                    "issues": [],
                    "cleanup": {"status": "passed"},
                }
            ],
        }
        validate_lane(lane, "a" * 40, True)
        for mutation in ("source", "skip", "cleanup"):
            changed = copy.deepcopy(lane)
            if mutation == "source":
                changed["sourceSha"] = "b" * 40
            elif mutation == "skip":
                changed["counts"]["skipped"] = 1
            else:
                changed["files"][0]["cleanup"]["status"] = "failed"
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                validate_lane(changed, "a" * 40, True)

    def test_catalog_measurement_is_bound_to_sql_method_and_real_server_identity(self):
        measurement = {
            "schema_digest": "schema",
            "method_digest": "method",
            "completed_catalog": "a" * 64,
            "ledger_catalog": "b" * 64,
            "restored_catalog": "c" * 64,
            "postgresql": "18.6",
            "drizzle": "0.45.4",
            "probe_sha": "d" * 40,
            "run_id": "123",
            "migration_count": 1,
            "prefixes": {
                "1": {
                    "catalog": "a" * 64,
                    "ledger": "b" * 64,
                    "restored_catalog": "c" * 64,
                    "upgraded_catalog": "c" * 64,
                }
            },
        }
        validate_measurement(measurement, "schema", "method")
        for key in measurement:
            changed = {**measurement, key: "wrong"}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate_measurement(changed, "schema", "method")
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):

            def git(*args):
                return subprocess.check_output(
                    ["git", *args], stderr=subprocess.DEVNULL
                )

            git("init", "--initial-branch=main")
            git("config", "user.name", "Curation Test")
            git("config", "user.email", "curation@example.invalid")
            Path("migrations/meta").mkdir(parents=True)
            sql = Path("migrations/0000_first.sql")
            sql.write_text("CREATE TABLE example (id integer);\n")
            manifest = Path("migrations/meta/_canonical-history.json")
            manifest.write_text('{"catalogs":{"completed":null}}')
            git("add", ".")
            git("commit", "-m", "unmeasured SQL")
            original = fingerprint()
            manifest.write_text('{"catalogs":{"completed":"measured"}}')
            git("add", ".")
            git("commit", "-m", "record measurement only")
            self.assertEqual(fingerprint(), original)
            sql.write_text("CREATE TABLE example (id text);\n")
            git("add", ".")
            git("commit", "-m", "different schema")
            self.assertNotEqual(fingerprint(), original)

    def test_zip_receipt_uses_bounded_http_ranges_and_rejects_whole_download(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("large-image-blob", b"x" * 3_000_000)
            archive.writestr("platform.json", json.dumps({"sourceSha": "a" * 40}))
        data = content.getvalue()
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                header = self.headers.get("Range")
                if self.path == "/ignores-range":
                    self.send_response(200)
                    self.end_headers()
                    return
                start, end = map(int, header.removeprefix("bytes=").split("-"))
                payload = data[start : end + 1]
                requests.append(len(payload))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"
        with zipfile.ZipFile(RangeFile(url + "/receipt")) as archive:
            self.assertEqual(
                json.loads(archive.read("platform.json"))["sourceSha"], "a" * 40
            )
        self.assertLess(sum(requests), 100_000)
        with self.assertRaisesRegex(RuntimeError, "honor byte ranges"):
            RangeFile(url + "/ignores-range")

    def test_published_migration_prefix_allows_append_and_rejects_rewrite(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):

            def git(*args):
                return (
                    subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)
                    .decode()
                    .strip()
                )

            git("init", "--initial-branch=main")
            git("config", "user.name", "Curation Test")
            git("config", "user.email", "curation@example.invalid")
            folder = Path("migrations/meta")
            folder.mkdir(parents=True)
            first = {
                "idx": 0,
                "tag": "0000_first",
                "when": 1,
                "version": "7",
                "breakpoints": True,
            }
            journal = {"version": "7", "dialect": "postgresql", "entries": [first]}
            path = folder / "_journal.json"
            path.write_text(json.dumps(journal))
            sql = Path("migrations/0000_first.sql")
            sql.write_text("CREATE TABLE example (id integer);\n")
            git("add", ".")
            git("commit", "-m", "synthetic published prefix")
            previous = git("rev-parse", "HEAD")
            journal["entries"].append(
                {**first, "idx": 1, "tag": "0001_second", "when": 2}
            )
            path.write_text(json.dumps(journal))
            Path("migrations/0001_second.sql").write_text(
                "ALTER TABLE example ADD COLUMN name text;\n"
            )
            Path("migrations/init-local.sql").write_text(
                "-- Bootstrap helper, not a migration.\n"
            )
            self.assertEqual(check_prefix(previous)["candidate_entries"], 2)
            # An intentional filename gap must keep Drizzle's next index aligned.
            Path("migrations/0001_second.sql").rename("migrations/0002_second.sql")
            journal["entries"][1].update(idx=2, tag="0002_second")
            path.write_text(json.dumps(journal))
            self.assertEqual(check_prefix(previous)["candidate_entries"], 2)
            journal["entries"][1]["idx"] = 1
            path.write_text(json.dumps(journal))
            with self.assertRaisesRegex(RuntimeError, "index must match"):
                check_prefix(previous)
            journal["entries"][1]["idx"] = 2
            path.write_text(json.dumps(journal))
            extra = Path("migrations/0003_unregistered.sql")
            extra.write_text("SELECT 1;\n")
            with self.assertRaisesRegex(RuntimeError, "SQL inventory differ"):
                check_prefix(previous)
            extra.unlink()
            sql.write_text("CREATE TABLE example (id text);\n")
            with self.assertRaisesRegex(RuntimeError, "SQL changed"):
                check_prefix(previous)
            sql.write_text("CREATE TABLE example (id integer);\n")
            journal["entries"][0]["when"] = 3
            path.write_text(json.dumps(journal))
            with self.assertRaisesRegex(RuntimeError, "metadata were rewritten"):
                check_prefix(previous)
