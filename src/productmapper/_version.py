"""Single source of truth for the package version.

The version is declared once, in ``pyproject.toml``, and read back from the installed
package metadata at import time. Nothing else in the codebase hardcodes it, so a release
cannot ship a User-Agent or ``__version__`` that disagrees with the published version.

The fallback only matters when the package is imported from a source tree that was never
installed (for example a plain ``sys.path`` manipulation), where no metadata exists.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _metadata_version

__all__ = ["__version__"]

try:
    __version__: str = _metadata_version("productmapper")
except PackageNotFoundError:  # pragma: no cover - only hit in an uninstalled source tree
    __version__ = "0.0.0.dev0"
