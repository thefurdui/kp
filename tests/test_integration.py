"""Native tests: disposable KDBX, fake Keychain, private named pasteboard."""

import shutil
import subprocess
import sys
import unittest
import uuid

import test_cli as cli

HELPER = cli.ROOT / "lib/clipboard.applescript"


@unittest.skipUnless(sys.platform == "darwin", "macOS native integration")
class PasteboardTests(unittest.TestCase):
    def setUp(self):
        self.board = "org.kp.tests." + str(uuid.uuid4())
        self.addCleanup(self.release_board)

    def release_board(self):
        self.script('board\'s releaseGlobally()\nreturn ""')

    def script(self, body):
        script = ('use framework "AppKit"\n'
                  'use framework "Foundation"\n'
                  'on run argv\n'
                  'set board to current application\'s NSPasteboard\'s pasteboardWithName:(item 1 of argv)\n'
                  + body + '\nend run\n')
        result = subprocess.run(["/usr/bin/osascript", "-", self.board], input=script,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.rstrip("\n")

    def copy(self, text):
        result = subprocess.run(["/usr/bin/osascript", str(HELPER), "copy", self.board],
                                input=text, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def clear(self, receipt, seconds="0"):
        result = subprocess.run(["/usr/bin/osascript", str(HELPER), "clear", receipt, seconds, self.board],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def read_text(self):
        # Base64 avoids command-output newline normalization in the assertion.
        import base64
        encoded = self.script('set value to board\'s stringForType:"public.utf8-plain-text"\n'
                              'if value is missing value then return ""\n'
                              'set dataBytes to value\'s dataUsingEncoding:(current application\'s NSUTF8StringEncoding)\n'
                              'return (dataBytes\'s base64EncodedStringWithOptions:0) as text')
        return base64.b64decode(encoded).decode()

    def test_native_copy_preserves_text_and_marks_confidential_transient(self):
        secret = " synthetic päss🔑 \\ \nsecond line\n\n"
        receipt = self.copy(secret)
        self.assertEqual(self.read_text(), secret)
        for marker in ("org.nspasteboard.ConcealedType", "org.nspasteboard.TransientType"):
            self.assertEqual(self.script('return (board\'s stringForType:"' + marker + '") as text'), "1")
        self.clear(receipt, "1")
        self.assertEqual(self.read_text(), "")

    def test_stale_timer_preserves_newer_copy(self):
        first = self.copy("first synthetic password")
        second = self.copy("second synthetic password")
        self.clear(first)
        self.assertEqual(self.read_text(), "second synthetic password")
        self.clear(second)
        self.assertEqual(self.read_text(), "")

    def test_timer_preserves_unrelated_clipboard_content(self):
        receipt = self.copy("synthetic password")
        self.script('board\'s clearContents()\n'
                    'board\'s setString:"ordinary text" forType:"public.utf8-plain-text"\nreturn ""')
        self.clear(receipt)
        self.assertEqual(self.read_text(), "ordinary text")

    def test_wrong_ownership_token_preserves_content(self):
        receipt = self.copy("synthetic password")
        self.clear(receipt.split(":")[0] + ":wrong-token")
        self.assertEqual(self.read_text(), "synthetic password")


@unittest.skipUnless(shutil.which("keepassxc-cli"), "KeePassXC CLI required")
class KeePassXCTests(unittest.TestCase):
    def setUp(self):
        self.s = cli.Sandbox()
        self.addCleanup(self.s.close)
        # Real backend, fake Keychain. Never query the real security command.
        (self.s.fakebin / "keepassxc-cli").unlink()
        self.s.database.unlink()
        self.backend = shutil.which("keepassxc-cli")
        result = subprocess.run([self.backend, "db-create", "-p", "-t", "100", str(self.s.database)],
                                input=self.s.master + "\n" + self.s.master + "\n",
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_database_generated_entry_lookup_and_failure(self):
        self.assertEqual(self.s.run("mkdir", "Work").returncode, 0)
        result = self.s.run("add", "Work/Test entry", "-u", "synthetic-user", "-g", "-L", "32")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.s.run("show", "Work/Test entry", "-q", "-a", "UserName")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "synthetic-user\n")
        self.assertIn("Work/Test entry", self.s.run("search", "Test").stdout)
        result = self.s.run("copy", "Work/Test entry", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.s.wait_cleanup()
        self.assertEqual(len((self.s.path / "clipboard").read_text()), 32)
        original = (self.s.path / "clipboard").read_bytes()
        result = self.s.run("copy", "Missing entry")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.s.path / "clipboard").read_bytes(), original)

    def test_real_add_and_edit_password_prompts(self):
        for command, password in (("add", "fake first \\ value "), ("edit", "fake second value")):
            with self.subTest(command=command):
                code, output = self.s.prompt(command, "Test entry", "-p", answer=(password + "\n").encode())
                self.assertEqual(code, 0, output)
                self.assertNotIn(password, output)
                result = self.s.run("show", "Test entry", "-q", "-a", "Password")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, password + "\n")

    def test_real_multiline_copy(self):
        # Use a synthetic XML export/import to create a password that cannot be
        # entered through KeePassXC's line-oriented interactive prompt.
        import xml.etree.ElementTree as ET
        self.assertEqual(self.s.run("add", "Test", "-g").returncode, 0)
        exported = self.s.run("export", "-q")
        self.assertEqual(exported.returncode, 0, exported.stderr)
        document = ET.fromstring(exported.stdout)
        secret = " multiline päss🔑\nsecond\n\n"
        for field in document.findall("./Root/Group/Entry/String"):
            if field.findtext("Key") == "Password":
                field.find("Value").text = secret
        xml = self.s.path / "synthetic.xml"
        ET.ElementTree(document).write(xml, encoding="utf-8", xml_declaration=True)
        imported = self.s.path / "imported.kdbx"
        result = subprocess.run([self.backend, "import", "-p", "-t", "100", str(xml), str(imported)],
                                input=self.s.master + "\n" + self.s.master + "\n",
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.s.env["KP_DATABASE"] = str(imported)
        result = self.s.run("copy", "Test", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.s.wait_cleanup()
        self.assertEqual((self.s.path / "clipboard").read_text(), secret)


if __name__ == "__main__":
    unittest.main()
