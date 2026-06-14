# HATSKit Pro v2.0.1

## Changes

- Added a component extras `Edit Target Path` action so registered extras can be retargeted without removing and re-adding them.
- Improved component extras source handling when retargeting files under `assets/component_extras/<component_id>/`.
- Changed the component extras `Scan Folder` button to a solid primary style so it no longer appears disabled on the dark theme.
- Highlight newly added selected components in orange in the Pack Builder preview, matching the existing changed-version indicator.
- Added a `+` marker for newly added components and kept `*` for components with version changes.
- Improved GitHub repository entry handling in the Component Editor with URL normalization and repo metadata scanning.
- Added authenticated GitHub API request support for release/version checks when a GitHub PAT is configured.
- Updated bundled component metadata, including refreshed versions and the ProdinForge component entry.

## Notes

- `assets/skeleton.zip` remains optional; component-owned extras continue to be the preferred source for pack-specific configs and resources.
- The generated pack changelog still records new, removed, and version-changed components during build output.
