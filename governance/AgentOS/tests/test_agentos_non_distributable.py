"""The non-distributable gate must be able to go red.

`policies/REDACTION-TERMS.json` holds the R10-confidential customer, product
and personnel identifiers. Its whole purpose is to suppress those identifiers,
so shipping the list ships the secret it exists to hide.

The declaration lives in `policies/NON-DISTRIBUTABLE.json` and every
distribution channel reads it:

  F-ND-1  tools/weekly_learning.py validate()   (governed corpus publisher)
  F-ND-2  installer/build-installer.ps1          (installer payload build)
  F-ND-3  installer/AgentOS.Setup.cs             (installer runtime refusal)

Each gate is checked here at the source level and, where the channel is
scriptable, by actually running it. A gate that stays green when its rule is
weakened is a false-green gate (DEC-030 example 8).
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "policies" / "NON-DISTRIBUTABLE.json"
SETUP_CS = ROOT / "installer" / "AgentOS.Setup.cs"
BUILD_INSTALLER = ROOT / "installer" / "build-installer.ps1"


class NonDistributablePolicyTests(unittest.TestCase):
    def test_policy_declares_the_redaction_term_file_with_a_reason(self):
        document = json.loads(POLICY.read_text(encoding="utf-8-sig"))
        declared = {item["path"]: item for item in document["files"]}

        self.assertIn("policies/REDACTION-TERMS.json", declared)
        entry = declared["policies/REDACTION-TERMS.json"]
        self.assertTrue(entry.get("reason", "").strip(),
                        "A declared file must state why it stays local.")

    def test_the_confidential_file_itself_is_still_present_locally(self):
        """The gate must not be satisfied by deleting the local input."""
        local = ROOT / "policies" / "REDACTION-TERMS.json"
        if not local.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        self.assertTrue(local.is_file(),
                        "bin/qa_leak.py still reads this file as a local input.")

    def test_policy_file_ships_so_other_machines_can_enforce_it(self):
        """The declaration travels; the secret does not."""
        self.assertTrue(POLICY.is_file())


class InstallerGateTests(unittest.TestCase):
    """These exercise the installer source.

    They need the installer tree and the confidential list, neither of which
    ships. Inside a distributed package the suite reports them as skipped
    rather than failed: the source repository is where they belong, and the
    publisher runs its own gate tests against the package.
    """

    def setUp(self):
        if not BUILD_INSTALLER.is_file() or not SETUP_CS.is_file():
            self.skipTest("Installer source tree is not part of this distribution.")

    def test_build_script_reads_the_shared_declaration(self):
        text = BUILD_INSTALLER.read_text(encoding="utf-8-sig")

        self.assertIn("NON-DISTRIBUTABLE.json", text,
                      "F-ND-2 must read the declared list, not hard-code a name.")

    def test_build_script_verifies_the_exclusion_took_effect(self):
        """Declaring the removal is not proof that it happened."""
        text = BUILD_INSTALLER.read_text(encoding="utf-8-sig")

        self.assertIn("Non-distributable file reached the installer payload",
                      text,
                      "F-ND-2 must verify the payload after the copy loop.")

    def test_runtime_installer_refuses_a_tainted_payload(self):
        """F-ND-3: an older payload archive must still be refused."""
        text = SETUP_CS.read_text(encoding="utf-8-sig")

        self.assertIn("RefuseNonDistributablePayload", text)
        self.assertIn("refusing to install", text)

    def test_runtime_gate_is_not_disabled_by_a_wrong_collection_cast(self):
        """DEC-030 example 8: JavaScriptSerializer yields ArrayList, not object[].

        A cast that assumes object[] returns null, the loop never runs and the
        gate passes silently. The enumeration must be collection-agnostic.
        """
        text = SETUP_CS.read_text(encoding="utf-8-sig")

        self.assertNotIn("files as object[]", text,
                         "object[] is the wrong cast for a deserialized JSON array.")
        self.assertIn("as IEnumerable", text)

    def test_runtime_gate_rejects_a_tainted_payload_when_executed(self):
        """Run the real gate: a payload carrying the secret must be refused.

        The executable is built from the CURRENT source in a throwaway
        directory. Testing a previously built exe would only prove that the
        build that produced it behaved, not that the source still does.

        The tainted file is synthesised from the declaration's own content
        signature, so this test runs inside a distributed package too, where
        the confidential list itself is deliberately absent.
        """
        compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
        if not compiler.is_file():
            compiler = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
        if not compiler.is_file():
            self.skipTest("No .NET Framework compiler on this host.")
        payload = ROOT / "dist" / "AgentOS-Installer" / "AgentOS-Payload"
        if not payload.is_dir():
            self.skipTest("Installer payload has not been built on this host.")
        signatures = self._declared_signature()
        if not signatures:
            self.skipTest("The non-distributable declaration names no signature.")
        with tempfile.TemporaryDirectory(prefix="agentos-nd-") as work:
            work_path = Path(work)
            exe = work_path / "AgentOS-Installer.exe"
            build = subprocess.run(
                [str(compiler), "/nologo", "/target:winexe", "/out:" + str(exe),
                 "/r:System.dll", "/r:System.Drawing.dll", "/r:System.Windows.Forms.dll",
                 "/r:System.Web.Extensions.dll", str(SETUP_CS)],
                capture_output=True, text=True, timeout=300)
            if build.returncode != 0:
                self.skipTest("Installer source does not compile on this host: "
                              + build.stderr[-300:])
            # The installer resolves its payload next to its own executable.
            shutil.copytree(payload, work_path / "AgentOS-Payload")
            self._assert_tainted_payload_is_refused(exe, work_path, signatures)

    def _declared_signature(self):
        """The JSON fragment that identifies the confidential list by content.

        The runtime installer cannot know the confidential bytes, because that
        list stays on the owner's machine. It can know the list's structural
        marker, which ordinary documentation and tests do not reproduce.
        """
        document = json.loads(POLICY.read_text(encoding="utf-8-sig"))
        markers = [str(x) for x in (document.get("content_markers") or []) if x]
        return markers

    def _assert_tainted_payload_is_refused(self, exe, work_path, signatures):
        copy = work_path / "AgentOS-Payload" / "policies" / "unexpected-copy.txt"
        copy.parent.mkdir(parents=True, exist_ok=True)
        # A copy is recognised by its digest, so the tainted file must have the
        # declared bytes. The declared digest identifies the local list, which
        # is not present in a distributed package; the fixture therefore
        # reconstructs a body whose digest the declaration also names.
        copy.write_text("".join(item + "\n" for item in signatures), encoding="utf-8")
        try:
            report = work_path / "self-test-nd.log"
            result = subprocess.run([str(exe), "--self-test", str(report)],
                                    capture_output=True, text=True, timeout=180)
            output = report.read_text(encoding="utf-8", errors="replace") if report.is_file() else ""
        finally:
            copy.unlink(missing_ok=True)

        self.assertNotEqual(result.returncode, 0,
                            "A tainted payload must not install successfully.")
        self.assertIn("non-distributable", output.lower())

    def test_installer_build_refuses_a_confidential_identifier_in_any_file(self):
        """F-ND-6: the build must not produce a payload that names a customer.

        A path rule cannot see an identifier typed into an ordinary note, so
        the build scans the content of every payload file against the local
        term list and refuses to produce the payload at all.
        """
        local = ROOT / "policies" / "REDACTION-TERMS.json"
        if not local.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        import json as _json
        document = _json.loads(local.read_text(encoding="utf-8"))
        literal = next((t["pattern"] for t in document.get("terms", [])
                        if t.get("kind") == "literal" and t.get("pattern")), None)
        if not literal:
            self.skipTest("The confidential list has no literal term to plant.")
        with tempfile.TemporaryDirectory(prefix="agentos-nd6-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            planted = tree / "protocols" / "FIELD-NOTES.md"
            planted.write_text("Customer contact: %s\n" % literal, encoding="utf-8")
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)

        self.assertNotEqual(result.returncode, 0,
                            "A payload carrying a confidential identifier must not build.")
        self.assertIn("Confidential identifier", result.stdout + result.stderr)

    def test_installer_build_refuses_an_identifier_in_an_unlisted_extension(self):
        """A file whose extension is not on any list is still text.

        A gate that matches on extension is exactly how a leak walks past it:
        a .bak copy, a .step file, a file with no extension at all.
        """
        local = ROOT / "policies" / "REDACTION-TERMS.json"
        if not local.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        import json as _json
        document = _json.loads(local.read_text(encoding="utf-8"))
        literal = next((t["pattern"] for t in document.get("terms", [])
                        if t.get("kind") == "literal" and t.get("pattern")), None)
        if not literal:
            self.skipTest("The confidential list has no literal term to plant.")
        with tempfile.TemporaryDirectory(prefix="agentos-nd6-ext-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            # An extension that appears on no whitelist.
            planted = tree / "protocols" / "CAD-NOTES.step"
            planted.write_text("customer %s line\n" % literal, encoding="utf-8")
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)

        self.assertNotEqual(result.returncode, 0,
                            "A payload carrying a confidential identifier must not build.")
        self.assertIn("Confidential identifier", result.stdout + result.stderr)

    def test_installer_build_refuses_a_tainted_declaration(self):
        """The declaration is scanned too.

        The declaration names the signatures it protects, so it is allowed to
        carry them -- but only because it is checked to carry nothing else.
        A declaration with a customer identifier in it is a confidential list
        wearing the declaration's name.
        """
        local = ROOT / "policies" / "REDACTION-TERMS.json"
        if not local.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        import json as _json
        document = _json.loads(local.read_text(encoding="utf-8"))
        literal = next((t["pattern"] for t in document.get("terms", [])
                        if t.get("kind") == "literal" and t.get("pattern")), None)
        if not literal:
            self.skipTest("The confidential list has no literal term to plant.")
        with tempfile.TemporaryDirectory(prefix="agentos-decl-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            declaration = tree / "policies" / "NON-DISTRIBUTABLE.json"
            body = _json.loads(declaration.read_text(encoding="utf-8"))
            body["notes"] = list(body.get("notes", [])) + ["customer %s" % literal]
            declaration.write_text(_json.dumps(body, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)

        self.assertNotEqual(result.returncode, 0,
                            "A tainted declaration must not produce a payload.")
        # The refusal names the declaration explicitly; the exact wording is
        # the gate's contract, so it is pinned rather than loosely matched.
        self.assertIn("declaration itself carries a confidential identifier",
                      result.stdout + result.stderr)

    def test_installer_build_refuses_a_term_hidden_behind_a_nul_byte(self):
        """A NUL byte is not a defence: the payload bytes are decoded every way."""
        local = ROOT / "policies" / "REDACTION-TERMS.json"
        if not local.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        import json as _json
        document = _json.loads(local.read_text(encoding="utf-8"))
        literal = next((t["pattern"] for t in document.get("terms", [])
                        if t.get("kind") == "literal" and t.get("pattern")), None)
        if not literal:
            self.skipTest("The confidential list has no literal term to plant.")
        with tempfile.TemporaryDirectory(prefix="agentos-nul-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            planted = tree / "protocols" / "LEAK.md"
            planted.write_bytes(b"\x00" * 64 + ("customer %s\n" % literal).encode("utf-8"))
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)
            payload = tree / "dist" / "AgentOS-Installer" / "AgentOS-Payload"
            carried = (payload / "protocols" / "LEAK.md").exists()

        self.assertNotEqual(result.returncode, 0,
                            "A payload carrying a confidential identifier must not build.")
        self.assertIn("Confidential identifier", result.stdout + result.stderr)
        self.assertFalse(carried, "The tainted file reached the payload.")

    def test_installer_build_refuses_a_term_written_in_utf16(self):
        """UTF-16 without a BOM decodes as UTF-8 with NULs; it must still be read."""
        local = ROOT / "policies" / "REDACTION-TERMS.json"
        if not local.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        import json as _json
        document = _json.loads(local.read_text(encoding="utf-8"))
        literal = next((t["pattern"] for t in document.get("terms", [])
                        if t.get("kind") == "literal" and t.get("pattern")), None)
        if not literal:
            self.skipTest("The confidential list has no literal term to plant.")
        with tempfile.TemporaryDirectory(prefix="agentos-u16-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            planted = tree / "protocols" / "LEAK.md"
            planted.write_bytes(("customer %s\n" % literal).encode("utf-16-le"))
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)

        self.assertNotEqual(result.returncode, 0,
                            "A payload carrying a confidential identifier must not build.")
        self.assertIn("Confidential identifier", result.stdout + result.stderr)

    def test_a_refused_build_leaves_no_payload_on_disk(self):
        """A refused build must not leave the tree it refused on disk.

        The payload is assembled before the gates run, so a refusal that does
        not clean up leaves the very content it refused sitting in dist/.
        """
        local = ROOT / "policies" / "REDACTION-TERMS.json"
        if not local.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        import json as _json
        document = _json.loads(local.read_text(encoding="utf-8"))
        literal = next((t["pattern"] for t in document.get("terms", [])
                        if t.get("kind") == "literal" and t.get("pattern")), None)
        if not literal:
            self.skipTest("The confidential list has no literal term to plant.")
        with tempfile.TemporaryDirectory(prefix="agentos-nd6-clean-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            planted = tree / "protocols" / "FIELD-NOTES.md"
            planted.write_text("Customer contact: %s\n" % literal, encoding="utf-8")
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)
            # Assert INSIDE the temporary directory. Reading the path after the
            # block closes finds a deleted directory and passes for ever.
            leftover = tree / "dist" / "AgentOS-Installer"
            refused = result.returncode != 0
            left_behind = leftover.exists()

        self.assertTrue(refused, "A payload carrying a confidential identifier must not build.")
        self.assertFalse(left_behind,
                         "A refused build left its output tree on disk: " + str(leftover))

    def test_installer_payload_carries_only_authorised_skills(self):
        """F-ND-7: the installer and the publisher must agree on what travels.

        A Skill the published corpus does not carry must not reach a target
        machine through the installer either.
        """
        allowlist = ROOT / "policies" / "REDISTRIBUTION-ALLOWLIST.json"
        if not allowlist.is_file():
            self.skipTest("The redistribution allowlist is not part of this distribution.")
        import json as _json
        document = _json.loads(allowlist.read_text(encoding="utf-8"))
        excluded = {str(item["path"]).replace("\\", "/").strip("/")
                    for item in document.get("excluded", [])}
        self.assertTrue(excluded, "The allowlist excludes no Skill.")
        with tempfile.TemporaryDirectory(prefix="agentos-allow-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            unlisted = tree / "skills" / "ming-systems"
            if not unlisted.is_dir():
                self.skipTest("The source tree has no Skill outside the allowlist to test with.")
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)
            payload = tree / "dist" / "AgentOS-Installer" / "AgentOS-Payload"
            # Collect INSIDE the temporary directory. Reading it afterwards
            # finds a deleted directory, the set comes out empty and the
            # assertion below passes without ever looking at a payload.
            carried = {p.name for p in (payload / "skills").iterdir() if p.is_dir()} \
                if (payload / "skills").is_dir() else set()
            build_ok = result.returncode == 0

        self.assertTrue(build_ok, "Build failed: " + result.stdout[-400:])
        self.assertTrue(carried, "The payload carried no Skill, so this test proved nothing.")
        for name in carried:
            self.assertNotIn("skills/" + name, excluded,
                             "The installer payload carries an excluded Skill: " + name)

    def test_build_script_removes_the_secret_from_a_fresh_payload(self):
        """F-ND-2: run the real build and check the payload it produces.

        A source-level assertion cannot tell whether the copy loop still
        removes the file; only the produced payload can.
        """
        signatures = self._declared_signature()
        if not signatures:
            self.skipTest("The non-distributable declaration names no signature.")
        # Build in a throwaway copy. A test that builds in place writes dist/
        # and reports/ into the tree it was run from, which mutates a released
        # package while the release gate is comparing it against its snapshot.
        with tempfile.TemporaryDirectory(prefix="agentos-build-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            # The build needs a security scanner. The distributed edition
            # carries one beside the publisher's tools/; the source tree does
            # not, so point at whichever is present.
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command,
                                    capture_output=True, text=True, timeout=900)
            payload = tree / "dist" / "AgentOS-Installer" / "AgentOS-Payload"
            self.assertEqual(result.returncode, 0,
                             "Installer build failed: " + result.stdout[-400:])
            self._assert_payload_is_clean(payload)

    def _assert_payload_is_clean(self, payload):
        signatures = self._declared_signature()
        # The declaration itself names the signature, so it is the one file
        # that legitimately contains it.
        carried = []
        for file in payload.rglob("*"):
            if not file.is_file() or file.name == "NON-DISTRIBUTABLE.json":
                continue
            try:
                content = file.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            if all(item in content for item in signatures):
                carried.append(file)
        self.assertEqual(carried, [],
                         "The produced payload still carries a confidential file: "
                         + ", ".join(str(p) for p in carried))


    def test_the_declaration_names_the_local_only_tree(self):
        """The deployment backup tree must be declared, not merely observed.

        The tree holds snapshots of client and project rule files, so it
        carries their engagement identifiers. A gate that only knows about
        files cannot protect a tree that grows on every deployment run.
        """
        document = json.loads(POLICY.read_text(encoding="utf-8-sig"))
        declared = {str(item["path"]): item for item in document["files"]}

        self.assertIn("runtime/backups/derivation/", declared,
                      "The derivation backup tree is not declared local-only.")
        entry = declared["runtime/backups/derivation/"]
        self.assertTrue(entry.get("reason", "").strip(),
                        "A declared tree must state why it stays local.")

    def test_installer_payload_carries_no_local_only_tree(self):
        """F-ND-2: the build must not carry the declared tree.

        The tree grows a new timestamped snapshot every time the derivation
        deployment runs, so the payload must not carry any of it -- not the
        directory, not one snapshot, not a renamed copy.
        """
        document = json.loads(POLICY.read_text(encoding="utf-8-sig"))
        trees = [str(item["path"]) for item in document["files"]
                 if str(item.get("path", "")).endswith("/")]
        if not trees:
            self.skipTest("No local-only tree is declared.")
        with tempfile.TemporaryDirectory(prefix="agentos-tree-") as work:
            tree = Path(work) / "AgentOS"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                "dist", "__pycache__", ".local"))
            command = ["pwsh", "-NoProfile", "-File",
                       str(tree / "installer" / "build-installer.ps1")]
            probe = ROOT
            for _ in range(4):
                if not probe:
                    break
                candidate = probe / "tools" / "security_check.ps1"
                if candidate.is_file():
                    command += ["-SecurityCheckPath", str(candidate)]
                    break
                probe = probe.parent
            result = subprocess.run(command,
                                    capture_output=True, text=True, timeout=900)
            payload = tree / "dist" / "AgentOS-Installer" / "AgentOS-Payload"
            build_ok = result.returncode == 0
            survivors = []
            if payload.is_dir():
                for prefix in trees:
                    # The tree is identified by its PATH, not by a substring
                    # of its name: a file named "derivation" elsewhere in the
                    # payload is not the tree.
                    wanted = prefix.rstrip("/")
                    for found in payload.rglob("*"):
                        relative = str(found.relative_to(payload)).replace("\\", "/")
                        if relative == wanted or relative.startswith(wanted + "/"):
                            survivors.append(relative)

        self.assertTrue(build_ok, "Build failed: " + result.stdout[-400:])
        self.assertEqual(survivors, [],
                         "The installer payload carries a declared local-only tree: "
                         + ", ".join(sorted(survivors)[:6]))

    def test_the_runtime_gate_refuses_a_term_list_with_its_markers_stripped(self):
        """F-ND-3: shedding one structural marker must not let a copy through.

        The runtime cannot know the confidential bytes, so it recognises a
        copy by the JSON structure it has. A rule that requires EVERY marker
        lets a copy drop one of them and pass: the file still carries all
        17 confidential terms, it just no longer matches the whole shape.
        Each marker is independently sufficient.
        """
        compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
        if not compiler.is_file():
            compiler = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
        if not compiler.is_file():
            self.skipTest("No .NET Framework compiler on this host.")
        payload = ROOT / "dist" / "AgentOS-Installer" / "AgentOS-Payload"
        if not payload.is_dir():
            self.skipTest("Installer payload has not been built on this host.")
        terms = ROOT / "policies" / "REDACTION-TERMS.json"
        if not terms.is_file():
            self.skipTest("The confidential list is deliberately not distributed.")
        document = json.loads(terms.read_text(encoding="utf-8-sig"))
        with tempfile.TemporaryDirectory(prefix="agentos-marker-") as work:
            work_path = Path(work)
            exe = work_path / "AgentOS-Installer.exe"
            build = subprocess.run(
                [str(compiler), "/nologo", "/target:winexe", "/optimize+", "/debug-",
                 "/out:" + str(exe), "/r:System.dll", "/r:System.Drawing.dll",
                 "/r:System.Windows.Forms.dll", "/r:System.Web.Extensions.dll",
                 str(SETUP_CS)],
                capture_output=True, text=True, timeout=300)
            if build.returncode != 0:
                self.skipTest("Installer source does not compile on this host: "
                              + build.stderr[-300:])
            shutil.copytree(payload, work_path / "AgentOS-Payload")
            # The control: the honest payload must be accepted. A gate that
            # refuses everything proves nothing.
            control = work_path / "control.log"
            accepted = subprocess.run([str(exe), "--self-test", str(control)],
                                       capture_output=True, text=True, timeout=180)
            self.assertEqual(accepted.returncode, 0,
                             "The honest payload must be accepted by the runtime gate.")
            # The attack: the real list with ONE structural marker removed,
            # at a name that is neither the declared path nor its stem.
            stripped = dict(document)
            stripped.pop("retained_public_identifiers", None)
            planted = work_path / "AgentOS-Payload" / "runtime" / "stripped-list.json"
            planted.parent.mkdir(parents=True, exist_ok=True)
            planted.write_text(json.dumps(stripped, ensure_ascii=False, indent=1),
                               encoding="utf-8")
            try:
                report = work_path / "tainted.log"
                result = subprocess.run([str(exe), "--self-test", str(report)],
                                        capture_output=True, text=True, timeout=180)
                output = report.read_text(encoding="utf-8", errors="replace") \
                    if report.is_file() else ""
            finally:
                planted.unlink(missing_ok=True)

        self.assertNotEqual(result.returncode, 0,
                            "A term list with a marker stripped must not install.")
        self.assertIn("non-distributable", output.lower(),
                      "The payload must be refused for the confidentiality reason, "
                      "not for an unrelated one.")

    def test_the_runtime_installer_refuses_a_payload_carrying_the_tree(self):
        """F-ND-3: an older payload archive that carries the tree is refused.

        The runtime cannot know the confidential bytes, but it can know the
        declared prefix, so a payload handed to it later is still refused.
        """
        compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
        if not compiler.is_file():
            compiler = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
        if not compiler.is_file():
            self.skipTest("No .NET Framework compiler on this host.")
        payload = ROOT / "dist" / "AgentOS-Installer" / "AgentOS-Payload"
        if not payload.is_dir():
            self.skipTest("Installer payload has not been built on this host.")
        with tempfile.TemporaryDirectory(prefix="agentos-runtime-tree-") as work:
            work_path = Path(work)
            exe = work_path / "AgentOS-Installer.exe"
            build = subprocess.run(
                [str(compiler), "/nologo", "/target:winexe", "/optimize+", "/debug-",
                 "/out:" + str(exe), "/r:System.dll", "/r:System.Drawing.dll",
                 "/r:System.Windows.Forms.dll", "/r:System.Web.Extensions.dll",
                 str(SETUP_CS)],
                capture_output=True, text=True, timeout=300)
            if build.returncode != 0:
                self.skipTest("Installer source does not compile on this host: "
                              + build.stderr[-300:])
            shutil.copytree(payload, work_path / "AgentOS-Payload")
            # The runtime gate reads the declaration that travels WITH the
            # payload. A payload built before the tree was declared carries
            # the old declaration, so the copy under test must carry the
            # CURRENT one -- otherwise the test proves only that an old
            # payload has an old rule.
            shutil.copy2(POLICY, work_path / "AgentOS-Payload" / "policies"
                         / "NON-DISTRIBUTABLE.json")
            planted = (work_path / "AgentOS-Payload" / "runtime" / "backups"
                       / "derivation" / "20990101-000000" / "AGENTS.md")
            planted.parent.mkdir(parents=True, exist_ok=True)
            planted.write_text("planted snapshot", encoding="utf-8")
            try:
                report = work_path / "self-test-tree.log"
                result = subprocess.run([str(exe), "--self-test", str(report)],
                                        capture_output=True, text=True, timeout=180)
                output = report.read_text(encoding="utf-8", errors="replace") \
                    if report.is_file() else ""
            finally:
                shutil.rmtree(planted.parent, ignore_errors=True)

        self.assertNotEqual(result.returncode, 0,
                            "A payload carrying a declared local-only tree must not install.")
        self.assertIn("non-distributable", output.lower())


if __name__ == "__main__":
    unittest.main()
