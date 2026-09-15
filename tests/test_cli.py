"""Regression tests with fake credentials; never access the user's Keychain."""

import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
KP = ROOT / "bin/kp"
STUB = r'''
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
root = Path(os.environ["FAKE_ROOT"])
mode = os.environ.get("FAKE_MODE", "")
args = sys.argv[1:]
data = b""
if name == "keepassxc-cli" and args[0] not in ("help", "--version", "generate", "diceware", "estimate"):
    data = sys.stdin.buffer.read()
elif name == "osascript" and args[1] == "copy":
    data = sys.stdin.buffer.read()
with (root / (name + ".jsonl")).open("a") as log:
    log.write(json.dumps({"args": args, "stdin": data.decode(), "environment": {
        key: os.environ[key] for key in ("master_password", "entry_password", "password") if key in os.environ
    }}) + "\n")
if name == "security":
    if mode == "keychain-fail":
        print("fake Keychain denied", file=sys.stderr)
        sys.exit(44)
    sys.stdout.buffer.write((root / "master").read_bytes() + b"\n")
elif name == "keepassxc-cli":
    if mode == "backend-fail":
        print("partial output")
        print("fake backend failure", file=sys.stderr)
        sys.exit(7)
    if mode == "move-bad-destination" and args[0] == "ls":
        print("fake missing group", file=sys.stderr)
        sys.exit(8)
    if mode == "move-missing-source" and args[0] == "show" and args[-1] == "Missing":
        print("fake missing entry", file=sys.stderr)
        sys.exit(6)
    if mode == "move-write-fail" and args[0] == "mv" and args[-2] == "Failing":
        print("fake save failure", file=sys.stderr)
        sys.exit(7)
    if args[0] == "show" and "Uuid" in args:
        print("uuid:" + args[-1].lstrip("/"))
    elif args[0] == "show":
        sys.stdout.buffer.write((root / "entry").read_bytes() + b"\n")
    else:
        print("fake " + args[0])
elif name == "osascript":
    if mode == "clipboard-fail":
        sys.exit(9)
    if args[1] == "copy":
        (root / "clipboard").write_bytes(data)
        print("42:fake-ownership-token")
'''


class Sandbox:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kp-test-")
        self.path = Path(self.temp.name)
        self.home = self.path / "home"
        self.home.mkdir()
        self.fakebin = self.path / "bin"
        self.fakebin.mkdir()
        self.database = self.path / "vault with spaces.kdbx"
        self.database.touch()
        self.master = "fake master \\ & secret"
        self.entry = "fake entry \\ & secret"
        (self.path / "master").write_text(self.master)
        (self.path / "entry").write_text(self.entry)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("KP_", "FAKE_"))}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
                        PATH=str(self.fakebin) + ":" + os.environ["PATH"],
                        KP_DATABASE=str(self.database), FAKE_ROOT=str(self.path))
        for name in ("security", "keepassxc-cli", "osascript"):
            target = self.fakebin / name
            target.write_text("#!" + sys.executable + "\n" + STUB)
            target.chmod(0o755)

    def close(self):
        # The fake cleanup exits immediately; allow it to close its log first.
        self.temp.cleanup()

    def run(self, *args, executable=KP, env=None):
        return subprocess.run([str(executable), *args], env=env or self.env,
                              input="", capture_output=True, text=True, timeout=15,
                              start_new_session=True)

    def log(self, name):
        path = self.path / (name + ".jsonl")
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def wait_cleanup(self):
        for _ in range(100):
            if any(call["args"][1] == "clear" for call in self.log("osascript")):
                return
            time.sleep(0.01)
        raise AssertionError("cleanup process did not start")

    def prompt(self, *args, answer):
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(str(KP), [str(KP), *args], self.env)
        output = b""
        sent = False
        deadline = time.monotonic() + 15
        status = None
        done = 0
        try:
            while time.monotonic() < deadline:
                readable, _, _ = select.select([fd], [], [], 0.1)
                if readable:
                    try:
                        chunk = os.read(fd, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output += chunk
                    if not sent and b"Entry password (hidden): " in output:
                        # Wait for Bash read -s to change the terminal mode.
                        time.sleep(0.05)
                        os.write(fd, answer)
                        sent = True
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    break
            else:
                raise AssertionError("hidden prompt timed out")
            if status is None or not done:
                _, status = os.waitpid(pid, 0)
                done = pid
            return os.waitstatus_to_exitcode(status), output.decode()
        finally:
            os.close(fd)
            if not done:
                try:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)
                except (ProcessLookupError, ChildProcessError):
                    pass


class CliTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.addCleanup(self.s.close)

    def test_help_version_and_backend_help_need_no_setup(self):
        self.s.env["KP_CONFIG_FILE"] = "/nonexistent/config"
        for args in [(), ("--help",), ("--version",), ("help", "show"),
                     ("help", "copy"), ("help", "init"), ("init", "--help"),
                     ("doctor", "--help"), ("add", "--help"), ("show", "--help"),
                     ("help", "mv"), ("mv", "--help"),
                     ("generate", "-L", "16")]:
            with self.subTest(args=args):
                result = self.s.run(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.s.log("security"), [])

    def test_arguments_and_master_password_are_preserved(self):
        result = self.s.run("show", "Work/A & B", "-a", "UserName")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.s.log("keepassxc-cli")[0]
        self.assertEqual(call["args"], ["show", str(self.s.database), "-q", "Work/A & B", "-a", "UserName"])
        self.assertEqual(call["stdin"], self.s.master + "\n")
        self.assertNotIn(self.s.master, json.dumps(call["args"]))
        self.assertNotIn(self.s.master, result.stdout + result.stderr)

    def test_failed_keychain_never_starts_backend(self):
        self.s.env["FAKE_MODE"] = "keychain-fail"
        result = self.s.run("ls")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Keychain", result.stderr)
        self.assertEqual(self.s.log("keepassxc-cli"), [])

    def test_multiline_or_empty_master_is_rejected(self):
        for master in ("", "line\nbreak", "trailing\n", "carriage\rreturn"):
            with self.subTest(master=master):
                (self.s.path / "master").write_text(master)
                self.assertNotEqual(self.s.run("ls").returncode, 0)
        self.assertEqual(self.s.log("keepassxc-cli"), [])

    def test_backend_exit_code_is_preserved(self):
        self.s.env["FAKE_MODE"] = "backend-fail"
        self.assertEqual(self.s.run("ls").returncode, 7)

    def test_move_batch_preserves_arguments_and_authenticates_once(self):
        entries = ["work/First entry", "work/A & B", "work/päss"]
        result = self.s.run("mv", *entries, "archive/")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.s.log("security")), 1)
        calls = self.s.log("keepassxc-cli")
        self.assertEqual([call["args"][0] for call in calls], ["ls", "show", "show", "show", "mv", "mv", "mv"])
        self.assertEqual([call["args"][-2:] for call in calls[-3:]], [[entry, "archive/"] for entry in entries])
        for call in calls:
            self.assertEqual(call["stdin"], self.s.master + "\n")
            self.assertNotIn(self.s.master, json.dumps(call["args"]))
            self.assertNotIn(self.s.master, call["environment"].values())
        for call in calls[1:4]:
            self.assertEqual(call["args"][-4:-1], ["-a", "Uuid", "--"])
        self.assertNotIn(self.s.entry, result.stdout + result.stderr)

    def test_move_single_entry_and_authentication_options(self):
        result = self.s.run("mv", "-q", "--key-file", "key with spaces", "One", "--yubikey=1", "archive")
        self.assertEqual(result.returncode, 0, result.stderr)
        for call in self.s.log("keepassxc-cli"):
            self.assertEqual(call["args"][3:7], ["-q", "--key-file", "key with spaces", "--yubikey=1"])
        self.assertEqual(self.s.log("keepassxc-cli")[-1]["args"][-2:], ["One", "archive"])

    def test_move_end_of_options_supports_paths_starting_with_dash(self):
        result = self.s.run("mv", "--", "-h", "--help", "-archive/")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [call for call in self.s.log("keepassxc-cli") if call["args"][0] == "mv"]
        self.assertEqual([call["args"][-3:] for call in calls], [["--", "-h", "-archive/"], ["--", "--help", "-archive/"]])

    def test_move_usage_errors_never_authenticate(self):
        for args in [(), ("One",), ("", "archive"), ("One", ""), ("--key-file",), ("--yubikey", ""),
                     ("--no-password", "One", "archive"), ("-f", "One", "archive")]:
            with self.subTest(args=args):
                result = self.s.run("mv", *args)
                self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.s.log("security"), [])

    def test_move_missing_source_or_destination_prevents_all_writes(self):
        for mode, expected_status in [("move-bad-destination", 8), ("move-missing-source", 6)]:
            with self.subTest(mode=mode):
                self.s.env["FAKE_MODE"] = mode
                result = self.s.run("mv", "One", "Missing", "archive")
                self.assertEqual(result.returncode, expected_status)
                self.assertIn("no entries moved", result.stderr)
        self.assertFalse(any(call["args"][0] == "mv" for call in self.s.log("keepassxc-cli")))

    def test_move_duplicate_entry_is_rejected_before_writes(self):
        result = self.s.run("mv", "One", "/One", "archive")
        self.assertEqual(result.returncode, 2)
        self.assertIn("specified more than once", result.stderr)
        self.assertFalse(any(call["args"][0] == "mv" for call in self.s.log("keepassxc-cli")))

    def test_move_write_failure_stops_with_completed_count(self):
        self.s.env["FAKE_MODE"] = "move-write-fail"
        result = self.s.run("mv", "First", "Failing", "Last", "archive")
        self.assertEqual(result.returncode, 7)
        self.assertIn("1 of 3 entries moved", result.stderr)
        self.assertIn("remaining entries were not attempted", result.stderr)
        calls = [call for call in self.s.log("keepassxc-cli") if call["args"][0] == "mv"]
        self.assertEqual([call["args"][-2] for call in calls], ["First", "Failing"])

    def test_move_failed_keychain_never_starts_backend(self):
        self.s.env["FAKE_MODE"] = "keychain-fail"
        result = self.s.run("mv", "One", "Two", "archive")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.s.log("keepassxc-cli"), [])

    def test_secrets_do_not_inherit_exported_variable_attributes(self):
        self.s.env.update(master_password="old master", entry_password="old entry", password="old password")
        result = self.s.run("copy", "Test", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.s.wait_cleanup()
        for name in ("security", "keepassxc-cli", "osascript"):
            for call in self.s.log(name):
                self.assertNotIn(self.s.master, call["environment"].values())
                self.assertNotIn(self.s.entry, call["environment"].values())

    def test_copy_preserves_multiline_unicode_and_schedules_without_secret(self):
        secret = " first \\ päss🔑\nsecond\n\n"
        (self.s.path / "entry").write_text(secret)
        result = self.s.run("Work/Test entry", "01", executable=ROOT / "bin/kpc")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual((self.s.path / "clipboard").read_text(), secret)
        self.s.wait_cleanup()
        calls = self.s.log("osascript")
        self.assertEqual(calls[0]["args"][1:], ["copy"])
        self.assertEqual(calls[1]["args"][1:], ["clear", "42:fake-ownership-token", "1"])
        self.assertNotIn(secret, result.stderr)
        self.assertNotIn(secret, json.dumps([call["args"] for call in calls]))

    def test_copy_failure_or_empty_password_does_not_touch_clipboard(self):
        for mode in ("keychain-fail", "backend-fail", ""):
            self.s.env["FAKE_MODE"] = mode
            (self.s.path / "entry").write_text("")
            with self.subTest(mode=mode):
                result = self.s.run("copy", "Missing")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("clipboard left unchanged", result.stderr)
        self.assertEqual(self.s.log("osascript"), [])

    def test_helper_failure_does_not_report_success(self):
        self.s.env["FAKE_MODE"] = "clipboard-fail"
        result = self.s.run("copy", "Test")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Password copied", result.stderr)

    def test_timeout_and_copy_arity_checked_before_authentication(self):
        for args in [("copy",), ("copy", "a", "1", "extra"),
                     *(("copy", "a", timeout) for timeout in ("0", "-1", "1.5", "3601", "99999999999999999999", "$(true)"))]:
            with self.subTest(args=args):
                self.assertEqual(self.s.run(*args).returncode, 2)
        self.assertEqual(self.s.log("security"), [])

    def test_config_is_literal_environment_wins_and_account_is_forwarded(self):
        config = self.s.path / "config"
        config.write_text("# test\ndatabase=/missing\nkeychain_service=literal $(touch nope) = test\n"
                          "keychain_account=account with spaces\nkey_file=\nclipboard_timeout=30\n")
        self.s.env["KP_CONFIG_FILE"] = str(config)
        result = self.s.run("ls")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.s.log("security")[0]["args"], ["find-generic-password", "-s",
                         "literal $(touch nope) = test", "-a", "account with spaces", "-w"])
        self.assertEqual(self.s.log("keepassxc-cli")[0]["args"][1], str(self.s.database))

    def test_unknown_or_missing_config_and_database_fail_before_keychain(self):
        config = self.s.path / "config"
        self.s.env["KP_CONFIG_FILE"] = str(config)
        self.assertNotEqual(self.s.run("ls").returncode, 0)
        config.write_text("unknown=value\n")
        self.assertNotEqual(self.s.run("ls").returncode, 0)
        config.write_text("database=/nonexistent\n")
        del self.s.env["KP_DATABASE"]
        self.assertNotEqual(self.s.run("ls").returncode, 0)
        self.assertEqual(self.s.log("security"), [])

    def test_key_file_forwarding(self):
        key = self.s.path / "test key.keyx"
        key.touch()
        self.s.env["KP_KEY_FILE"] = str(key)
        self.assertEqual(self.s.run("ls").returncode, 0)
        self.assertEqual(self.s.log("keepassxc-cli")[0]["args"][2:], ["-q", "--key-file", str(key)])

    def test_init_is_private_and_refuses_overwrite(self):
        result = self.s.run("init", str(self.s.database))
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.s.home / ".config/kp/config"
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        original = config.read_bytes()
        self.assertIn(str(self.s.database), original.decode())
        self.assertNotEqual(self.s.run("init", str(self.s.database)).returncode, 0)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(self.s.log("security"), [])

    def test_doctor_does_not_read_keychain(self):
        result = self.s.run("doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("were not tested", result.stdout)
        self.assertEqual(self.s.log("security"), [])

    def test_unknown_and_administration_commands_fail_without_auth(self):
        for command in ("typo", "db-create", "db-edit", "merge", "import", "open"):
            self.assertEqual(self.s.run(command).returncode, 2)
        self.assertEqual(self.s.log("security"), [])

    def test_option_values_are_not_mistaken_for_prompts_or_help(self):
        for value in ("-p", "--password-prompt", "--help", "a -p note"):
            result = self.s.run("add", "Test", "--notes", value, "-g")
            self.assertEqual(result.returncode, 0, result.stderr)
        for args in [("-p", "-g"), ("-qp",), ("--notes",)]:
            self.assertEqual(self.s.run("add", "Test", *args).returncode, 2)

    def test_add_and_edit_hidden_prompts(self):
        for command, option in (("add", "-p"), ("edit", "--password-prompt")):
            with self.subTest(command=command):
                code, output = self.s.prompt(command, "Test", option, answer=b" fake \\ value \n")
                self.assertEqual(code, 0, output)
                self.assertNotIn("fake \\ value", output)
                self.assertEqual(self.s.log("keepassxc-cli")[-1]["stdin"], self.s.master + "\n fake \\ value \n")

    def test_empty_prompt_cancels_without_backend(self):
        code, output = self.s.prompt("add", "Test", "-p", answer=b"\n")
        self.assertNotEqual(code, 0)
        self.assertIn("canceled", output)
        self.assertEqual(self.s.log("keepassxc-cli"), [])

    def test_prompt_requires_a_terminal(self):
        result = self.s.run("add", "Test", "-p")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interactive terminal", result.stderr)
        self.assertEqual(self.s.log("keepassxc-cli"), [])

    def test_install_upgrade_symlink_resolution_and_uninstall(self):
        prefix = self.s.path / "install with spaces"
        installer = ROOT / "scripts/install.sh"
        for _ in range(2):
            result = subprocess.run(["/bin/bash", str(installer), "install", str(prefix)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        installed = prefix / "bin/kp"
        self.assertEqual(self.s.run("--version", executable=installed).stdout.strip(),
                         "kp " + (ROOT / "VERSION").read_text().strip())
        result = self.s.run("Test", "1", executable=prefix / "bin/kpc")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.s.wait_cleanup()
        config = self.s.home / "preserved-config"
        config.write_text("preserve me")
        result = subprocess.run(["/bin/bash", str(installer), "uninstall", str(prefix)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(installed.exists())
        self.assertFalse((prefix / "libexec/kp").exists())
        self.assertEqual(config.read_text(), "preserve me")
        self.assertTrue(self.s.database.exists())

    def test_installer_refuses_unrelated_commands_and_directories(self):
        prefix = self.s.path / "install"
        (prefix / "bin").mkdir(parents=True)
        target = prefix / "bin/kpc"
        target.write_text("unrelated")
        installer = ROOT / "scripts/install.sh"
        for action in ("install", "uninstall"):
            result = subprocess.run(["/bin/bash", str(installer), action, str(prefix)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), "unrelated")
        self.assertFalse((prefix / "bin/kp").exists())
        target.unlink()
        package = prefix / "libexec/kp"
        package.mkdir(parents=True)
        (package / "valuable").write_text("unrelated")
        result = subprocess.run(["/bin/bash", str(installer), "install", str(prefix)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((package / "valuable").read_text(), "unrelated")


if __name__ == "__main__":
    unittest.main()
