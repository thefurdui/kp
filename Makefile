PREFIX ?= $(HOME)/.local
PYTHON ?= python3

.PHONY: help install uninstall test test-integration lint

help:
	@printf '%s\n' 'make install       Install into ~/.local (override PREFIX=/absolute/path)' 'make uninstall     Remove installed code; preserve config and Keychain' 'make test          Run isolated CLI tests (Python 3)' 'make test-integration  Test real KeePassXC and a private macOS pasteboard' 'make lint          Check Bash syntax and ShellCheck'

install:
	/bin/bash scripts/install.sh install "$(PREFIX)"

uninstall:
	/bin/bash scripts/install.sh uninstall "$(PREFIX)"

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_cli.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_completion.py' -v

test-integration:
	$(PYTHON) -m unittest discover -s tests -p 'test_integration.py' -v

lint:
	@for script in bin/kp lib/kp.sh lib/completion.sh completions/kp.bash scripts/install.sh; do /bin/bash -n "$$script" || exit; done
	zsh -n completions/kp.zsh
	shellcheck -x -P . bin/kp lib/kp.sh lib/completion.sh completions/kp.bash scripts/install.sh
