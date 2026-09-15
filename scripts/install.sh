#!/bin/bash
set -euo pipefail

fail() { printf 'kp install: %s\n' "$*" >&2; exit 1; }

action=${1:-install}
prefix=${2:-$HOME/.local}
[[ $# -le 2 ]] || fail 'usage: scripts/install.sh [install|uninstall] [PREFIX]'
[[ "$action" = install || "$action" = uninstall ]] || fail 'expected install or uninstall'
[[ "$prefix" = /* && "$prefix" != / ]] || fail 'PREFIX must be an absolute directory other than /'
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
package=$prefix/libexec/kp
marker='kp-managed-install-v1'

# A previous kp install may be replaced. Unrelated files and symlinks may not.
if [[ -e "$package" || -L "$package" ]]; then
    [[ ! -L "$package" && -d "$package" && -f "$package/.kp-install" ]] || fail "unmanaged path: $package"
    [[ $(cat "$package/.kp-install") = "$marker" ]] || fail "unrecognized installation: $package"
    [[ $(cd "$package" && pwd -P) != "$root" ]] || fail 'installation cannot replace the source checkout'
fi
for name in kp kpc; do
    target=$prefix/bin/$name
    if [[ -e "$target" || -L "$target" ]]; then
        [[ -L "$target" && $(readlink "$target") = "../libexec/kp/bin/$name" ]] || fail "refusing to replace unrelated command: $target"
    fi
done

if [[ "$action" = uninstall ]]; then
    for name in kp kpc; do
        target=$prefix/bin/$name
        [[ ! -L "$target" ]] || rm -- "$target"
    done
    [[ ! -d "$package" ]] || rm -rf -- "$package"
    printf 'Uninstalled kp from %s. Configuration and Keychain items were preserved.\n' "$prefix"
    exit
fi

mkdir -p -- "$prefix/bin" "$prefix/libexec"
staging=$(mktemp -d "$prefix/libexec/.kp-install.XXXXXX")
trap 'rm -rf -- "$staging"' EXIT
mkdir -p "$staging/bin" "$staging/lib"
install -m 755 "$root/bin/kp" "$staging/bin/kp"
ln -s kp "$staging/bin/kpc"
install -m 644 "$root/lib/kp.sh" "$root/lib/clipboard.applescript" "$staging/lib/"
install -m 644 "$root/VERSION" "$root/README.md" "$root/CHANGELOG.md" "$staging/"
if [[ -f "$root/LICENSE" ]]; then install -m 644 "$root/LICENSE" "$staging/"; fi
printf '%s\n' "$marker" > "$staging/.kp-install"
chmod 755 "$staging"

# Stage the complete payload before touching the old installation. Keep it for
# rollback if the final rename fails. Upgrades should run while kp is idle.
previous=
if [[ -d "$package" ]]; then
    previous=$staging/previous
    mv -- "$package" "$previous"
fi
if ! mv -- "$staging" "$package"; then
    [[ -z "$previous" ]] || mv -- "$previous" "$package"
    fail 'could not install package'
fi
staging=$package/previous
for name in kp kpc; do
    target=$prefix/bin/$name
    [[ -L "$target" ]] || ln -s "../libexec/kp/bin/$name" "$target"
done
printf 'Installed kp %s to %s/bin\n' "$(cat "$package/VERSION")" "$prefix"
printf 'Ensure %s/bin is on PATH. Next: kp init /path/to/vault.kdbx\n' "$prefix"
