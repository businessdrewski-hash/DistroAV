#!/usr/bin/env python3
"""Fail CI unless the packaged DistroAV DLL contains the new diagnostic code."""

from __future__ import annotations

from pathlib import Path
import sys
import zipfile


REQUIRED_MARKERS = (
    b"DistroAV Receiver Clock Health",
    b"Live diagnostics dock registered and available in Docks menu",
    b"Probe reconcile source=",
    b"Probe destroy cleanup source=",
)


def main() -> int:
    archives = sorted(Path("release").glob("*.zip")) + sorted(Path("release-portable").glob("*.zip"))
    if not archives:
        print("ERROR: no packaged Windows zip was found", file=sys.stderr)
        return 2

    checked: list[str] = []
    combined = bytearray()
    for archive in archives:
        with zipfile.ZipFile(archive) as package:
            dll_names = [name for name in package.namelist() if name.lower().endswith(".dll")]
            if not dll_names:
                continue
            for name in dll_names:
                checked.append(f"{archive}:{name}")
                combined.extend(package.read(name))

    if not checked:
        print("ERROR: no DLL was found inside the packaged zips", file=sys.stderr)
        return 2

    missing = [marker.decode("utf-8") for marker in REQUIRED_MARKERS if marker not in combined]
    if missing:
        print("ERROR: packaged DLL is missing required diagnostics markers:", file=sys.stderr)
        for marker in missing:
            print(f"  - {marker}", file=sys.stderr)
        print("DLLs checked:", file=sys.stderr)
        for item in checked:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("Packaged DLL contains the live dock and probe-lifecycle markers.")
    for item in checked:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
