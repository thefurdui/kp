# Sourced by bin/kp. Compatible with macOS's Bash 3.2.
# shellcheck shell=bash

kp_error() {
    printf 'kp: %s\n' "$*" >&2
    return 1
}

kp_help() {
    cat <<'EOF'
Usage: kp COMMAND [ARGS...]
       kpc ENTRY [SECONDS]

Setup:
  init DATABASE             Create config for an existing database
  doctor                    Check setup without retrieving credentials
  help [COMMAND]            Show kp or KeePassXC command help
  --version                 Print the kp version

Everyday use:
  ls [GROUP]                List entries
  search QUERY              Find entry paths
  show ENTRY [OPTIONS]      Show an entry (password hidden by default)
  copy ENTRY [SECONDS]      Copy password; clear after 15 seconds by default
  add ENTRY [OPTIONS]       Add entry; -g generates, -p prompts secretly
  edit ENTRY [OPTIONS]      Edit entry; -p prompts secretly

Also supported:
  mkdir, mv, rm, rmdir, db-info, export, analyze,
  attachment-export, attachment-import, attachment-rm
  generate, diceware, estimate (no database or Keychain needed)

KeePassXC options are forwarded; omit the database argument.
Use separate short options, e.g. -q -p instead of -qp.
Config: ${XDG_CONFIG_HOME:-$HOME/.config}/kp/config
Override the config location with KP_CONFIG_FILE.
EOF
}

kp_config_path() {
    printf '%s\n' "${KP_CONFIG_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kp/config}"
}

kp_command_help() {
    case "$1" in
        init) printf 'Usage: kp init DATABASE\nCreate config for an existing database; never overwrite existing config.\n' ;;
        doctor) printf 'Usage: kp doctor\nCheck configuration and dependencies without retrieving credentials.\n' ;;
        copy|clip|kpc) printf 'Usage: kp copy ENTRY [SECONDS]\n       kpc ENTRY [SECONDS]\n' ;;
        *) kp_require_backend && keepassxc-cli help "$1" ;;
    esac
}

kp_load_config() {
    local file line key value line_number=0
    file=$(kp_config_path)
    database=
    keychain_service=KeePassVault
    keychain_account=
    key_file=
    clipboard_timeout=15
    if [[ -e "$file" || -L "$file" ]]; then
        [[ -f "$file" && -r "$file" ]] || { kp_error "cannot read config: $file"; return 1; }
        while IFS= read -r line || [[ -n "$line" ]]; do
            ((line_number += 1))
            line=${line%$'\r'}
            case "$line" in ''|'#'*) continue ;; esac
            [[ "$line" = *=* ]] || { kp_error "expected key=value at $file:$line_number"; return 1; }
            key=${line%%=*}
            value=${line#*=}
            case "$key" in
                database) database=$value ;;
                keychain_service) keychain_service=$value ;;
                keychain_account) keychain_account=$value ;;
                key_file) key_file=$value ;;
                clipboard_timeout) clipboard_timeout=$value ;;
                *) kp_error "unknown config key at $file:$line_number: $key"; return 1 ;;
            esac
        done < "$file"
    elif [[ -n "${KP_CONFIG_FILE:-}" ]]; then
        kp_error "config does not exist: $file"
        return 1
    fi
    # Configuration is data, never sourced or evaluated. Environment wins.
    database=${KP_DATABASE-$database}
    keychain_service=${KP_KEYCHAIN_SERVICE-$keychain_service}
    keychain_account=${KP_KEYCHAIN_ACCOUNT-$keychain_account}
    key_file=${KP_KEY_FILE-$key_file}
    clipboard_timeout=${KP_CLIPBOARD_TIMEOUT-$clipboard_timeout}
}

kp_require_backend() {
    command -v keepassxc-cli >/dev/null 2>&1 || {
        kp_error 'keepassxc-cli is missing; install KeePassXC (see README)'
        return 1
    }
}

