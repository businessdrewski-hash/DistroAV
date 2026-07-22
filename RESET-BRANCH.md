# Clean downstream diagnostics branch replacement

Do not delete the entire DistroAV repository. The plugin source, local build actions,
submodules, CMake files, and packaging infrastructure are still required.

## Recommended clean reset

1. Delete only the broken `receiver-clock-downstream-diagnostics` branch.
2. Recreate `receiver-clock-downstream-diagnostics` from the known working receiver-clock branch.
3. Upload the contents of this package while preserving paths.
4. Commit the upload to `receiver-clock-downstream-diagnostics`.
5. The workflow runs on every push to that branch. No `paths:` filter is used.

## Files supplied

- `.github/workflows/build-receiver-clock-live-diagnostics.yml`
- `tools/apply-receiver-clock-live-diagnostics.py`
- `src/receiver-clock-diagnostics-dock.cpp`
- `src/receiver-clock-diagnostics-dock.h`

The patcher accepts buildspec versions `6.2.1.1` or `6.2.1.2`, then changes the
diagnostics build identity to `6.2.1.3`. It remains idempotent if already applied.

## Important

This is a replacement overlay for the diagnostics integration, not a substitute for
the full DistroAV repository. Wiping every repository file would remove the build
system and make the project unbuildable.
