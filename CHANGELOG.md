# Changelog

User-visible changes are recorded here. Version numbers follow
[Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- `kp mv ENTRY... GROUP` moves multiple entries into an existing group, checks all
  paths before writing, and reports partial failures. The original single-entry
  syntax remains supported.
- A batch move retrieves its Keychain password once for all checks and writes.

## 0.1.0

Initial release candidate; not yet tagged.

### Added

- Standalone `kp` command and `kpc` shortcut for a KeePassXC/KeePassium database.
- Literal config files, environment overrides, setup checks, and Keychain authentication.
- Hidden password prompts for entry creation and editing.
- Concealed, transient clipboard copies with conditional expiration.
- Installation and removal under a configurable prefix, without editing shell files.
- Isolated regression tests, macOS integration tests, and GitHub Actions checks.
