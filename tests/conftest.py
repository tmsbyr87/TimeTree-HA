"""Test setup.

``custom_components/timetree/__init__.py`` imports Home Assistant, which is not
installed in the unit-test environment. The modules under test (api, event,
store) are deliberately HA-free, so we register the package object *without*
executing ``__init__.py`` and let the submodules import normally.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_cc = sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
_cc.__path__ = [str(ROOT / "custom_components")]  # type: ignore[attr-defined]

_pkg_dir = ROOT / "custom_components" / "timetree"
if "custom_components.timetree" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "custom_components.timetree",
        _pkg_dir / "__init__.py",
        submodule_search_locations=[str(_pkg_dir)],
    )
    assert _spec is not None
    _pkg = importlib.util.module_from_spec(_spec)
    # Intentionally NOT calling _spec.loader.exec_module(_pkg).
    sys.modules["custom_components.timetree"] = _pkg
