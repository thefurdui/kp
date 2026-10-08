# Load after compinit with: source <(kp completion zsh)

_kp() {
    local output kind
    local -a candidates
    output=$(command kp __complete "${(@Q)words[1,CURRENT]}" 2>/dev/null)
    candidates=("${(@f)output}")
    kind=$candidates[1]
    candidates[1]=()
    case $kind in
        files) _files ;;
        commands|shells|entries|groups|paths)
            # compsys owns matching, quoting, and the user's listing/menu policy.
            compadd -a candidates ;;
    esac
}

compdef _kp kp kpc
