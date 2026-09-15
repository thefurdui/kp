# kp

A macOS command-line companion for KeePass databases used with KeePassium.

`kp` supplies your configured database and its password from macOS Keychain to
`keepassxc-cli`. `kpc` copies an entry's password, marks it as confidential, and
expires the copy after 15 seconds.

```sh
kp search example-app
kp show 'work/example-app'
kpc 'work/example-app'
kp help edit
```

KeePassXC handles the KDBX format and encryption. KeePassium remains your graphical
client. Both can use the [same compatible database](https://support.keepassium.com/kb/compatible-apps/).
This is an independent utility, unaffiliated with either project.

[Install](#install) · [Configure](#configure) · [Recipes](#everyday-recipes) ·
[Commands](#command-reference) · [How it works](#how-it-works) ·
[Releases](#versioning-and-releases)

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
kp init "$HOME/Documents/Passwords/vault.kdbx"
```

Use your actual database path. `init` creates `~/.config/kp/config` with mode `600`
and refuses to overwrite an existing config. It does not create, open, or modify
the database, and it does not read or change Keychain.

The default Keychain service name is `KeePassVault`. To create an item containing
the database's master password, run this command and enter the password at the
hidden prompt. Skip this step if a matching item already exists:

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

Start with the [recipes](#everyday-recipes), or jump to the
[complete command reference](#command-reference). All account names, entry paths,
and service URLs below are fictional examples. Replace them with values from your
database.

`work` is a database group and `work/example-app` is an entry inside it. Quote entry
names containing spaces and use the spelling shown by `kp ls` or `kp search`.
After creating the example entry, use the recipes independently; renaming or moving
it changes the path used by subsequent commands.

### Everyday recipes

#### Create a group and an entry

List the root groups first. Create `work` if it does not exist, then add the entry:

```sh
kp ls
kp mkdir 'work'
kp add 'work/example-app' -u user@example.com -g -L 32
kpc 'work/example-app'
```

`-g` generates the password and `-L 32` sets its length. **The parent group must
already exist.** If `add` reports `Could not create entry with path
work/example-app.`, check `kp ls` and `kp ls 'work'` first. For nested groups,
create each parent in order. Use `edit` when you want to change an existing entry.

To supply your own password, use a hidden, single-line prompt instead:

```sh
kp add 'work/another-app' -u user@example.com -p
```

Both `add` and `edit` accept `-p` or `--password-prompt`. An empty answer cancels the
operation. These prompts require a terminal; generated passwords work in scripts.

#### Replace a stored password with a newly generated one

```sh
kp edit 'work/example-app' -g -L 32
kpc 'work/example-app'
```

This generates and saves a new password for the **existing entry**, preserving its
username and other fields. It updates the database immediately. You must also
change the password on the actual server or service; kp does not contact it.

If the service requires uppercase, lowercase, digits, and symbols:

```sh
kp edit 'work/example-app' -g -L 32 -l -U -n -s --every-group
```

Here `--every-group` requires at least one character from each selected character
set. To enter a replacement yourself, use `kp edit 'work/example-app' -p`.
Choose either `-g` or `-p` in a single command.

#### Find entries and read fields

```sh
kp ls 'work'
kp ls -R -f
kp search example-app
kp show 'work/example-app'
kp show 'work/example-app' -a UserName -a URL
```

`ls -R -f` lists entries recursively with flattened paths. A normal `show` masks
protected fields. Explicitly selecting `-a Password` prints the password in clear
text; `-s` reveals protected fields in the summary. For an entry with TOTP already
configured, `kp show 'work/example-app' --totp` prints its current code.

#### Copy a password

```sh
kpc 'work/example-app'
kp copy 'work/example-app' 30
```

The first uses the configured timeout (15 seconds by default); the second uses
30 seconds. `kpc ENTRY [SECONDS]` and `kp clip ENTRY [SECONDS]` are aliases for
`kp copy`. They copy the password from an exact entry path; they do not accept
KeePassXC's additional `clip` options. Use `search` to find the path first. An entry
named `-h` or `--help` can be addressed through its group path, such as
`work/--help`.

#### Update account details

```sh
kp edit 'work/example-app' -u user@example.com \
  --url 'https://app.example.com' \
  --notes 'Example application account'
```

Omitted fields retain their values. Editing account details without `-g` or `-p`
preserves the stored password.

#### Store and retrieve an attachment

Given an existing local file `./recovery.txt`:

```sh
kp attachment-import 'work/example-app' 'recovery.txt' './recovery.txt'
kp show 'work/example-app' --show-attachments
kp attachment-export 'work/example-app' 'recovery.txt' './recovery-copy.txt'
kp attachment-rm 'work/example-app' 'recovery.txt'
```

The attachment name and local filename are separate arguments. Import leaves the
source file in place; export writes a separate local file; `attachment-rm` removes
the attachment from the entry. Use `attachment-import -f` to replace an existing
attachment of the same name.

#### Rename and move an entry

```sh
kp edit 'work/example-app' -t 'example-app-old'
kp mkdir 'archive'
kp mv 'work/example-app-old' 'archive'
```

Create `archive` only if it does not exist. The resulting path is
`archive/example-app-old`. Renaming uses `edit -t`; `mv` takes an entry path and
an existing **destination group**, retaining the entry's title.

#### Generate a password or passphrase without saving an entry

```sh
kp generate -L 32
kp diceware -W 6
```

These print a generated value to stdout without opening or updating the database.
Use `add -g` or `edit -g` when you want the generated password saved to an entry.

### Command reference

This reference covers every command exposed by kp. Uppercase words are placeholders;
brackets indicate optional arguments. Append supported KeePassXC options to database
commands. Use separate short options and values (`-q -p`, `-L 32`).

For every upstream flag, run `kp help COMMAND` or `man keepassxc-cli`. Backend help
shows a required `database` argument; **omit it when calling through kp**. This keeps
the reference matched to your installed KeePassXC version.

#### Setup, help, and clipboard

| Command | Purpose |
| --- | --- |
| `kp init DATABASE` | Create config pointing at an existing database; refuse to overwrite existing config. |
| `kp doctor` | Check config, paths, and tools without retrieving credentials or unlocking the database. |
| `kp help [COMMAND]` | Show kp's overview or help for a command. `kp`, `kp -h`, and `kp --help` also show the overview. |
| `kp --version` | Print the installed kp version; `kp -v` is an alias. |
| `kp copy ENTRY [SECONDS]` | Copy the entry password with confidential/transient markers and conditional expiration; aliases: `kp clip` and `kpc`. |

#### Browse and inspect the database

| Command | Purpose |
| --- | --- |
| `kp ls [GROUP]` | List the root or a group's contents. `-R` includes descendants; `-f` flattens output. |
| `kp search QUERY` | Search entries and print matching paths for use with `show`, `copy`, or `edit`. |
| `kp show ENTRY` | Display an entry. `-a FIELD` selects fields, `--totp` prints a configured TOTP code, and `--show-attachments` lists attachments. |
| `kp db-info` | Display database metadata, such as its format, encryption settings, and entry/group counts. |
| `kp analyze -H FILE` | Check entry passwords against a local HIBP password-hash file. In KeePassXC 2.7.12, this file is required; the command does not download it. |
| `kp export` | Write an **unencrypted** database export to stdout. `-f xml`, `-f csv`, or `-f html` selects the format; XML is the default. |

For example, `kp export -f csv > export.csv` writes a plaintext export containing
credentials. Keep exports outside the repository. To back up the encrypted database,
copy the `.kdbx` file itself.

#### Change entries and groups

| Command | Purpose |
| --- | --- |
| `kp add ENTRY` | Create an entry inside an existing group. `-u` sets its username; `-g` generates a password; `-p` prompts for one. |
| `kp edit ENTRY` | Change selected fields of an existing entry. `-g` replaces its password, `-p` prompts for one, and `-t TITLE` renames it. |
| `kp mkdir GROUP` | Create a database group. For a nested path, create its parent groups first. |
| `kp mv ENTRY GROUP` | Move an entry to an existing destination group. This does not rename the entry or move a group. |
| `kp rm ENTRY` | Remove an entry, using the database's recycle-bin behavior described below. |
| `kp rmdir GROUP` | Remove a group **and its contents**; the group need not be empty. |

Writes take effect immediately. `rm` and `rmdir` do not prompt for confirmation.
With the recycle bin enabled, they normally move items there; with it disabled,
or when removing items already in the recycle bin, removal is permanent. This is
KeePassXC's [entry](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/src/cli/Remove.cpp)
and [group](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/src/cli/RemoveGroup.cpp)
removal behavior. Use KeePassium or KeePassXC's GUI to inspect or restore recycled
items when needed.

#### Attachments

| Command | Purpose |
| --- | --- |
| `kp attachment-import ENTRY NAME FILE` | Read a local file into a named entry attachment; `-f` allows replacement. |
| `kp attachment-export ENTRY NAME FILE` | Write a named attachment to a local file. |
| `kp attachment-rm ENTRY NAME` | Remove a named attachment from an entry. |

#### Tools that do not open the database

| Command | Purpose |
| --- | --- |
| `kp generate` | Print a random password. `-L` sets its length; `-l`, `-U`, `-n`, and `-s` select character sets. |
| `kp diceware` | Print a random passphrase. `-W` sets the word count; `-w FILE` supplies a custom word list. |
| `kp estimate [PASSWORD]` | Estimate password entropy. With no password argument, read one line from stdin. |

These commands need no configuration or Keychain access. For an existing single-line
entry password, use stdin to avoid putting it in command arguments or shell history:

```sh
kp show 'work/example-app' -a Password | kp estimate
```

`estimate` reads ordinary stdin, so typing directly into it is not a hidden prompt.
Its `--advanced` option prints password fragments as part of the analysis. See the
[upstream implementation](https://github.com/keepassxreboot/keepassxc/blob/2.7.12/src/cli/Estimate.cpp)
for these input/output details.

#### Database administration

Use `keepassxc-cli` directly for `db-create` (new database), `db-edit` (database
settings or master credentials), `merge` (combine databases), and `import` (create a
database from XML). Its interactive `open`/`close` commands are also outside kp's
scope. These commands need different database arguments, authentication flows, or
session state. Inspect their usage with `keepassxc-cli help COMMAND`.

Do not use `--no-password` through kp; it always authenticates with Keychain.
Hardware-key-only and passwordless databases are outside this release's scope.

#### Output and exit status

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
KP_CLIPBOARD_TIMEOUT=30 kpc 'work/example-app'
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

### Where the wrapper adds value

kp keeps KeePassXC's names and flags for database operations. Familiar commands
such as `edit -g` remain usable with upstream examples and help, while kp supplies
the database path, Keychain authentication, and hidden entry-password input.
The native `copy` workflow adds clipboard markers and conditional expiration;
`init` and `doctor` handle kp's own configuration.

Group creation is explicit: a typo in an entry path fails instead of creating an
unintended group. Backend command names and options stay compatible with KeePassXC;
`kp help COMMAND` and `man keepassxc-cli` provide the full reference for the
installed version.

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

`scripts/install.sh` manages installation and removal. `VERSION` supplies the release
number reported by the installed command.

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

[VERSION](VERSION) is the source of the version printed by `kp --version` and is
included in installations. An annotated Git tag identifies the exact released
commit. Version reporting also works in source downloads without `.git`.

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

[MIT](LICENSE).
