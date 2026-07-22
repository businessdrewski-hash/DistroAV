# Upload instructions

Upload the contents of this package to:

```text
businessdrewski-hash/DistroAV
branch: receiver-clock-downstream-diagnostics
```

Required files:

```text
.github/workflows/build-receiver-clock-live-diagnostics.yml
src/receiver-clock-diagnostics-dock.cpp
src/receiver-clock-diagnostics-dock.h
tools/apply-receiver-clock-live-diagnostics.py
tools/verify-receiver-clock-live-diagnostics-build.py
```

Commit them in one commit. The push automatically starts **Build Receiver Clock Live Diagnostics**.

A correct artifact name begins with:

```text
receiver-clock-live-diagnostics-6.2.1.4-
```

## Installer

After the workflow succeeds, download the artifact with `windows-x64-installer` in its name. Extract the GitHub artifact ZIP and run the enclosed `*-Installer.exe`.
