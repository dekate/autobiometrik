"""PyInstaller entry point.

The package's ``__main__.py`` uses a relative import, which only works when
run as ``python -m autobiometrik``. PyInstaller executes its entry file as a
plain top-level script, so it needs this absolute-import shim instead.
"""

from autobiometrik.app import main

if __name__ == "__main__":
    main()
