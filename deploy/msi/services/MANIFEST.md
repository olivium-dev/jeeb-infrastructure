# Candidate manifest contract (schema 1)

This tool deploys **reviewed prebuilt bytes**, not a repository name or a branch
head. Every host action requires `--manifest` and an independently approved
`--manifest-sha256`. SHA values are lowercase hexadecimal; Git commits are 40
characters and SHA-256 values are 64. Hash exact file bytes, not a reserialized
JSON representation, when approving an input file.

The supplied manifest hash is the trust root. `approved_commit`, review hashes
and provenance hashes are operator declarations: the tool validates their shape
and consistency but does **not** contact GitHub, authenticate a reviewer, verify
a signature, or independently attest that a binary came from a commit. Keep and
review the actual source/build/test evidence separately. A syntactically valid
manifest is not deployment authorization.

## Observation input

Before capturing a baseline, enumerate the incumbent configuration files and
shell-sourced environment files privately. `inspect` accepts this smaller input:

```json
{
  "schema": 1,
  "service": "user-management",
  "config_files": ["/ABSOLUTE/INCUMBENT/appsettings.json"],
  "launch": {
    "environment_bindings": [
      {"path": "/ABSOLUTE/INCUMBENT/service.env"}
    ]
  },
  "path_bindings": [
    {
      "path": "appsettings.json",
      "target": "/ABSOLUTE/INCUMBENT/appsettings.json",
      "kind": "config"
    }
  ]
}
```

Replace these deliberately nonexistent placeholders before approving the input.
The output must be a **new file** in a root-owned mode-0700 directory with
root-owned, non-group/world-writable physical ancestors, for example an approved
private directory under `/root`. It contains:

- `baseline.units`: exact redacted system and user-manager snapshots for running
  `jeeb-*` services, settlement, nginx and the MSI tunnel unit.
- `baseline.files`: hashes of observed unit fragments/drop-ins, declared systemd
  environment files, requested configuration and shell-environment sources.
- `baseline.listener_addresses`: actual `ss` address representations for the
  selected unit's catalog port; do not translate or invent these values.
- `incumbent_environment`: per-variable value hashes from the selected process,
  not raw values. This is a starting observation, not an automatically approved
  candidate environment.

Copy the complete `baseline` object into the candidate manifest. Capture again
after another service is legitimately deployed; its changed PID/configuration
will invalidate older peer baselines. Do not reuse a saved baseline merely
because the date looks recent: exact state is checked again before selection.
The read-only capture does not prove that every active owner is running.

## Required candidate fields

| Field | Required value / meaning |
| --- | --- |
| `schema` | Integer `1`. |
| `service` | Exact catalog service ID; it must match the selected wrapper. |
| `run_id` | New `[a-z0-9][a-z0-9-]{0,79}` identifier. Choose a timestamp-prefixed ID that sorts after previous deployment drop-ins. Reusing an existing release/drop-in/report is rejected. |
| `catalog_sha256` | Hash of the reviewed `service-catalog.json` bytes used by the command. |
| `launcher_sha256` | Hash of the reviewed sibling `native_launch.py` bytes. Review and pin the whole tooling revision separately as well. |
| `source.repository` | Exact `olivium-dev/<repository>` catalog value. |
| `source.commit` | Exact approved candidate Git commit, not a mutable ref. |
| `source.default_branch` | Refreshed repository default branch; must match the catalog. |
| `source.default_commit` | Exact observed default-branch commit. Candidate may differ only with explicit reviewed approval. |
| `source.approved_commit` | Boolean `true` only after approval. |
| `source.provenance_sha256` | Hash of separately retained source/build/test evidence. |
| `artifact.path` / `artifact.sha256` | Physical absolute MSI path and hash of the complete finite tar artifact. |
| `artifact.files` | Exact inventory of every regular payload file: `path`, `sha256`, integer `size`, boolean `executable`. |
| `baseline` | Complete object from the fresh observation output, reviewed for coverage. |
| `config_files` | Nonempty list of incumbent configuration files required by the candidate; all must be in baseline files and bound as configuration. |
| `path_bindings` | Explicit existing config-file and persistent-directory mappings described below. Empty is accepted only if the required configuration rules can still be satisfied. |
| `runtime_files` | Array of external runtime/tool/library file pins: physical `path`, `sha256`, numeric `uid`, numeric permission `mode`. Must include the resolved external launch executable and external final executable when applicable. Add the runtime libraries/tools needed to substantiate compatibility. |
| `expected_environment` | Exact final process environment map: variable name to SHA-256 of its raw value bytes. No raw values. |
| `launch` | Reviewed launch contract described below. |

