"""Read bundled assets independently of the working directory.

Wheels contain assets inside the package. Source checkouts retain their existing
fixtures/, schemas/, and static/ directories. Resources are always read-only.
"""

from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path


RESOURCE_KINDS = frozenset({"fixtures", "schemas", "static"})


def resource_root(kind):
    """Return a Traversable directory from the package or source checkout."""
    if not isinstance(kind, str) or kind not in RESOURCE_KINDS:
        raise ValueError("Unknown bundled resource kind")
    packaged = files("graphrag_discovery").joinpath(kind)
    if packaged.is_dir():
        return packaged
    checkout = Path(__file__).resolve().parent.parent
    source = checkout / kind
    if (checkout / "pyproject.toml").is_file() and source.is_dir():
        return source
    raise FileNotFoundError(f"Bundled resource directory is missing: {kind}")


def _resource(kind, parts):
    if any(not isinstance(part, str) or not part or part in {".", ".."}
           or "/" in part or "\\" in part or ":" in part for part in parts):
        raise ValueError("Resource names must be individual relative path components")
    result = resource_root(kind)
    for part in parts:
        result = result.joinpath(part)
    return result


def read_bytes(kind, *parts):
    return _resource(kind, parts).read_bytes()


def read_text(kind, *parts, encoding="utf-8"):
    return _resource(kind, parts).read_text(encoding=encoding)


@contextmanager
def resource_path(kind, *parts):
    """Yield a filesystem path; keep this context open while using that path.

    Python 3.12+ supports temporary extraction of resource directories too.
    """
    with as_file(_resource(kind, parts)) as path:
        yield path
