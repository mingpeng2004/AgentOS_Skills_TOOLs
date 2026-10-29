"""Extract only PS functions and exercise isolated fixture roots, never production install."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
PS = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(PS, "PowerShell unavailable")
class PSClientIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agentos-ps-client-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ["bin", "runtime", ".local", "reports"]:
            (self.root / name).mkdir()
        self.template = b"# Test managed entry\nRoot: {agentos_root}\n"
        (self.root / "runtime/managed-client-entry.md").write_bytes(self.template)
        self.rule = self.root / "client/AGENTS.md"
        self.rule.parent.mkdir()
        self.block = ("<!-- AGENTOS:BEGIN client-entry-v1 -->\n" +
                      self.template.decode().replace("{agentos_root}", str(self.root.resolve())).rstrip() +
                      "\n<!-- AGENTOS:END client-entry-v1 -->\n").encode()
        self.rule.write_bytes(b"User text untouched\n\n" + self.block)
        self.client = {"id": "rule-only", "source": None, "skill_roots": [],
                       "rule_files": [str(self.rule)], "discovered": True}
        self.write_bindings()
        (self.root / "bin/agentos_paths.py").write_text(
            "import json\nprint(json.dumps(" + repr({"clients": [self.client, {"id": "fallback",
            "source": None, "skill_roots": [], "rule_files": [], "discovered": False}]}) + "))\n")
        (self.root / "bin/agentos_client_deploy.py").write_text(
            "import json,sys,pathlib,hashlib\n"
            "pathlib.Path(__file__).with_suffix('.called').write_text(json.dumps(sys.argv))\n"
            "args=sys.argv; out=pathlib.Path(args[args.index('--output')+1])\n"
            "bindings=json.loads(pathlib.Path(args[args.index('--bindings')+1]).read_text())\n"
            "selected=args[args.index('--client')+1] if '--client' in args else None\n"
            "records=[(k,v) for k,v in bindings['clients'].items() if selected is None or k==selected]\n"
            "clients=[]\n"
            "for client,record in records:\n"
            " files=[]\n"
            " for item in record['adapter_files']:\n"
            "  p=pathlib.Path(item['path']); h=hashlib.sha256(p.read_bytes()).hexdigest(); state='unchanged' if h==item['sha256'] else 'drift'\n"
            "  files.append({'path':str(p),'before_sha256':h,'sha256':h,'source_sha256':item['source_sha256'],'managed_block_sha256':item['managed_block_sha256'],'state':state})\n"
            " clients.append({'id':client,'adapter_files':files})\n"
            "result={'clients':clients}\n"
            "out.write_text(json.dumps(result))\nprint(json.dumps(result))\n")

    def write_bindings(self):
        d = {"schema": "agentos-host-bindings-v1", "runtime": {"python": {"path": sys.executable}},
             "clients": {"rule-only": {"rule_files": [str(self.rule)], "adapter_files": [{
                 "path": str(self.rule), "sha256": hashlib.sha256(self.rule.read_bytes()).hexdigest(),
                 "source_sha256": hashlib.sha256(self.template).hexdigest(),
                 "managed_block_sha256": hashlib.sha256(self.block).hexdigest()}]},
                 "fallback": {"rule_files": [], "adapter_files": []}}}
        (self.root / ".local/host-bindings.json").write_text(json.dumps(d))

    def run_function(self, command):
        def quote(x):
            return "'" + str(x).replace("'", "''") + "'"
        code = ("$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest;"
                "$tokens=$null;$errors=$null;$ast=[System.Management.Automation.Language.Parser]::ParseFile(" +
                quote(ROOT / "bin/AgentOS.ps1") + ",[ref]$tokens,[ref]$errors);"
                "$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) |"
                " ForEach-Object {Invoke-Expression $_.Extent.Text};"
                "$script:AgentOsRoot=" + quote(self.root) + ";" + command)
        return subprocess.run([PS, "-NoProfile", "-Command", code], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=45)

    def test_rule_only_client_and_unknown_fallback_are_reported_separately(self):
        p = self.run_function("Invoke-AgentOsDiagnose")
        # Core presence is mocked independently from the client hash contract.
        report = json.loads(next((self.root / "reports").glob("diagnose-*.json")).read_text())
        self.assertEqual(len(report["clients"]), 2)
        self.assertEqual(report["clients"][0]["file_parity"], "verified")
        self.assertEqual(report["clients"][1]["file_parity"], "unknown")
        self.assertFalse(report["complete"])
        self.assertEqual(report["python"]["source"], "host-binding")

    def test_client_drift_fails_even_with_managed_marker(self):
        self.rule.write_bytes(self.rule.read_bytes() + b"concurrent user edit\n")
        p = self.run_function("Invoke-AgentOsDiagnose")
        report = json.loads(next((self.root / "reports").glob("diagnose-*.json")).read_text())
        self.assertEqual(report["clients"][0]["file_parity"], "drift")
        self.assertNotEqual(p.returncode, 0)

    def test_missing_registered_native_binding_fails_diagnose(self):
        bindings_path = self.root / ".local/host-bindings.json"
        data = json.loads(bindings_path.read_text())
        del data["clients"]["rule-only"]
        bindings_path.write_text(json.dumps(data))
        p = self.run_function("Invoke-AgentOsDiagnose")
        report = json.loads(next((self.root / "reports").glob("diagnose-*.json")).read_text())
        self.assertEqual(report["clients"][0]["file_parity"], "missing")
        self.assertFalse(report["native_client_pass"])
        self.assertNotEqual(p.returncode, 0)

    def test_tool_catalog_health_is_a_named_diagnosis_gate(self):
        (self.root / "bin/agentos_tools.py").write_text(
            "import json,sys\n"
            "print(json.dumps({'state':'validated_inventory','asset_count':25,'capability_count':67}))\n")
        p = self.run_function("Invoke-AgentOsDiagnose")
        report = json.loads(next((self.root / "reports").glob("diagnose-*.json")).read_text())
        check = next(x for x in report["checks"] if x["name"] == "tool-catalog")
        self.assertTrue(check["pass"], check["detail"])
        self.assertIn("25 assets", check["detail"])

    def test_install_delegates_to_registered_cas_tool(self):
        before = self.rule.read_bytes()
        p = self.run_function("Install-ClientAdapters")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / "bin/agentos_client_deploy.called").is_file())
        args = json.loads((self.root / "bin/agentos_client_deploy.called").read_text())
        self.assertIn("--backup-root", args)
        self.assertEqual(before, self.rule.read_bytes())

    def test_no_host_bindings_does_not_install_or_create_client_home(self):
        (self.root / ".local/host-bindings.json").unlink()
        p = self.run_function("Install-ClientAdapters")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((self.root / "bin/agentos_client_deploy.called").exists())


if __name__ == "__main__":
    unittest.main()
