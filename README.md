# kp

A small macOS CLI for the KeePass database you use with KeePassium.

`kp` supplies your configured database and its password from macOS Keychain to
`keepassxc-cli`. `kpc` copies an entry's password, marks it as confidential, and
expires the copy after 15 seconds.

```sh
kp search github
kp show 'Personal/GitHub'
kpc 'Personal/GitHub'
kp add 'Work/Example' -u 'me@example.com' -g -L 32
```

KeePassXC handles the KDBX format and encryption. KeePassium remains your graphical
client. Both can use the [same compatible database](https://support.keepassium.com/kb/compatible-apps/).
This is an independent utility, unaffiliated with either project.

## Requirements

- macOS with its built-in Bash 3.2, `security`, and `osascript`.
- KeePassXC CLI on `PATH`; tested with **2.7.12**.
- An existing, locally readable KDBX database protected by a nonempty, single-line
  master password. An additional key file is supported.
- A generic-password item in macOS Keychain containing that master password.

No build step or application language runtime is needed. Python 3 and ShellCheck
are development tools only.

## Install

Install [KeePassXC with Homebrew](https://formulae.brew.sh/cask/keepassxc):

```sh
brew install --cask keepassxc
keepassxc-cli --version
```

If you installed KeePassXC manually, its CLI is inside
`/Applications/KeePassXC.app/Contents/MacOS/`; make that directory available on `PATH`.

Clone or download this repository, enter its directory, then run:

```sh
make install
```

This copies the release files into `~/.local/libexec/kp` and creates `kp` and `kpc`
symlinks in `~/.local/bin`. It needs no `sudo`, does not edit shell startup files,
and keeps working if you move or remove the checkout. It refuses to replace
unrelated commands or an unmanaged installation directory.

If `~/.local/bin` is not already on `PATH`, add this **once** to `~/.zshrc`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Open a new terminal, or run that line in your current shell. The executables work
from any directory and from other shells with the same `PATH`.

Without `make`, use `/bin/bash scripts/install.sh install`. A custom destination
works with `make install PREFIX="/absolute/path"`; add that prefix's `bin` directory
to `PATH`.

## Configure

Point `kp` at the existing database:

```sh
kp init "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Passwords/vault.kdbx"
```

Use your actual database path. `init` creates `~/.config/kp/config` with mode `600`
and refuses to overwrite an existing config. It does not create, open, or modify
the database, and it does not read or change Keychain.

The default Keychain service is `KeePassVault`, matching the original shell
functions. If you already have that item, keep using it. For a new setup, create
an item with an interactive, hidden password prompt:

```sh
security add-generic-password -a "$USER" -s 'KeePassVault' -w
```

Leave `-w` last and enter the database's master password at the prompt. Do not put
the password in the command. Add `keychain_account=your-account-name` to the config
if multiple items share the same service. Manage existing credentials and access
permissions in **Keychain Access**; after changing the database master password,
update its Keychain item there too.

```sh
kp doctor
kp ls
```

`doctor` checks the config, paths, and available tools without retrieving a password
or unlocking the database. `kp ls` checks the actual Keychain/unlock path and may
trigger a macOS access prompt.

## Usage

| Task                                    | Command                                 |
| --------------------------------------- | --------------------------------------- |
| List entries or a group                 | `kp ls` / `kp ls 'Work'`                |
| Find entry paths                        | `kp search github`                      |
| Show an entry summary                   | `kp show 'Personal/GitHub'`             |
| Print a specific field                  | `kp show 'Personal/GitHub' -a UserName` |
| Explicitly print a password             | `kp show 'Personal/GitHub' -a Password` |
| Copy a password                         | `kpc 'Personal/GitHub'`                 |
| Copy with a 30-second timeout           | `kp copy 'Personal/GitHub' 30`          |
| Add with a generated password           | `kp add 'Work/Example' -u me -g -L 32`  |
| Add with a hidden password prompt       | `kp add 'Work/Example' -u me -p`        |
| Change a password using a hidden prompt | `kp edit 'Work/Example' -p`             |
| Create a group                          | `kp mkdir 'Work'`                       |
| Show backend options                    | `kp help add`                           |

`kpc ENTRY [SECONDS]` and `kp clip ENTRY [SECONDS]` are aliases for `kp copy`.
`clip` uses kp's syntax; KeePassXC's additional clipboard options are not forwarded.
Copy uses an exact entry path; use `search` to find it first. Entry paths containing
spaces must be quoted. An entry named `-h` or `--help` can be addressed through its
group path (for example `Personal/--help`).

The following commands forward their arguments to KeePassXC after inserting the
configured database: `ls`, `search`, `show`, `add`, `edit`, `mkdir`, `mv`, `rm`,
`rmdir`, `db-info`, `export`, `analyze`, `attachment-export`, `attachment-import`,
and `attachment-rm`. See `kp help COMMAND` for the backend syntax, then omit the
database argument when invoking it through `kp`. Separate short options and their
values (`-q -p`, `-L 32`). `add` and `edit` recognize both `-p` and
`--password-prompt`; a blank answer cancels the operation. These prompts require a
terminal and accept a single line. Generated passwords work in scripts.

`generate`, `diceware`, and `estimate` run without configuration or Keychain access.
Database administration (`db-create`, `db-edit`, `merge`, `import`, interactive
`open`) remains in `keepassxc-cli`: these commands have different database and
authentication requirements. Do not use `--no-password` through `kp`; it always
authenticates with Keychain. Hardware-key-only and passwordless databases are
outside this release's scope.

Database commands use KeePassXC's `-q` option to suppress already-answered password
prompts and secondary messages. Result data is passed through; copy messages and
errors go to stderr.
Exit status is `0` on success, `2` for wrapper usage errors, and nonzero on failure.
Forwarded commands preserve the backend's exit status; copy reports lookup/helper
failures as `1`. Wrapper diagnostics use `1` for setup and authentication errors.

### Configuration reference

The config is **literal `key=value` data**, not a shell script. Use no surrounding
quotes, no spaces around `=`, and absolute paths. Spaces and `=` inside a value
are preserved. `$HOME`, `~`, command substitutions, and inline comments are not
expanded. Blank lines and lines starting with `#` are ignored; unknown keys fail.
See [examples/config](examples/config).

| Key                 | Default                      | Environment override   |
| ------------------- | ---------------------------- | ---------------------- |
| `database`          | Required                     | `KP_DATABASE`          |
| `keychain_service`  | `KeePassVault`               | `KP_KEYCHAIN_SERVICE`  |
| `keychain_account`  | Any matching account         | `KP_KEYCHAIN_ACCOUNT`  |
| `key_file`          | None                         | `KP_KEY_FILE`          |
| `clipboard_timeout` | `15` seconds, range `1–3600` | `KP_CLIPBOARD_TIMEOUT` |

Precedence: environment → config → defaults. Empty environment values override
the config too. The config lives at `${XDG_CONFIG_HOME:-$HOME/.config}/kp/config`.
Set `KP_CONFIG_FILE` to use a different config; an explicitly selected missing file
is an error. A copy's positional timeout overrides the configured timeout.

```sh
KP_CLIPBOARD_TIMEOUT=30 kpc 'Personal/GitHub'
KP_CONFIG_FILE="$HOME/.config/kp/work" kp ls
```

## How it works

```text
kp / kpc ── config ── macOS Keychain
                         │ master password over stdin
                         ▼
                   keepassxc-cli ── shared .kdbx file ── KeePassium
                         │ entry password over stdin (copy only)
                         ▼
                  macOS pasteboard
                         │ generation + ownership token, no password
                         ▼
                  delayed conditional cleanup
```

Each database operation retrieves the master password anew. A failed Keychain read
stops before KeePassXC runs. For copy, the complete lookup must succeed before the
clipboard is touched. Password text is preserved, including embedded and trailing
newlines; only KeePassXC's final output newline is removed. Empty copies fail.

The helper publishes text together with the
[`ConcealedType` and `TransientType` markers](https://nspasteboard.org/). A detached
cleanup process receives only a clipboard generation and random ownership token.
After the timeout it checks both before clearing, so an older timer normally leaves
newer clipboard contents alone. The check uses macOS's
[`changeCount`](https://developer.apple.com/documentation/appkit/nspasteboard/changecount).

### Trust and limits

- Master and entry passwords travel through process memory and pipes. kp does not
  put them in process arguments, exported variables, log files, or temporary files.
  It disables inherited shell tracing before handling them. Explicit commands such
  as `show -a Password` and `export` still print secrets by design.
- The CLI, scripts, config, `PATH`, and local account must be trusted. Keychain
  access rules still apply. Allowing `security` to read an item can allow other
  processes in your session to request the same access.
- Clipboard markers are requests to cooperating applications, not access control.
  Other apps can read the clipboard. Expiration is best effort: process termination,
  sleep, or pasteboard failures can delay/prevent it. The ownership check and clear
  are not an atomic operation. This is not guaranteed memory erasure.
- KeePassium and kp share a file; kp does not coordinate cloud sync or concurrent
  writes. Let syncing finish before editing, avoid simultaneous edits on different
  clients, and keep database backups. Cloud-only placeholder files must be downloaded.
- kp writes database changes immediately through KeePassXC. It adds no independent
  transaction, backup, or sync layer.

## Update and uninstall

Check out the desired release and rerun `make install` while kp is idle. Installation
copies the code, so pulling the repository alone does not update the installed CLI.
It preserves configuration, databases, and Keychain items.

```sh
make uninstall
# For a custom install, use the same prefix:
make uninstall PREFIX="/absolute/path"
```

Keep a checkout/download to run the uninstall script. It removes only a recognized
kp installation and its expected command links, leaving personal data in place.

## Development

The repository has three runtime responsibilities:

| File                             | Responsibility                                                    |
| -------------------------------- | ----------------------------------------------------------------- |
| `bin/kp` (`bin/kpc` links to it) | Resolve installation paths and select the command                 |
| `lib/kp.sh`                      | Configuration, CLI dispatch, Keychain and KeePassXC orchestration |
| `lib/clipboard.applescript`      | Native pasteboard writes and conditional expiration               |

`scripts/install.sh` owns installation; `VERSION` owns the release number. No generic
plugin system or password-storage layer is needed for this scope.

```sh
brew install shellcheck
make lint
make test
make test-integration
```

CLI tests use Python's standard `unittest` library, fake executables, fake passwords,
and a temporary home directory. Integration tests create a disposable KDBX database
and use a **private named pasteboard**, leaving your vault, Keychain, and general
clipboard untouched. Native integration requires a logged-in macOS session and
KeePassXC on `PATH`. GitHub Actions runs the same checks on macOS.

Changes involving authentication, entry prompts, clipboard ownership, or install
replacement need regression coverage. Keep user-facing changes in
[CHANGELOG.md](CHANGELOG.md). Report bugs without posting credentials, vaults, or
unredacted exports.

## Versioning and releases

Versioning belongs to the project, independently of a package manager.
[VERSION](VERSION) contains `0.1.0`, which is also printed by `kp --version` and
included in installations. An annotated Git tag identifies the exact released
commit. The file keeps version reporting working in downloads without `.git`.

Use [Semantic Versioning](https://semver.org/): after `1.0.0`, fixes increment PATCH,
compatible features increment MINOR, and breaking CLI/config changes increment
MAJOR. For the initial `0.x` phase, this project uses patch releases for compatible
fixes and minor releases for features or breaking changes, with breaks called out
in the changelog. The public interface is the documented commands, flags,
configuration, output, and exit behavior; forwarded behavior also depends on the
installed KeePassXC version.

To release:

1. Set `VERSION`, update the changelog with the version and release date, and run
   `make lint test test-integration`.
2. Commit those changes (for a later release, e.g. `chore(release): 0.2.0`).
3. Create an annotated tag on that commit and publish it:

   ```sh
   git tag -a v0.1.0 -m 'Release v0.1.0'
   git push origin main
   git push origin v0.1.0
   ```

4. Create a GitHub Release from the tag with the relevant changelog notes. GitHub's
   source archive is sufficient for this source-only distribution.

Keep `VERSION` and the tag in agreement, and never move a published release tag.
Conventional Commits describe changes; they do not create versions automatically.
Manual releases are enough at this size.

## License

[MIT](LICENSE), copyright Andrei Furdui.
