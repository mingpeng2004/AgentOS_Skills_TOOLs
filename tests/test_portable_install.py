"""Synthetic isolation tests; no client activation, network or system changes."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "portable_install", Path(__file__).resolve().parent.parent / "tools/portable_install.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PortableInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentos-portable-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "bundle"
        self.source.mkdir()
        self.target = self.root / "installed"
        self.write("governance/AgentOS/VERSION", b"1.0\n")
        self.write("tools/example.py", b"print('synthetic fixture')\n")
        self.seal()

    def write(self, name, data):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def seal(self, exclusions=()):
        manifest = m.build_manifest(self.source, exclusions)
        (self.source / m.MANIFEST_NAME).write_bytes(m._encoded(manifest))
        return manifest

    def test_normal_install_idempotence_and_first_rollback(self):
        result = m.install(self.source, self.target)
        self.assertEqual(result["state"], "installed")
        self.assertEqual((self.target / "governance/AgentOS/VERSION").read_bytes(), b"1.0\n")
        self.assertFalse((self.target / m.MANIFEST_NAME).exists())
        receipt_bytes = (self.target / m.STATE_DIR / "receipt.json").read_bytes()
        self.assertEqual(m.install(self.source, self.target)["state"], "unchanged")
        self.assertEqual(receipt_bytes, (self.target / m.STATE_DIR / "receipt.json").read_bytes())
        self.assertEqual(m.rollback(self.target)["state"], "rolled_back")
        self.assertFalse(self.target.exists())

    def test_dry_run_has_no_writes(self):
        self.assertEqual(m.install(self.source, self.target, True)["state"], "planned")
        self.assertFalse(self.target.exists())
        m.install(self.source, self.target)
        before = (self.target / m.STATE_DIR / "receipt.json").read_bytes()
        self.assertEqual(m.rollback(self.target, True)["state"], "planned")
        self.assertEqual(before, (self.target / m.STATE_DIR / "receipt.json").read_bytes())

    def test_update_backup_and_chained_rollback(self):
        m.install(self.source, self.target)
        self.write("governance/AgentOS/VERSION", b"2.0\n")
        (self.source / "tools/example.py").unlink()
        self.write("new-file.txt", b"new\n")
        self.seal()
        self.assertEqual(m.install(self.source, self.target)["action"], "update")
        self.assertFalse((self.target / "tools/example.py").exists())
        m.rollback(self.target)
        self.assertEqual((self.target / "governance/AgentOS/VERSION").read_bytes(), b"1.0\n")
        self.assertTrue((self.target / "tools/example.py").is_file())
        self.assertFalse((self.target / "new-file.txt").exists())
        m.rollback(self.target)
        self.assertFalse(self.target.exists())

    def test_manifest_changed_missing_and_added_files(self):
        for mutation in ("changed", "missing", "added"):
            with self.subTest(mutation=mutation):
                path = self.source / "tools/example.py"
                original = path.read_bytes()
                if mutation == "changed":
                    path.write_bytes(b"changed")
                elif mutation == "missing":
                    path.unlink()
                else:
                    self.write("extra.txt", b"unexpected")
                with self.assertRaises(m.Blocked):
                    m.install(self.source, self.target)
                self.assertFalse(self.target.exists())
                path.write_bytes(original)
                (self.source / "extra.txt").unlink(missing_ok=True)

    def test_empty_bundle_and_nonexistent_exclusion(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(m.Blocked):
            m.build_manifest(empty)
        with self.assertRaises(m.Blocked):
            m.build_manifest(self.source, ["missing.txt"])

    def test_exact_excluded_file_is_not_installed(self):
        self.write("evidence/local-note.txt", b"explicitly not installed")
        self.seal(["evidence/local-note.txt"])
        m.install(self.source, self.target)
        self.assertFalse((self.target / "evidence/local-note.txt").exists())

    def test_unowned_target_and_overlap_refused(self):
        self.target.mkdir()
        with self.assertRaises(m.Blocked):
            m.install(self.source, self.target)
        for target in (self.source, self.source / "inside", self.source.parent):
            with self.subTest(target=target), self.assertRaises(m.Blocked):
                m.install(self.source, target)

    def test_relative_paths_and_missing_parent_refused(self):
        with self.assertRaises(m.Blocked):
            m.install(self.source, Path("relative-target"))
        with self.assertRaises(m.Blocked):
            m.install(self.source, self.root / "missing" / "target")

    def test_unsafe_manifest_paths_and_case_collisions(self):
        record = {"sha256": "0" * 64, "bytes": 0}
        for name in ("../outside", "/absolute", "C:/escape", "a\\b", "NUL.txt", "a. ", "a?b", ".agentos-install/file", ".AGENTOS-INSTALL/file", "nested/.AgentOS-Install/file"):
            with self.subTest(name=name), self.assertRaises(m.Blocked):
                m._validate_records({name: record})
        for names in (("a", "A"), ("A/first", "a/second"), ("a", "a/second")):
            with self.subTest(names=names), self.assertRaises(m.Blocked):
                m._validate_records({name: record for name in names})

    def test_target_user_changes_block_install_and_rollback_without_writes(self):
        m.install(self.source, self.target)
        version = self.target / "governance/AgentOS/VERSION"
        version.write_bytes(b"user changed")
        receipt = (self.target / m.STATE_DIR / "receipt.json").read_bytes()
        for operation in (lambda: m.install(self.source, self.target), lambda: m.rollback(self.target)):
            with self.assertRaises(m.Blocked):
                operation()
            self.assertEqual(version.read_bytes(), b"user changed")
            self.assertEqual(receipt, (self.target / m.STATE_DIR / "receipt.json").read_bytes())

    def test_target_added_or_missing_file_blocks_rollback(self):
        m.install(self.source, self.target)
        extra = self.target / "user.txt"
        extra.write_bytes(b"preserve")
        with self.assertRaises(m.Blocked):
            m.rollback(self.target)
        extra.unlink()
        (self.target / "tools/example.py").unlink()
        with self.assertRaises(m.Blocked):
            m.rollback(self.target)

    def test_corrupt_backup_blocks_before_any_restore(self):
        m.install(self.source, self.target)
        self.write("governance/AgentOS/VERSION", b"2.0\n")
        self.seal()
        m.install(self.source, self.target)
        receipt = m._receipt(self.target)
        backup = self.target / m.STATE_DIR / "history" / receipt["transaction"] / "backup"
        (backup / "governance/AgentOS/VERSION").write_bytes(b"corrupt backup")
        before = m._payload(self.target)
        with self.assertRaises(m.Blocked):
            m.rollback(self.target)
        self.assertEqual(before, m._payload(self.target))

    def test_new_install_failure_restores_absent_target(self):
        original = m._write_bytes
        failed = False
        def fail_once(path, data, **kwargs):
            nonlocal failed
            if Path(path) == self.target / "tools/example.py" and not failed:
                failed = True
                raise OSError("synthetic injected write failure")
            return original(path, data, **kwargs)
        with mock.patch.object(m, "_write_bytes", side_effect=fail_once):
            with self.assertRaisesRegex(m.Blocked, "original state restored"):
                m.install(self.source, self.target)
        self.assertTrue(failed)
        self.assertFalse(self.target.exists())

    def test_update_failure_restores_prior_files_and_receipt(self):
        m.install(self.source, self.target)
        before = m._payload(self.target)
        receipt = (self.target / m.STATE_DIR / "receipt.json").read_bytes()
        self.write("governance/AgentOS/VERSION", b"2.0\n")
        self.write("zzz-new.txt", b"fail after version changed")
        self.seal()
        original = m._write_bytes
        failed = False
        def fail_once(path, data, **kwargs):
            nonlocal failed
            if Path(path) == self.target / "zzz-new.txt" and not failed:
                failed = True
                raise OSError("synthetic injected update failure")
            return original(path, data, **kwargs)
        with mock.patch.object(m, "_write_bytes", side_effect=fail_once):
            with self.assertRaisesRegex(m.Blocked, "original state restored"):
                m.install(self.source, self.target)
        self.assertTrue(failed)
        self.assertEqual(before, m._payload(self.target))
        self.assertEqual(receipt, (self.target / m.STATE_DIR / "receipt.json").read_bytes())

    def test_foreign_lock_is_preserved(self):
        m.install(self.source, self.target)
        lock = self.target / m.STATE_DIR / "operation.lock"
        lock.write_bytes(b"another operation")
        with self.assertRaises(m.Blocked):
            m.rollback(self.target)
        self.assertEqual(lock.read_bytes(), b"another operation")

    def test_added_metadata_and_changed_descriptor_block_rollback(self):
        m.install(self.source, self.target)
        extra = self.target / m.STATE_DIR / "user-note.txt"
        extra.write_bytes(b"user metadata")
        with self.assertRaises(m.Blocked):
            m.rollback(self.target)
        self.assertEqual(extra.read_bytes(), b"user metadata")
        extra.unlink()
        receipt = m._receipt(self.target)
        descriptor = self.target / m.STATE_DIR / "history" / receipt["transaction"] / "before.json"
        descriptor.write_bytes(b"{}")
        with self.assertRaises(m.Blocked):
            m.rollback(self.target)
        self.assertEqual((self.target / "governance/AgentOS/VERSION").read_bytes(), b"1.0\n")

    def test_shape_change_fails_before_any_write(self):
        self.write("shape", b"old regular file")
        self.seal()
        m.install(self.source, self.target)
        before = m._payload(self.target)
        (self.source / "shape").unlink()
        self.write("shape/nested.txt", b"new directory")
        self.seal()
        with mock.patch.object(m, "_write_bytes", side_effect=AssertionError("No writes allowed")):
            with self.assertRaises(m.Blocked):
                m.install(self.source, self.target)
        self.assertEqual(before, m._payload(self.target))

    def test_duplicate_json_keys_are_rejected(self):
        path = self.source / m.MANIFEST_NAME
        path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
        with self.assertRaises(m.Blocked):
            m.validate_bundle(self.source)

    def test_concurrent_user_edit_preserves_failed_install_for_recovery(self):
        original = m._write_bytes
        def change_then_fail(path, data, **kwargs):
            if Path(path) == self.target / "tools/example.py":
                (self.target / "governance/AgentOS/VERSION").write_bytes(b"concurrent user edit")
                raise OSError("synthetic concurrent change")
            return original(path, data, **kwargs)
        with mock.patch.object(m, "_write_bytes", side_effect=change_then_fail):
            with self.assertRaisesRegex(m.Blocked, "recovery required"):
                m.install(self.source, self.target)
        self.assertEqual((self.target / "governance/AgentOS/VERSION").read_bytes(), b"concurrent user edit")
        self.assertTrue((self.target / m.STATE_DIR / "receipt.json").is_file())

    def test_concurrent_user_edit_immediately_before_replace_is_preserved(self):
        m.install(self.source, self.target)
        self.write("governance/AgentOS/VERSION", b"2.0\n")
        self.write("tools/example.py", b"new tool bytes")
        self.seal()
        original = m._write_bytes
        victim = self.target / "tools/example.py"
        edited = False
        def inject(path, data, **kwargs):
            nonlocal edited
            if Path(path) == victim and not edited:
                edited = True
                victim.write_bytes(b"ordinary concurrent user edit")
            return original(path, data, **kwargs)
        with mock.patch.object(m, "_write_bytes", side_effect=inject):
            with self.assertRaisesRegex(m.Blocked, "recovery required"):
                m.install(self.source, self.target)
        self.assertEqual(victim.read_bytes(), b"ordinary concurrent user edit")

    def test_concurrent_user_edit_immediately_before_restore_is_preserved(self):
        m.install(self.source, self.target)
        self.write("governance/AgentOS/VERSION", b"2.0\n")
        self.write("tools/example.py", b"new tool bytes")
        self.seal()
        m.install(self.source, self.target)
        original = m._write_bytes
        victim = self.target / "tools/example.py"
        edited = False
        def inject(path, data, **kwargs):
            nonlocal edited
            if Path(path) == victim and not edited:
                edited = True
                victim.write_bytes(b"ordinary concurrent rollback edit")
            return original(path, data, **kwargs)
        with mock.patch.object(m, "_write_bytes", side_effect=inject):
            with self.assertRaisesRegex(m.Blocked, "Concurrent change"):
                m.rollback(self.target)
        self.assertEqual(victim.read_bytes(), b"ordinary concurrent rollback edit")

    def test_concurrent_user_edit_immediately_before_delete_is_preserved(self):
        m.install(self.source, self.target)
        (self.source / "tools/example.py").unlink()
        self.seal()
        original = m._delete_payload
        victim = self.target / "tools/example.py"
        def inject(path, expected):
            if Path(path) == victim:
                victim.write_bytes(b"ordinary concurrent delete edit")
            return original(path, expected)
        with mock.patch.object(m, "_delete_payload", side_effect=inject):
            with self.assertRaisesRegex(m.Blocked, "recovery required"):
                m.install(self.source, self.target)
        self.assertEqual(victim.read_bytes(), b"ordinary concurrent delete edit")

    def test_case_variant_reserved_source_directory_rejected(self):
        reserved = self.source / ".AGENTOS-INSTALL"
        reserved.mkdir()
        (reserved / "user.txt").write_bytes(b"must not be installation state")
        with self.assertRaises(m.Blocked):
            m.build_manifest(self.source)
        self.assertFalse(self.target.exists())

    def test_reparse_ancestor_rejected_via_lstat_attributes(self):
        original = Path.lstat
        ancestor = self.source.parent
        class ReparseInfo:
            st_mode = 0
            st_file_attributes = 0x400
        def lstat(path, *args, **kwargs):
            return ReparseInfo() if path == ancestor else original(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", lstat), self.assertRaises(m.Blocked):
            m.validate_bundle(self.source)

    def test_actual_symlink_refused_when_available(self):
        linked = self.root / "linked-bundle"
        try:
            linked.symlink_to(self.source, target_is_directory=True)
        except OSError as exc:
            self.skipTest("Symlink creation unavailable: " + str(exc))
        with self.assertRaises(m.Blocked):
            m.install(linked, self.target)

    def test_cli_reports_failure_and_rejects_arbitrary_manifest_output(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = m.main(["manifest", "--source", str(self.source), "--output", str(self.root / "outside.json")])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "blocked")
        self.assertFalse((self.root / "outside.json").exists())

    def test_unreadable_source_reports_blocked_without_installation(self):
        original = Path.read_bytes
        victim = self.source / "tools/example.py"
        def denied(path):
            if path == victim:
                raise PermissionError("synthetic denied read; no ACL modified")
            return original(path)
        with mock.patch.object(Path, "read_bytes", denied), contextlib.redirect_stdout(io.StringIO()) as output:
            result = m.main(["install", "--source", str(self.source), "--target", str(self.target)])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "blocked")
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
