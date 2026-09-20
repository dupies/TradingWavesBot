"""Strategy plugins.

Every module in this package is imported on load so that its
`@register_strategy` decorator runs. Dropping a new strategy file into this
directory is therefore all that is needed for the registry — and so the
config file — to see it.
"""

from __future__ import annotations

import importlib
import pkgutil


def _load_plugins() -> None:
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_") or module.name == "base":
            continue
        importlib.import_module(f"{__name__}.{module.name}")


_load_plugins()
