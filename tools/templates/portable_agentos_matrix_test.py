"""Test the published capability profile against only its included providers."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import agentos_import
import agentos_skills


class PortableMatrixTests(unittest.TestCase):
    def test_import_contract_contains_only_shipped_required_files(self):
        result = agentos_import.validate(ROOT)
        manifest = json.loads((ROOT / "runtime/IMPORT-MANIFEST.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(result["state"], "valid")
        self.assertEqual(manifest["agentos_version"], (ROOT / "VERSION").read_text().strip())
        self.assertTrue(manifest.get("distribution_profile"))
        self.assertTrue(all((ROOT / path.replace("\\", "/")).is_file() for path in manifest["required_files"]))

    def test_every_mapped_capability_has_an_included_provider_and_resources(self):
        registry_path = ROOT / "policies/SKILL-REGISTRY.json"
        data, capabilities, providers = agentos_skills.registry(registry_path)
        with tempfile.TemporaryDirectory(prefix="portable-agentos-matrix-") as temp:
            home = Path(temp) / "home"
            home.mkdir()
            mapped = 0
            candidates = 0
            for cap in capabilities.values():
                if cap["availability"] == "candidate":
                    candidates += 1
                    self.assertIsNone(cap["provider"])
                    self.assertEqual(cap["resources"], [])
                    continue
                mapped += 1
                provider = providers[cap["provider"]]
                skill_root, _scope = agentos_skills.resolve_provider(
                    provider, Path(temp), "codex", user_root=home, system_root=ROOT)
                for resource in cap["resources"]:
                    self.assertTrue((skill_root / resource).is_file(), cap["id"] + ": " + resource)
            self.assertGreater(mapped, 0)
            self.assertGreater(candidates, 0)


if __name__ == "__main__":
    unittest.main()
