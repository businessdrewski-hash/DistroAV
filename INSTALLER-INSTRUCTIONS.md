# Windows installer build

This package makes the **Build Receiver Clock Live Diagnostics** workflow produce three downloadable artifacts:

1. A Windows Inno Setup installer artifact containing:
   - `distroav-6.2.1.4-windows-x64-Installer.exe`
   - its SHA-256 checksum file
2. A standard Windows ZIP.
3. A portable Windows ZIP.

## Upload

Upload these five operational files to `receiver-clock-downstream-diagnostics`, preserving their paths:

```text
.github/workflows/build-receiver-clock-live-diagnostics.yml
src/receiver-clock-diagnostics-dock.cpp
src/receiver-clock-diagnostics-dock.h
tools/apply-receiver-clock-live-diagnostics.py
tools/verify-receiver-clock-live-diagnostics-build.py
```

Commit them together. The branch push triggers the workflow.

## Download and install

Open the completed workflow run and download the artifact whose name contains:

```text
windows-x64-installer
```

GitHub downloads workflow artifacts as ZIP containers. Extract that artifact ZIP, then run the enclosed `*-Installer.exe`.

Fully exit OBS before running the installer. Windows SmartScreen may warn because this experimental build is not Authenticode-signed. Confirm that the installer SHA-256 matches the included `.sha256` file before running it.