kp_require_database() {
    [[ -n "$database" ]] || { kp_error 'no database configured; run: kp init /absolute/path/to/vault.kdbx'; return 1; }
    [[ "$database" = /* && -f "$database" && -r "$database" ]] || {
        kp_error "database must be an absolute path to a readable file: $database"
        return 1
    }
    [[ -n "$keychain_service" ]] || { kp_error 'keychain_service must not be empty'; return 1; }
    if [[ -n "$key_file" && ( "$key_file" != /* || ! -f "$key_file" || ! -r "$key_file" ) ]]; then
        kp_error "key_file must be an absolute path to a readable file: $key_file"
        return 1
    fi
    kp_require_backend || return
    command -v security >/dev/null 2>&1 || { kp_error 'macOS security command is missing'; return 1; }
}

kp_validate_timeout() {
    case "$1" in ''|*[!0-9]*) kp_error 'clipboard timeout must be 1–3600 whole seconds'; return 1 ;; esac
    if [[ ${#1} -gt 4 ]] || ((10#$1 < 1 || 10#$1 > 3600)); then
        kp_error 'clipboard timeout must be 1–3600 whole seconds'
        return 1
    fi
}

kp_init() {
    [[ $# = 1 ]] || { kp_error 'usage: kp init DATABASE'; return 2; }
    [[ -f "$1" && -r "$1" ]] || { kp_error "database is not a readable file: $1"; return 1; }
    local file absolute_database
    file=$(kp_config_path)
    absolute_database=$(cd -P -- "$(dirname -- "$1")" && printf '%s/%s' "$PWD" "${1##*/}") || return
    case "$absolute_database" in *$'\n'*|*$'\r'*) kp_error 'database path cannot contain line breaks'; return 1 ;; esac
    [[ ! -e "$file" && ! -L "$file" ]] || { kp_error "config already exists: $file (edit it directly)"; return 1; }
    (
        umask 077
        mkdir -p -- "$(dirname -- "$file")" || exit 1
        set -o noclobber
        {
            printf '# kp configuration: literal values, no quotes or shell expansion.\n'
            printf 'database=%s\n' "$absolute_database"
            printf 'keychain_service=KeePassVault\nkeychain_account=\nkey_file=\nclipboard_timeout=15\n'
        } > "$file"
    ) || { kp_error "could not create config: $file"; return 1; }
    printf 'Created %s\nRun kp doctor to check setup.\n' "$file"
}

kp_doctor() {
    kp_require_database || return
    kp_validate_timeout "$clipboard_timeout" || return
    command -v osascript >/dev/null 2>&1 || { kp_error 'macOS osascript command is missing'; return 1; }
    command -v nohup >/dev/null 2>&1 || { kp_error 'nohup command is missing'; return 1; }
    printf 'kp %s\n' "$(cat "$KP_ROOT/VERSION")"
    printf 'Config: %s\nDatabase: %s\n' "$(kp_config_path)" "$database"
    printf 'Keychain service: %s\nKeychain account: %s\n' "$keychain_service" "${keychain_account:-(any matching account)}"
    printf 'Clipboard timeout: %s seconds\n' "$clipboard_timeout"
    keepassxc-cli --version || return
    printf 'Setup checks passed. Credentials and database unlock were not tested.\n'
}

# Only add/edit need argument inspection: their extra prompt shares stdin with
# the database password. Consume option values so a note containing "-p" is data.
kp_entry_options() {
    entry_prompt=false
    entry_generate=false
    entry_help=false
    while (($#)); do
        case "$1" in
            --) break ;;
            -h|--help) entry_help=true ;;
            -p|--password-prompt) entry_prompt=true ;;
            -g|--generate) entry_generate=true ;;
            -k|--key-file|-y|--yubikey|-u|--username|--url|--notes|-t|--title|-L|--length|-x|--exclude|-c|--custom)
                [[ $# -ge 2 ]] || { kp_error "missing value for $1"; return 2; }
                shift ;;
            --no-password) kp_error '--no-password is incompatible with Keychain authentication'; return 2 ;;
            --*) ;; # KeePassXC validates long options, including --option=value.
            -??*) kp_error "use separate short options and values: $1"; return 2 ;;
        esac
        shift
    done
    if [[ "$entry_prompt" = true && "$entry_generate" = true ]]; then
        kp_error 'choose -p (prompt) or -g (generate), not both'
        return 2
    fi
}

kp_run_database() {
    local command=$1 master_password entry_password result
    export -n master_password entry_password
    shift
    local security_args=(-s "$keychain_service")
    local auth_args=(-q)
    [[ -z "$keychain_account" ]] || security_args+=(-a "$keychain_account")
    [[ -z "$key_file" ]] || auth_args+=(--key-file "$key_file")

    # The sentinel preserves trailing line breaks so they can be rejected, not
    # silently removed by command substitution. Neither secret becomes argv.
    master_password=$(
        security find-generic-password "${security_args[@]}" -w
        result=$?
        printf '\001'
        exit "$result"
    ) || { kp_error 'could not read database password from Keychain; check service/account and access permissions'; return 1; }
    master_password=${master_password%$'\001'}
    master_password=${master_password%$'\n'}
    case "$master_password" in
        ''|*$'\n'*|*$'\r'*) kp_error 'database password must be nonempty and single-line'; return 1 ;;
    esac

    if [[ "${entry_prompt:-false}" = true ]]; then
        # /dev/tty keeps redirected stdin from accidentally becoming a password.
        if ! { printf 'Entry password (hidden): ' > /dev/tty; } 2>/dev/null; then
            kp_error '-p requires an interactive terminal; use -g to generate a password'
            return 1
        fi
        IFS= read -r -s entry_password < /dev/tty
        result=$?
        printf '\n' > /dev/tty
        [[ $result = 0 && -n "$entry_password" ]] || { kp_error 'canceled; empty password or end of input'; return 1; }
        printf '%s\n%s\n' "$master_password" "$entry_password" |
            keepassxc-cli "$command" "$database" "${auth_args[@]}" "$@"
    else
        printf '%s\n' "$master_password" |
            keepassxc-cli "$command" "$database" "${auth_args[@]}" "$@"
    fi
    result=$?
    unset master_password entry_password
    return "$result"
}