An array inventory entry is, for example, `{"path":"UserManagement.dll",
"sha256":"REPLACE_WITH_REAL_SHA256","size":12345,"executable":false}`.
The illustrative size/hash are not actual build evidence.

### Launch contract

```json
{
  "argv": ["/ABSOLUTE/PINNED/dotnet", "{release}/UserManagement.dll"],
  "environment_bindings": [
    {
      "path": "/ABSOLUTE/INCUMBENT/service.env",
      "sha256": "REPLACE_WITH_REAL_SHA256",
      "export_all": false
    }
  ],
  "source_review_sha256": "REPLACE_WITH_APPROVED_LAUNCH_REVIEW_SHA256",
  "argv_policy": "runtime-and-paths-only",
  "contains_no_inline_credentials": false,
  "configuration_and_persistent_paths_reviewed": false
}
```

The two review booleans deliberately start **false**: this is not an approved
manifest. Change them only after reviewing the exact runtime source contract.

`{release}` expands to
`/opt/jeeb-msi-service-releases/<service>/<run_id>`. The selected unit runs with
that actual working directory; do not assume that a framework's content-root
setting also fixes paths resolved against the OS working directory. Launch
arguments must select the new release, be non-secret runtime/path arguments,
and contain no inline credential/config assignments. Ports or module names can
be separate non-secret arguments. The engine rejects `=` assignments, control
characters and systemd `%` specifiers. Do not put shell `-c` command strings or
provider credentials in the launch manifest.

The helper runs as the existing non-root service identity. For each reviewed
shell-source binding it checks the hash, freezes bytes in a sealed anonymous
memory file, sources them using Bash, and closes the descriptor before the final
exec. `export_all: true` deliberately uses shell `set -a`; `false` preserves
explicit exports only. Match the incumbent source semantics and ordering. This
is executable shell source under the service UID, **not** a generic dotenv
parser. Do not duplicate a systemd `EnvironmentFile` as a shell binding unless
the reviewed launch actually needs both. Existing systemd environment settings
remain in place.

Review inherited unit hooks (`ExecStartPre`, `ExecStartPost`, stop commands and
other loaded directives) as well as the application entrypoint. The deployer
preserves those files; it cannot promise they have no startup effects.

### Configuration and persistent paths

These links are created by the deployer from approved bindings; the archive
itself cannot contain symlinks. Targets must already exist at physical paths.

```json
[
  {
    "path": "appsettings.json",
    "target": "/ABSOLUTE/INCUMBENT/appsettings.json",
    "kind": "config",
    "sha256": "REPLACE_WITH_REAL_SHA256",
    "uid": 1001,
    "mode": 384
  },
  {
    "path": "uploads",
    "target": "/ABSOLUTE/EXISTING/uploads",
    "kind": "persistent-directory",
    "uid": 1001,
    "mode": 488,
    "device": 123,
    "inode": 456
  }
]
```

All numbers above are **illustrative, not observed permissions/inodes**. JSON
uses decimal permission numbers: `384` is octal `0600`, `488` is octal `0750`,
`493` is octal `0755`. Record actual values; never chmod existing credentials or
storage to fit a template. Config files are hash-pinned; persistent directories
are pinned by device/inode/owner/mode, not content hash, because application
data can legitimately change.

Declare every required framework config variant and relative storage/generated
path. Do not bind the old application directory as the entire new release: that
could select stale code. Do not bind an old Python code package to make imports
work; package the new code and explicitly preserve only its reviewed writable
data/template locations. Names cannot overlap payload files, be ancestors of
other declared entries, traverse `..`, or occupy the reserved `.msi` namespace.
There is no automatic config discovery, secret copy, data migration or storage
permission repair.

### Environment and transforming processes

Hash each final raw environment value independently. The projection validates
then omits only `INVOCATION_ID`, `SYSTEMD_EXEC_PID` and `JOURNAL_STREAM`, whose
identities change with systemd invocation. Everything else—including runtime,
framework and real/fake-provider mode—must match the approved hash map. Derive
intentional differences such as the new working-directory value from source
review and inert Linux execution; do not accept an arbitrary post-deployment
environment by replacing the expectation with whatever happened.

