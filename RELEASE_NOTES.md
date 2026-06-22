# HATSKit Pro v2.0.2

## What's New

- Added support for components hosted in private GitHub repositories.
- GitHub Personal Access Tokens now authenticate both release metadata requests and release asset downloads.
- Added active preset names to generated pack filenames and pack summaries, making preset-based builds easier to identify.
- Updated bundled component metadata and versions, including Atmosphere and Hekatos.

## Private Repository Access

To download components from a private GitHub repository, configure a Personal Access Token in HATSKit Pro:

- Fine-grained tokens require access to the selected repository with **Contents: Read-only** permission.
- Classic tokens require the `repo` scope.

Public GitHub repositories continue to work without repository-specific token permissions.
