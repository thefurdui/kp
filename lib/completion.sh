# Sourced only for the private __complete protocol. Bash 3.2 compatible.
# shellcheck shell=bash

kp_completion_commands() {
    printf '%s\n' init doctor help completion copy clip strong renew ls search show \
        add edit mv mkdir rm rmdir db-info export analyze attachment-export \
        attachment-import attachment-rm generate diceware estimate --help --version
}

# Arguments are the command's words, dequoted by the shell adapter, through the
# word at the cursor (including an empty final word). The first output line is
# the kind; subsequent lines are literal candidates, never shell code.
kp_complete() {
    [[ $# -ge 2 ]] || return 2
    local invoked=${1##*/} command positional=0 options=true value_kind='' word kind=none
    shift
    if [[ $invoked = kpc ]]; then
        command=copy
    elif [[ $# = 1 ]]; then
        printf 'commands\n'
        kp_completion_commands
        return
    else
        command=$1
        shift
    fi

    while (($# > 1)); do
        word=$1
        shift
        if [[ -n $value_kind ]]; then value_kind=; continue; fi
        if [[ $options = true ]]; then
            case "$word" in
                --) options=false; continue ;;
                -h|--help) printf 'none\n'; return ;;
                -k|--key-file|-w|--word-list|-H|--hibp) value_kind=files; continue ;;
                -y|--yubikey|-u|--username|--url|--notes|-t|--title|-L|--length|-x|--exclude|-c|--custom|-a|--attributes|-W|--words)
                    value_kind=none; continue ;;
                -f|--format)
                    if [[ $command = export ]]; then value_kind=none; fi
                    continue ;;
                -*) continue ;;
            esac
        fi
        ((positional += 1))
    done
    if [[ -n $value_kind ]]; then
        kind=$value_kind
    elif [[ $options = true && $1 = -* ]]; then
        kind=none
    else
        case "$command:$positional" in
            help:0) kind=commands ;;
            completion:0) printf 'shells\nbash\nzsh\n'; return ;;
            init:0|attachment-import:2|attachment-export:2) kind=files ;;
            copy:0|clip:0|show:0|edit:0|renew:0|rm:0|attachment-import:0|attachment-export:0|attachment-rm:0)
                kind=entries ;;
            ls:0|rmdir:0|mkdir:0|add:0|strong:0) kind=groups ;;
            mv:*) kind=paths ;;
        esac
    fi
    printf '%s\n' "$kind"
    case "$kind" in
        commands) kp_completion_commands ;;
        entries|groups|paths) kp_completion_paths "$kind" "$1" ;;
    esac
}

kp_completion_paths() {
    local kind=$1 prefix=$2 listing candidate
    kp_load_config || return
    kp_require_database || return
    # Capture the whole listing first: a failed unlock must not publish partial
    # output. Only names are read, and nothing is cached on disk.
    listing=$(kp_run_database ls -R -f) || return
    [[ $kind = entries ]] || printf '/\n'
    while IFS= read -r candidate; do
        case "$candidate" in
            ''|'[empty]'|*/'[empty]') continue ;;
            */)
                [[ $kind != entries ]] || continue
                candidate=${candidate%/} ;;
            *) [[ $kind != groups ]] || continue ;;
        esac
        [[ $prefix != /* ]] || candidate=/$candidate
        printf '%s\n' "$candidate"
    done <<< "$listing"
}