Direct native executables and ordinary `dotnet <new.dll>` launches are checked
against the expanded `launch.argv` and resolved executable. An Elixir release
launcher can exec BEAM with different arguments; some Python wrappers also
transform the process. Such launches require this additional top-level field:

```json
{
  "expected_process": {
    "argv_sha256": "REPLACE_WITH_FINAL_NUL_DELIMITED_ARGV_SHA256",
    "exe": "/ABSOLUTE/PINNED/beam.smp",
    "release_argument": "{release}/releases/APPROVED_VERSION/start",
    "source_review_sha256": "REPLACE_WITH_APPROVED_PROCESS_REVIEW_SHA256"
  }
}
```

Derive the exact executable, NUL-delimited `/proc/<pid>/cmdline` hash (including
its trailing NUL) and a complete release-specific argument from the approved
launcher/build, validated with inert Linux execution. The shown path is only a
placeholder, **not** a claim about either existing BEAM process. The expanded
release argument must be an exact final argv element, not a substring. Final
external executables must also be runtime-pinned; a packaged executable may use
`{release}/...`. Never put raw BEAM cookies or credentials in these records.

## Artifact rules and build boundaries

Use USTAR (`tarfile.USTAR_FORMAT` / an explicitly reviewed USTAR packer), plain or
gzip-compressed. Supply only the finite regular-file inventory: no recursive
directory entries, links/hardlinks, devices, PAX/GNU metadata or hidden appended
archives. Directory structure is created from validated file names. Files must
have canonical relative ASCII paths within USTAR limits. The engine checks raw
headers as well as every extracted file hash, size and inventory membership.
Limits: 10,000 files, 512 MiB archive/file limit, 1.5 GiB expanded payload.

Exclude `.git`, `.env*`, credentials/secrets/fixtures, `appsettings*`, private
keys/certificates and debug/backup files. These filename checks are **not a
secret scanner**: inspect all bytes before approving the artifact. Runtime
configuration belongs in reviewed incumbent bindings, not packages. Output
files become root-owned `0444` (data/code) or `0555` (executable); application
writes belong only in separately declared existing data paths.

Use the service repository's build/test contract for its specific revision:

- .NET: respect `global.json`, locked restore and target Linux ABI. Do not turn a
  self-contained app into a framework-dependent one without runtime evidence.
- Go/Rust: attest the toolchain, lockfiles and resulting Linux executable; retain
  CGO/libc compatibility where applicable.
- Python: package approved new source and frozen Linux dependencies or use the
  explicitly pinned existing compatible Linux environment. Never copy a macOS
  venv. Native MSI and Docker Python versions currently differ for several apps.
- Elixir: pin Elixir/OTP/ERTS, release and libc compatibility. Preserve incumbent
  `MIX_ENV` and external runtime choices. Do not reuse Docker server wrappers
  that migrate before starting, or mistake a release shell for its final BEAM
  process contract.

The tool does not build these artifacts or resolve missing dependencies. Source
review must identify unsupported writable paths, ports, subprocess/listener
ownership, runtime transforms and startup effects **before** deployment, not
after a selected candidate fails.

## Selection, evidence and limits

The new system-manager drop-in is
`/etc/systemd/system/<unit>.d/zzzzzz-msi-release-<run_id>.conf`; user-manager
drop-ins are created as the matching user in its existing
`~/.config/systemd/user/<unit>.d` directory. Ordering is verified, so a new ID
must sort after all existing drop-in names. An inert `.pending` hardlink remains
as publication evidence; it is not a selectable fallback.

Private phase records use
`/var/tmp/jeeb-msi-deploy-<service>-<run_id>/` (root `0700`, files `0600`). No raw
service journal is exported. Treat environment hashes and topology metadata as
private even though values are not printed. Protect manifests and review
evidence accordingly; do not commit these host-specific records.

This is an **upgrade of an existing running service**, not first installation or
repair of an inactive unit. Incumbent health is required. If a failed candidate
leaves the service down, this tool will not silently waive that gate: an
operator must review a separate forward-repair procedure. Likewise, an
unrecognized systemd shape, stale probe contract or source/configuration gap is
a stopped operation, not authority to invent a baseline or restore an old
release. There is no rollback mechanism.
