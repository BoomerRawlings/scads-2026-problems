"""Fetch hash-pinned admitted source PDFs; never imported by the offline runtime.

Run from any directory. ``--verify-only`` performs no network access. Sources,
admission decisions and document metadata live in data/corpus-manifest.jsonl.
Downloads are bounded, verified before atomic replacement and never silently
overwrite a file whose bytes differ from the admitted manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


PROJECT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def destination(record: dict, root: Path) -> Path:
    relative = Path(record["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("manifest path must be a project-relative safe path")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError("destination escapes project root")
    return result


def verify(path: Path, record: dict) -> None:
    expected = record.get("sha256", "")
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("admitted source requires a lowercase SHA-256 pin")
    if not path.is_file():
        raise ValueError("source file missing")
    if path.stat().st_size != record["byte_size"]:
        raise ValueError("source byte count differs from manifest")
    with path.open("rb") as stream:
        if not stream.read(5).startswith(b"%PDF-"):
            raise ValueError("source is not a PDF")
    if sha256(path) != expected:
        raise ValueError("source SHA-256 differs from manifest")


class HTTPSOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("refusing non-HTTPS download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def acquire(record: dict, target: Path, max_bytes: int, timeout: int) -> str:
    if target.exists():
        verify(target, record)
        return "verified-existing"
    expected_bytes = record["byte_size"]
    if expected_bytes > max_bytes:
        raise ValueError("admitted file exceeds download size limit")
    urls = record.get("download_urls") or [record["document"]["source_uri"]]
    target.parent.mkdir(parents=True, exist_ok=True)
    failures = []
    opener = urllib.request.build_opener(HTTPSOnlyRedirect())
    for url in urls:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            raise ValueError("download URL must use HTTPS without credentials")
        temporary = None
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "VOPT-corpus-acquisition/1.0"})
            with opener.open(request, timeout=timeout) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > min(max_bytes, expected_bytes):
                    raise ValueError("server content length exceeds admitted byte count")
                with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as out:
                    temporary = Path(out.name)
                    total = 0
                    started = time.monotonic()
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > min(max_bytes, expected_bytes):
                            raise ValueError("download exceeds admitted byte count")
                        if time.monotonic() - started > max(60, timeout * 4):
                            raise TimeoutError("total download time limit exceeded")
                        out.write(chunk)
            verify(temporary, record)
            # Recheck: another acquisition may have completed while downloading.
            if target.exists():
                verify(target, record)
                return "verified-existing"
            temporary.replace(target)
            return "downloaded-and-verified"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            failures.append(f"{parsed.hostname}: {type(exc).__name__}: {exc}")
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    raise ValueError("; ".join(failures))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PROJECT / "data/corpus-manifest.jsonl")
    parser.add_argument("--root", type=Path, default=PROJECT, help="root for project-relative document paths")
    parser.add_argument("--ids", nargs="*", help="document IDs to acquire; admitted records only")
    parser.add_argument("--verify-only", action="store_true", help="verify locally without networking")
    parser.add_argument("--max-mb", type=int, default=40)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    if args.max_mb <= 0 or args.timeout <= 0:
        parser.error("limits must be positive")
    records = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    admitted = [r for r in records if r.get("admission_status") == "admitted"]
    requested = set(args.ids or [])
    unknown = requested - {r["document"]["doc_id"] for r in admitted}
    if unknown:
        parser.error("IDs are missing or not admitted: " + ", ".join(sorted(unknown)))
    failures = 0
    for record in admitted:
        doc_id = record["document"]["doc_id"]
        if requested and doc_id not in requested:
            continue
        try:
            target = destination(record, args.root)
            if args.verify_only:
                verify(target, record)
                status = "verified"
            else:
                status = acquire(record, target, args.max_mb * 1024 * 1024, args.timeout)
            print(json.dumps({"doc_id": doc_id, "status": status, "sha256": record["sha256"]}))
        except (OSError, ValueError, KeyError) as exc:
            failures += 1
            print(json.dumps({"doc_id": doc_id, "status": "failed", "error": str(exc)}), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
