# Tool Deployment Standard

> Version: 1.0
> Effective: 2026-10-29
> Authority: `${PROJECT_PATH}\999_AI_TOOLS_SKILLS\_ops\DEPLOYMENT_POLICY.md`

Every tool, CLI, IDE, MCP server, skill library, model cache and update
staging area on this host lives under
`${PROJECT_PATH}\999_AI_TOOLS_SKILLS`. The C: drive keeps only junctions.

## Mandatory rules

1. **Do not install a new tool to C:**. Confirm the install path points at
   `${PROJECT_PATH}\999_AI_TOOLS_SKILLS\installed\<name>` before the installer runs.
2. **A tool already on C: gets migrated**, not left in place. Keep the
   original C: path as a directory junction so installers, PATH entries,
   shortcuts and running programs keep working untouched.
3. **Skills** go to `${PROJECT_PATH}\999_AI_TOOLS_SKILLS\999_SKILLS`.
   The Magpie library is already there and is reached through
   `${USER_HOME}\.config\magpie\library`.
4. Placement by kind: complete applications to `installed\`, user
   configuration to `appdata\`, regenerable caches and model weights to
   `cache\`, installers to `downloads\`, portable tools to `portable\`.

## Before any migration

Check three things and state the result:

| Check | How | If it fails |
|---|---|---|
| Is the payload an MSI-registered product? | `Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'` | A junction will not work. Windows Installer protects the files and an elevated delete still returns `0x80070005`. Uninstall and reinstall to D: instead. |
| Is the application running? | `Get-CimInstance Win32_Process` | A running image cannot be deleted. Windows allows renaming it, but not inside `C:\Program Files`. Stop the process first. |
| Does the application update itself? | Inspect `app-update.yml` | An electron updater replaces the junction with a real directory and its uninstaller can empty the D: side. The watchdog repairs this; say so. |

## Evidence required before declaring a migration done

```powershell
pwsh -File ${PROJECT_PATH}\999_AI_TOOLS_SKILLS\scripts\Audit-ToolMigrationState.ps1
pwsh -File ${PROJECT_PATH}\999_AI_TOOLS_SKILLS\scripts\Verify-ToolMigrationFull.ps1
```

The audit must report every entry as a junction with a non-empty target.
The full verification hashes every file on both sides. "The path opens"
is not evidence that the migration succeeded.

## Do not

- Do not delete the C: path. Replace it with a junction.
- Do not delete files of a running application.
- Do not treat an equal file count as the verification criterion. The
  destination may legitimately hold more files than the source, for example
  when two architectures share one tree. The criterion is that every
  source file exists on the destination with the same size.
- Do not build a capability that depends on UAC elevation. Elevation on this
  host queues consent requests that are never confirmed, and the parent
  process waits forever. User-level scheduled tasks and logon entries are
  the reliable mechanism.

## Recovery and rollback

The registry at
`${PROJECT_PATH}\999_AI_TOOLS_SKILLS\_ops\TOOL_MIGRATION_REGISTRY_20261029.md`
holds the full C-to-D mapping, the failure modes found in practice and the
scripts that implement each step.

