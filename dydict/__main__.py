"""Run DyDict."""

import os
import sys

from dydict.shell import layer_shell_library, layer_shell_preload


def main() -> None:
    updated = layer_shell_preload(os.environ.get("LD_PRELOAD", ""), layer_shell_library())
    if updated is not None:
        os.environ["LD_PRELOAD"] = updated
        os.execv(sys.executable, [sys.executable, *sys.argv])
    from dydict.app import main as run

    raise SystemExit(run())


if __name__ == "__main__":
    main()
