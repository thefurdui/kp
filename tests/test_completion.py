"""Completion regressions, including real Tab presses in clean Bash/Zsh PTYs."""

import os
import pty
import re
import select
import shutil
import signal
import time
import unittest

from test_cli import ROOT, Sandbox


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.addCleanup(self.s.close)
        self.s.env["PATH"] = str(ROOT / "bin") + os.pathsep + self.s.env["PATH"]
        self.listing = self.s.path / "listing"
        self.listing.write_text(
            "github\ngitlab\nUnique key\nwork/\nwork/Alpha one\nwork/Alpha two\n"
            "work/Sub/\nwork/Sub/Nested entry\nEmpty/\nEmpty/[empty]\n"
            "literal[bracket]\nquote's key\ndouble\"quote\nback\\slash\n"
            "service:account\nkey=value\n$(touch PWNED)\nКлюч\nHello!world\n"
        )

    def complete(self, *words):
        result = self.s.run("__complete", *words)
        self.assertEqual(result.stderr, "")
        return result.stdout.splitlines()

    def test_setup_and_command_completion_need_no_credentials(self):
        self.s.env["KP_CONFIG_FILE"] = "/missing/config"
        for shell in ("bash", "zsh"):
            self.assertEqual(self.s.run("completion", shell).returncode, 0)
        for words in (("kp", ""), ("kp", "help", "")):
            candidates = self.complete(*words)
            self.assertEqual(candidates[0], "commands")
            self.assertIn("renew", candidates)
            self.assertIn("completion", candidates)
        self.assertEqual(self.complete("kp", "completion", ""), ["shells", "bash", "zsh"])
        for args in ((), ("fish",), ("bash", "extra")):
            self.assertEqual(self.s.run("completion", *args).returncode, 2)
        self.assertEqual(self.s.log("security"), [])

    def test_entry_and_group_contexts(self):
        for command in ("copy", "clip", "show", "edit", "renew", "rm",
                        "attachment-import", "attachment-export", "attachment-rm"):
            with self.subTest(command=command):
                candidates = self.complete("kp", command, "")
                self.assertEqual(candidates[0], "entries")
                self.assertIn("work/Alpha one", candidates)
                self.assertNotIn("work", candidates)
                self.assertNotIn("Empty/[empty]", candidates)
        self.assertIn("github", self.complete("kpc", "gi"))
        self.assertIn("/work/Alpha one", self.complete("kpc", "/wo"))
        for command in ("ls", "rmdir", "mkdir", "add", "strong"):
            self.assertEqual(self.complete("kp", command, ""),
                             ["groups", "/", "work", "work/Sub", "Empty"])
        for words in (("kp", "mv", ""), ("kp", "mv", "github", "gitlab", "")):
            candidates = self.complete(*words)
            self.assertEqual(candidates[0], "paths")
            self.assertIn("github", candidates)
            self.assertIn("work", candidates)
        self.assertEqual(self.s.log("osascript"), [])
        self.assertTrue(all(call["args"][0] == "ls" for call in self.s.log("keepassxc-cli")))

    def test_options_and_non_entry_arguments_do_not_suggest_passwords(self):
        for words in (("kpc", "github", ""), ("kp", "renew", "github", ""),
                      ("kp", "show", "-a", ""), ("kp", "edit", "--notes", ""),
                      ("kp", "attachment-rm", "github", ""), ("kp", "search", ""),
                      ("kp", "generate", ""), ("kp", "show", "--help", "")):
            self.assertEqual(self.complete(*words), ["none"])
        for words in (("kp", "init", ""), ("kp", "show", "-k", ""),
                      ("kp", "attachment-import", "github", "file", "")):
            self.assertEqual(self.complete(*words), ["files"])
        self.assertEqual(self.s.log("security"), [])
        for words in (("kp", "edit", "--notes", "two words", ""),
                      ("kp", "show", "-a", "UserName", ""),
                      ("kp", "show", "--attributes=UserName", ""),
                      ("kp", "renew", "--", "-")):
            self.assertEqual(self.complete(*words)[0], "entries")

    def test_failed_lookup_is_silent_and_discards_partial_candidates(self):
        for mode in ("keychain-fail", "backend-fail"):
            self.s.env["FAKE_MODE"] = mode
            self.assertEqual(self.complete("kpc", ""), ["entries"])
        self.s.env["KP_CONFIG_FILE"] = "/missing/config"
        self.assertEqual(self.complete("kpc", ""), ["entries"])

    def shell_input(self, shell, line):
        """Execute completed text through harmless capture functions, never kp."""
        executable = shutil.which(shell)
        if not executable:
            self.skipTest(shell + " is not installed")
        env = dict(self.s.env, TERM="dumb", PS1="KP_READY> ", PS2="", HISTFILE="/dev/null")
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.s.path)
            args = [executable, "--noprofile", "--norc", "-i"] if shell == "bash" else [executable, "-f", "-i"]
            os.execve(executable, args, env)

        def receive(marker):
            output = b""
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if select.select([fd], [], [], 0.1)[0]:
                    output += os.read(fd, 65536)
                    if marker in output:
                        return output.decode(errors="replace")
            raise AssertionError("shell timed out: " + repr(output))

        try:
            # zsh may replace an inherited PS1, so wait for an explicit marker.
            setup = "PS1='KP_READY> '; "
            if shell == "zsh":
                setup += "autoload -Uz compinit; compinit -D -i; bindkey -e; "
            else:
                setup += "bind 'set show-all-if-ambiguous off'; bind 'set bell-style none'; "
            setup += "source <(command kp completion " + shell + "); "
            setup += "kp() { printf '__ARG__<%s>\\n' \"$@\"; printf '__END__\\n'; }; kpc() { kp \"$@\"; }; "
            setup += "printf '\\nSETUP_DONE\\n'\n"
            os.write(fd, setup.encode())
            receive(b"\r\nSETUP_DONE\r\n")
            # Give the line editor time to start before sending Tab.
            time.sleep(0.05)
            os.write(fd, line.encode() + b"\n")
            output = receive(b"\r\n__END__\r\n")
            return re.findall(r"__ARG__<(.*?)>\r?\n", output), output
        finally:
            os.close(fd)
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)

    def test_real_tab_completes_and_quotes_entry_names(self):
        cases = [
            ("kpc Uniq\tNEXT", ["Unique key", "NEXT"]),
            ("kpc work/Alpha\\ o\t", ["work/Alpha one"]),
            ('kpc "work/Alpha o\t', ["work/Alpha one"]),
            ("kpc 'work/Alpha o\t", ["work/Alpha one"]),
            ('kpc "Uniq"\t', ["Unique key"]),
            ("kpc literal\\[\t", ["literal[bracket]"]),
            ("kpc quo\t", ["quote's key"]),
            ("kpc 'quo\t", ["quote's key"]),
            ("kpc doub\t", ['double"quote']),
            ('kpc "doub\t', ['double"quote']),
            ("kpc back\t", ["back\\slash"]),
            ('kpc "back\t', ["back\\slash"]),
            ("kpc service:a\t", ["service:account"]),
            ("kpc key=v\t", ["key=value"]),
            ("kpc \\$\t", ["$(touch PWNED)"]),
            ('kpc "\\$\t', ["$(touch PWNED)"]),
            ("kpc Кл\t", ["Ключ"]),
            ('kpc "Hell\t', ["Hello!world"]),
            ("kp show Uniq\t", ["show", "Unique key"]),
            ("kp renew Uniq\t", ["renew", "Unique key"]),
            ("kp edit --notes 'two words' Uniq\t", ["edit", "--notes", "two words", "Unique key"]),
        ]
        for shell in ("bash", "zsh"):
            for line, expected in cases:
                with self.subTest(shell=shell, line=line):
                    args, output = self.shell_input(shell, line)
                    self.assertEqual(args, expected, output)
        self.assertFalse((self.s.path / "PWNED").exists())
        self.assertEqual(self.s.log("osascript"), [])

    def test_real_tab_shared_prefix_listing_and_no_match(self):
        (self.s.path / "nonexistent-local-file").touch()
        (self.s.path / "github").mkdir()
        for shell in ("bash", "zsh"):
            tabs = "\t\t\t" if shell == "bash" else "\t\t"
            for line, expected in (("kpc gi\t", ["git"]),
                                   ("kpc gi" + tabs + "l\t", ["gitlab"]),
                                   ("kpc gith\tNEXT", ["github", "NEXT"]),
                                   ("kpc nonexistent\t", ["nonexistent"]),
                                   ("kp sh\t", ["show"])):
                with self.subTest(shell=shell, line=line):
                    args, output = self.shell_input(shell, line)
                    self.assertEqual(args, expected, output)
                    if "\t\t" in line:
                        self.assertIn("github", output)
                        self.assertIn("gitlab", output)


if __name__ == "__main__":
    unittest.main()
