# Load with: source <(kp completion bash)
# Works with macOS Bash 3.2; bash-completion is not required.

# Decode shell quoting without eval: a vault name must never execute code.
_kp_unquote() {
    local input=$1 quote='' char next i
    REPLY=
    for ((i = 0; i < ${#input}; i++)); do
        char=${input:i:1}
        case "$quote:$char" in
            ":'"|':"') quote=$char ;;
            "':'"|'":"') quote= ;;
            ":\\"|"\":\\")
                next=${input:i+1:1}
                if [[ -z $quote || $next = [\$\`\"\\] ]]; then
                    REPLY=$REPLY$next
                    ((i += 1))
                else
                    REPLY=$REPLY$char
                fi ;;
            *) REPLY=$REPLY$char ;;
        esac
    done
    QUOTING=$quote
}

_kp_quote() {
    local input=$1 quote=$2 char i
    REPLY=
    for ((i = 0; i < ${#input}; i++)); do
        char=${input:i:1}
        case "$quote:$char" in
            "':'") REPLY=$REPLY"'\\''" ;;
            "':"*) REPLY=$REPLY$char ;;
            '":!') REPLY=$REPLY"\"'!'\"" ;;
            '":$'|'":`'|'":"'|"\":\\") REPLY=$REPLY\\$char ;;
            '":'*) REPLY=$REPLY$char ;;
            :[a-zA-Z0-9_./,:=@%+-]) REPLY=$REPLY$char ;;
            *) REPLY=$REPLY\\$char ;;
        esac
    done
}

_kp_complete() {
    local REPLY QUOTING quote current fragment trim='' candidate kind i join=false
    local -a words=()
    COMPREPLY=()
    # Bash 4+ may split these word-break characters into separate COMP_WORDS.
    # Rejoin them without changing the user's global COMP_WORDBREAKS setting.
    for ((i = 0; i <= COMP_CWORD; i++)); do
        case "${COMP_WORDS[i]}" in
            :|=)
                words[${#words[@]}-1]+=${COMP_WORDS[i]}
                join=true ;;
            *)
                if [[ $join = true ]]; then
                    words[${#words[@]}-1]+=${COMP_WORDS[i]}
                    join=false
                else
                    words+=("${COMP_WORDS[i]}")
                fi ;;
        esac
    done
    for ((i = 0; i < ${#words[@]}; i++)); do
        _kp_unquote "${words[i]}"
        words[i]=$REPLY
    done
    current=${words[${#words[@]}-1]}
    quote=$QUOTING
    _kp_unquote "$2"
    fragment=$REPLY
    # Readline replaces only the suffix after an unquoted ':' or '='.
    [[ $current != *"$fragment" ]] || trim=${current%"$fragment"}
    while IFS= read -r candidate; do
        if [[ -z ${kind:-} ]]; then kind=$candidate; continue; fi
        if [[ $candidate = "$current"* ]]; then
            _kp_quote "${candidate#"$trim"}" "$quote"
            COMPREPLY+=("$REPLY")
        fi
    done < <(command kp __complete "${words[@]}" 2>/dev/null)
    if [[ ${kind:-} = files ]]; then
        while IFS= read -r candidate; do
            _kp_quote "${candidate#"$trim"}" "$quote"
            COMPREPLY+=("$REPLY")
        done < <(compgen -f -- "$current")
    fi
}

# Let Readline handle common prefixes, match listing, and final spaces. Quote
# literal names ourselves: Bash 3.2's filename quoting can expand '$()' and treats
# entries that happen to match local directories as directories.
# No fallback to local filenames when the vault has no matching entry.
complete -F _kp_complete kp kpc
