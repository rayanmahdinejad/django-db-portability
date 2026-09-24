from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-db-portability")
except PackageNotFoundError:
    # Package isn't installed (e.g. running from a source checkout without
    # `pip install -e .`) - keep this in sync with pyproject.toml's version.
    __version__ = "0.5.0"

__all__ = ["__version__"]