kp_copy() {
    [[ $# -ge 1 && $# -le 2 && -n "$1" ]] || { kp_error 'usage: kp copy ENTRY [SECONDS] (or kpc ENTRY [SECONDS])'; return 2; }
    local timeout=${2-$clipboard_timeout} password receipt result
    export -n password
    kp_validate_timeout "$timeout" || return 2
    command -v osascript >/dev/null 2>&1 || { kp_error 'macOS osascript command is missing'; return 1; }
    command -v nohup >/dev/null 2>&1 || { kp_error 'nohup command is missing'; return 1; }
    # Preserve embedded/trailing newlines. Strip only KeePassXC's output newline.
    password=$(
        kp_run_database show -a Password -- "$1"
        result=$?
        printf '\001'
        exit "$result"
    ) || { kp_error 'password lookup failed; clipboard left unchanged'; return 1; }
    password=${password%$'\001'}
    password=${password%$'\n'}
    [[ -n "$password" ]] || { kp_error 'entry password is empty; clipboard left unchanged'; return 1; }
    receipt=$(printf '%s' "$password" | osascript "$KP_ROOT/lib/clipboard.applescript" copy) || {
        kp_error 'could not write clipboard'
        return 1
    }
    unset password
    # Receipt contains only a generation number and random ownership token.
    # All descriptors are detached so scripts can capture stdout without waiting.
    nohup osascript "$KP_ROOT/lib/clipboard.applescript" clear "$receipt" "$((10#$timeout))" \
        </dev/null >/dev/null 2>&1 &
    printf 'Password copied; expires in %s seconds.\n' "$((10#$timeout))" >&2
}

kp_main() {
    local command=${1:-help}
    local entry_prompt=false entry_generate=false entry_help=false
    (($# == 0)) || shift
    case "$command" in
        help|-h|--help)
            [[ $# -le 1 ]] || { kp_error 'usage: kp help [COMMAND]'; return 2; }
            if [[ $# = 0 ]]; then kp_help; else kp_command_help "$1"; fi
            return ;;
        --version|-v)
            [[ $# = 0 ]] || { kp_error '--version takes no arguments'; return 2; }
            printf 'kp %s\n' "$(cat "$KP_ROOT/VERSION")"; return ;;
        init)
            if [[ $# = 1 && ( $1 = --help || $1 = -h ) ]]; then kp_command_help init; else kp_init "$@"; fi
            return ;;
        generate|diceware|estimate) kp_require_backend && keepassxc-cli "$command" "$@"; return ;;
        copy|clip)
            if [[ ${1:-} = --help || ${1:-} = -h ]]; then
                kp_command_help copy; return
            fi
            [[ $# -ge 1 && $# -le 2 && -n "$1" ]] || { kp_error 'usage: kp copy ENTRY [SECONDS] (or kpc ENTRY [SECONDS])'; return 2; } ;;
        doctor)
            if [[ $# = 1 && ( $1 = --help || $1 = -h ) ]]; then kp_command_help doctor; return; fi
            [[ $# = 0 ]] || { kp_error 'doctor takes no arguments'; return 2; } ;;
        add|edit) kp_entry_options "$@" || return
            if [[ "$entry_help" = true ]]; then kp_require_backend && keepassxc-cli help "$command"; return; fi ;;
        ls|search|show|mkdir|mv|rm|rmdir|db-info|export|analyze|attachment-export|attachment-import|attachment-rm)
            if [[ $# = 1 && ( $1 = --help || $1 = -h ) ]]; then
                kp_require_backend && keepassxc-cli help "$command"; return
            fi ;;
        *) kp_error "unsupported command: $command (see kp help; use keepassxc-cli directly for database administration)"; return 2 ;;
    esac
    kp_load_config || return
    if [[ "$command" = doctor ]]; then kp_doctor; return; fi
    kp_require_database || return
    case "$command" in
        copy|clip) kp_copy "$@" ;;
        *) kp_run_database "$command" "$@" ;;
    esac
}
