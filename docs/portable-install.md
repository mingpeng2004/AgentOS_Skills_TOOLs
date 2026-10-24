# Offline portable installation

This is the recommended installation path. The old AgentOS GUI/PowerShell
installers are retained as legacy source, not called by this tool. Python 3.9+
and its standard library are required. No dependency is downloaded.

## Bundle preparation and installation

The publisher generates `portable-manifest.json` from the final bundle. It lists
every installable file's SHA256 and byte size. The manifest itself is excluded
to avoid self-reference. Any additional exclusion must name an exact existing
file; excluded files are not installed. No glob or directory exclusion exists.
The source package root's `.git` directory or worktree-style `.git` file
(case-insensitive name match) is
repository metadata and is automatically ignored during manifest generation and
validation; it is never copied. Its path still undergoes link/reparse checks and
is never followed. Nested `.git` paths are not automatically excluded and remain
subject to the complete manifest. A target that later acquires a root `.git`
directory (even empty) or file blocks reinstall and rollback, preserving the
user's repository instead of treating it as disposable installation state.

```powershell
python -B tools/portable_install.py manifest --source C:\Bundles\AgentOS
python -B tools/portable_install.py validate --source C:\Bundles\AgentOS
python -B tools/portable_install.py install --source C:\Bundles\AgentOS --target C:\Tools\AgentOS --dry-run
python -B tools/portable_install.py install --source C:\Bundles\AgentOS --target C:\Tools\AgentOS
python -B tools/portable_install.py rollback --target C:\Tools\AgentOS --dry-run
python -B tools/portable_install.py rollback --target C:\Tools\AgentOS
```

The example paths are placeholders, not this machine's configuration. All paths
must be absolute. The target parent must already exist. First installation is
create-only: an existing arbitrary or empty directory is not adopted. An
unchanged managed installation can be updated; installing the identical bundle
is a no-op. Source and target must not overlap. Missing/added/changed source or
installed files, path traversal, Windows device names, case collisions, symlinks
and Windows reparse points in any existing ancestor block the operation.

The tool only deploys files. It does not set environment variables, activate
client rules, register projects, alter security controls, install services or
create schedules. Any such integration requires a separate explicit plan.

## Backup, receipts and recovery

Before payload writes, `.agentos-install/history/<transaction>/` stores a
verified complete prior payload backup and `before.json`. A first installation
records the prior absence of the target. The active `receipt.json` records the
transaction, manifest fingerprint and installed file hashes. No private source
path or credential is needed in the installed receipt.

Rollback verifies the entire current payload and the entire backup before its
first write. A subsequent user modification, new file, missing file or damaged
backup blocks rollback rather than overwriting user work. An update rollback
restores the previous payload and receipt. A first-install rollback removes the
transaction-created directory. The manifest is a distribution verification
input and is not itself installed; the installed receipt binds its digest.
Each payload replacement/deletion rechecks the expected old content immediately
before the write. This reduces ordinary concurrent-edit races; it is not an
operating-system compare-and-swap or protection against a hostile same-user
process. Backups and rollback preserve file bytes and managed receipts, not ACLs,
ownership, executable modes, timestamps or other filesystem metadata.

Ordinary caught installation failures attempt restoration from verified backups.
If unexpected concurrent changes prevent safe restoration, state is preserved
and the operation reports `blocked`/recovery required. Abrupt process termination
can leave an `installing` receipt or operation lock: do not delete the lock and
rerun blindly. Preserve the target and backup, inspect the receipt and obtain
supervised recovery. Rollback I/O failures likewise remain explicit failures;
the backup is retained. No claim of crash-proof transactions is made.

These checks are cooperative same-user protections, not a defense against an
administrator or concurrent hostile process. Hash manifests provide integrity
relative to the manifest, not publisher authentication; obtain the bundle through
the reviewed repository commit and independently verify its published hashes.
Installed backups and receipts are private local state and must not be published.

## Python interface

`build_manifest(package, exclusions=())` returns the manifest dictionary.
`validate_bundle(source)` verifies and returns it. `install(source, target,
dry_run=False)` returns an installed/unchanged/planned result. `rollback(target,
dry_run=False)` returns a rolled_back/planned result. `Blocked` indicates a
failed precondition or safely reported failure. The CLI returns 0 only for a
completed validation/plan/operation and 2 for blocked/failed operations. A dry run
does not install anything, and file installation is not client activation or
another physical computer's acceptance evidence.
