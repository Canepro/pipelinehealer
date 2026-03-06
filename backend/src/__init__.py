"""PipelineHealer package metadata."""

from importlib.metadata import PackageNotFoundError, version


def _resolve_version() -> str:
    try:
        return version("pipelinehealer")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _resolve_version()
