"""Local export leases and explicit recovery; no daemon or PID-based ownership.

The operating system releases a lease when its process exits, including crashes.
Keep lock files in place: deleting a held lock file would split its ownership.
Use a local filesystem; cross-host/network-filesystem locking is not supported.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .errors import AnalyticsError
from .metadata_io import retry_metadata_io


_ID = re.compile(r"[0-9a-f]{32}")
_MAX_JOB_BYTES = 1024 * 1024


def _identifier(job_id):
    if not isinstance(job_id, str) or not _ID.fullmatch(job_id):
        raise AnalyticsError("invalid_spec", "Job ID must be 32 lowercase hexadecimal characters")
    return job_id


def _redirect(metadata):
    # Includes Windows symlinks/junctions and other reparse-point indirections.
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _store(runs):
    try:
        directory = Path(os.path.abspath(os.fspath(runs)))
        metadata = directory.lstat()
        if _redirect(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise AnalyticsError("unsafe_job_path", "Job store must be an existing ordinary local directory")
        return directory.resolve(strict=True)
    except (OSError, TypeError, ValueError):
        raise AnalyticsError("io_error", "Cannot access the configured job directory") from None


def _regular(path, *, missing=False):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise AnalyticsError("io_error", "Job file is unavailable") from None
    if (_redirect(metadata) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1):
        raise AnalyticsError("unsafe_job_path", "Job files must be ordinary files, without links or directory indirections")
    return metadata


def _same(first, second):
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _open_file(path, flags, *, create=False):
    """Refuse existing redirects before opening, and verify the opened identity."""
    before = _regular(path, missing=create)
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        current = _regular(path)
        if not _same(opened, current) or (before is not None and not _same(before, opened)):
            raise AnalyticsError("unsafe_job_path", "Job file changed while it was being opened")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def _lease(path):
    descriptor, locked = None, False
    try:
        descriptor = _open_file(path, os.O_RDWR | os.O_CREAT, create=True)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            # Windows permits locking a byte beyond EOF. Initialize only after
            # owning it, avoiding a first-open write race with another worker.
            if os.fstat(descriptor).st_size == 0:
                os.lseek(descriptor, 0, os.SEEK_SET)
                os.write(descriptor, b"\0")
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise AnalyticsError("job_busy", "A live process owns this job or export registry lease; retry after it finishes") from None
            raise
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        raise AnalyticsError("io_error", "Cannot acquire the local export job lease") from None
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        raise
    try:
        yield
    finally:
        if descriptor is not None:
            try:
                if locked:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


@contextmanager
def acquire_job(runs, job_id):
    """Acquire one nonblocking process lease, held for the entire with block.

    Raises ``job_busy`` if a live process already owns it. The persistent .lock
    file is not itself evidence of liveness, and must never be deleted to unlock.
    """
    job_id = _identifier(job_id)
    directory = _store(runs)
    with _lease(directory / f"{job_id}.lock"):
        # The worker may read/write these paths after acquiring the lease.
        for suffix in (".json", ".csv.part", ".csv", ".cancel", ".export"):
            _regular(directory / f"{job_id}{suffix}", missing=True)
        yield


@contextmanager
def reserve_export(runs, job_id, maximum=2):
    """Reserve bounded worker capacity while the caller saves and launches a job.

    Keep only queue creation and worker startup inside this block. Success keeps
    the marker until the worker calls release_export after publishing its terminal
    status; exceptions release it. Admissions inspect only tiny .export markers.
    The registry lease stays held through this short block so manual recovery
    cannot mistake a new reservation for a crashed launch.
    """
    job_id = _identifier(job_id)
    if type(maximum) is not int or not 1 <= maximum <= 1000:
        raise AnalyticsError("invalid_configuration", "max_concurrent_exports must be an integer from 1 to 1000")
    directory = _store(runs)
    marker = directory / f"{job_id}.export"
    with _lease(directory / ".exports.lock"):
        if _regular(marker, missing=True) is not None:
            raise AnalyticsError("job_busy", "This export already has a worker reservation")
        reservations = [path for path in directory.glob("*.export") if _ID.fullmatch(path.stem)]
        for path in reservations:
            _regular(path)
        if len(reservations) >= maximum:
            raise AnalyticsError("budget_exceeded", "Export worker capacity is full; wait for completion or recover abandoned exports")
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(json.dumps({"job_id": job_id, "reserved_at": datetime.now(timezone.utc).isoformat()}).encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            yield
        except BaseException:
            release_export(directory, job_id)
            raise


def release_export(runs, job_id):
    """Release one owned capacity marker after terminal job metadata is published.

    No registry lease is needed: a concurrent removal can only free capacity.
    Persistent process lock files are never removed here.
    """
    job_id = _identifier(job_id)
    directory = _store(runs)
    path = directory / f"{job_id}.export"
    return _remove_owned(path, _regular(path, missing=True))


def _read_job(path):
    descriptor = _open_file(path, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        content = stream.read(_MAX_JOB_BYTES + 1)
    if len(content) > _MAX_JOB_BYTES:
        raise AnalyticsError("invalid_job", "Job metadata exceeds the 1 MiB recovery limit")
    def reject_constant(value):
        raise ValueError("Nonfinite JSON constant")
    try:
        value = json.loads(content, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise AnalyticsError("invalid_job", "Job metadata is not valid JSON") from None
    if not isinstance(value, dict):
        raise AnalyticsError("invalid_job", "Job metadata must be an object")
    return value, metadata


def _remove_owned(path, expected):
    if expected is None:
        return False
    current = _regular(path, missing=True)
    if current is None:
        return False
    if not _same(current, expected):
        raise AnalyticsError("unsafe_job_path", "Export artifact changed during recovery")
    path.unlink()
    return True


def _write_job(path, job, expected):
    content = (json.dumps(job, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.recovery.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        current = _regular(path)
        if (not _same(current, expected) or current.st_mtime_ns != expected.st_mtime_ns
                or current.st_size != expected.st_size):
            raise AnalyticsError("unsafe_job_path", "Job metadata changed during recovery")
        retry_metadata_io(lambda: os.replace(temporary, path))
    finally:
        temporary.unlink(missing_ok=True)


def recover_exports(runs):
    """Explicitly fail abandoned queued/running jobs; active leases are skipped.

    Recovery uses only the local job store, so it also works after dataset/catalog
    changes. A queued worker that has not yet acquired its lease may be recovered;
    callers should stop scheduling new exports while manually recovering jobs.
    A CSV published before a crash is preserved as an unverified orphan, never
    promoted to success. Export the original analysis again to create a new job.
    """
    directory = _store(runs)
    with _lease(directory / ".exports.lock"):
        return _recover_exports_locked(directory)


def _recover_exports_locked(directory):
    recovered, active, invalid, released = [], [], [], []
    ignored = 0
    try:
        markers = {path.stem for path in directory.glob("*.export") if _ID.fullmatch(path.stem)}
        candidates = sorted(markers | {path.stem for path in directory.glob("*.json") if _ID.fullmatch(path.stem)})
    except OSError:
        raise AnalyticsError("io_error", "Cannot enumerate the local export job store") from None
    for job_id in candidates:
        path = directory / f"{job_id}.json"
        try:
            metadata = _regular(path, missing=True)
            if metadata is None:
                if job_id in markers:
                    with acquire_job(directory, job_id):
                        if release_export(directory, job_id):
                            released.append(job_id)
                continue
            if metadata.st_size > _MAX_JOB_BYTES and job_id not in markers:
                # Large analysis results cannot be jobs from this implementation.
                ignored += 1
                continue
            # Avoid creating leases for analysis results and finished jobs.
            job, _ = _read_job(path)
            if job.get("kind") != "export" or job.get("status") not in ("queued", "running"):
                if job_id in markers:
                    if job.get("kind") != "export" or job.get("job_id") != job_id or job.get("status") not in ("complete", "failed", "cancelled"):
                        raise AnalyticsError("invalid_job", "Export reservation has incompatible job metadata")
                    with acquire_job(directory, job_id):
                        if release_export(directory, job_id):
                            released.append(job_id)
                ignored += 1
                continue
            if job.get("job_id") != job_id:
                raise AnalyticsError("invalid_job", "Job ID disagrees with its filename")
            with acquire_job(directory, job_id):
                job, metadata = _read_job(path)
                if job.get("kind") != "export" or job.get("job_id") != job_id:
                    raise AnalyticsError("invalid_job", "Job identity changed during recovery")
                if job.get("status") not in ("queued", "running"):
                    if job.get("status") in ("complete", "failed", "cancelled") and release_export(directory, job_id):
                        released.append(job_id)
                    ignored += 1
                    continue
                if job.get("complete") is not False:
                    raise AnalyticsError("invalid_job", "Pending export has inconsistent completion metadata")
                partial = directory / f"{job_id}.csv.part"
                cancel = directory / f"{job_id}.cancel"
                final = directory / f"{job_id}.csv"
                # Validate every artifact before any cleanup; stored paths are ignored.
                artifacts = {item: _regular(item, missing=True) for item in (partial, cancel, final)}
                previous = job["status"]
                removed_partial = _remove_owned(partial, artifacts[partial])
                _remove_owned(cancel, artifacts[cancel])
                orphan = None
                if artifacts[final] is not None:
                    orphan = {"path": final.name, "verified": False, "preserved": True}
                for key in ("file", "sha256", "orphan_artifact"):
                    job.pop(key, None)
                recovered_at = datetime.now(timezone.utc).isoformat()
                job.setdefault("stopped_stage", job.get("stage", previous))
                job.update(status="failed", complete=False, stage="failed",
                           stage_started_at=recovered_at, last_progress_at=recovered_at,
                           error={"code": "worker_interrupted", "message": "Export worker is no longer active; start a new export from the original analysis"},
                           recovered_at=recovered_at, previous_status=previous)
                if orphan:
                    job["orphan_artifact"] = orphan
                _write_job(path, job, metadata)
                if release_export(directory, job_id):
                    released.append(job_id)
                recovered.append({"job_id": job_id, "status": "failed", "previous_status": previous,
                                  "removed_partial": removed_partial, "orphan_artifact": orphan})
        except AnalyticsError as exc:
            if exc.code == "job_busy":
                active.append(job_id)
            else:
                invalid.append({"job_id": job_id, "error": exc.as_dict()})
        except (OSError, ValueError):
            invalid.append({"job_id": job_id, "error": {"code": "io_error", "message": "Could not recover this export; check local files and permissions"}})
    return {"recovered": recovered, "active": active, "invalid": invalid,
            "recovered_count": len(recovered), "active_count": len(active), "invalid_count": len(invalid),
            "orphan_count": sum(item["orphan_artifact"] is not None for item in recovered), "ignored_count": ignored,
            "released_reservations": released, "released_reservation_count": len(released)}
