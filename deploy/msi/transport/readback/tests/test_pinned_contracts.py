"""Exercise actual pinned read-only v9 contracts, in memory, with synthetic data."""
import hashlib
import io
import os
from pathlib import Path
import stat
import struct
import tarfile
import unittest
from unittest import mock

from test_audit import audit, SCRIPT

ARCHIVE = SCRIPT.parent.parent / 'jeeb-msi-runtime-activation-bootstrap-v9.tar'
with tarfile.open(ARCHIVE) as bundle:
    source = bundle.extractfile('jeeb-msi-runtime-activation-bootstrap-v9/payload/jeeb-msi-user-management-smtp-admin').read()
UM = audit.load_pinned_module('row20_test_pinned_um', source, audit.HELPERS['user-management-smtp'])


def acl(perm, extra=False):
    entries = [(1, perm, 0xffffffff), (2, perm, 1001), (4, 0, 0xffffffff), (16, perm, 0xffffffff), (32, 0, 0xffffffff)]
    if extra:
        entries.append((2, perm, 1002))
    return struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *item) for item in entries)


def credentials(extra_principal=False, extra_member=False, mismatch=False):
    info = os.stat_result((stat.S_IFREG | 0o440, 1, 1, 1, 0, 0, 7, 0, 0, 0))
    files = {name: (info, b'fixture', acl(4, extra_principal)) for name in UM.FIELDS}
    if extra_member:
        files['unexpected'] = (info, b'fixture', acl(4))
    if mismatch:
        files[UM.FIELDS[0]] = (info, b'different', acl(4))
    return UM.RuntimeCredentials(0, 0, 0o550, acl(5), True, files)


class PinnedCredentialTests(unittest.TestCase):
    def test_exact_acl_fixture_passes_real_v9_validator(self):
        UM.verify_runtime_credentials(credentials(), dict.fromkeys(UM.FIELDS, 'fixture'), 1001, 1001)

    def test_extra_acl_principal_fails_real_v9_validator(self):
        with self.assertRaises(UM.ActivationError):
            UM.verify_runtime_credentials(credentials(extra_principal=True), dict.fromkeys(UM.FIELDS, 'fixture'), 1001, 1001)

    def test_extra_member_fails_real_v9_validator(self):
        with self.assertRaises(UM.ActivationError):
            UM.verify_runtime_credentials(credentials(extra_member=True), dict.fromkeys(UM.FIELDS, 'fixture'), 1001, 1001)

    def test_runtime_source_mismatch_fails_real_v9_validator(self):
        with self.assertRaises(UM.ActivationError):
            UM.verify_runtime_credentials(credentials(mismatch=True), dict.fromkeys(UM.FIELDS, 'fixture'), 1001, 1001)

    def test_unknown_prefixed_shadow_fails(self):
        with self.assertRaises(audit.AuditHold):
            audit.smtp_shadows_absent({'PasswordResetSmtp__Unexpected': 'fixture'})

    def test_extra_dropin_fails_real_candidate_validator(self):
        layout = UM.PRODUCTION
        release = UM.current_stage(layout).release
        class System:
            def show(self):
                return {'Id': UM.UNIT, 'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
                        'User': 'ec2-user', 'Group': 'ec2-user', 'WorkingDirectory': str(release),
                        'DropInPaths': ' '.join(map(str, [layout.base_dropin, layout.activation_dropin, UM.FIREBASE_DROPIN])) + ' /unexpected.conf'}
        with self.assertRaises(UM.ActivationError):
            UM.verify_candidate(layout, System(), release, {}, str(UM.FIREBASE_TARGET))


class ArchiveReceiptTests(unittest.TestCase):
    def fixture(self, path='UserManagement.dll'):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:') as archive:
            item = tarfile.TarInfo(path)
            item.size = 7
            item.mode = 0o644
            archive.addfile(item, io.BytesIO(b'fixture'))
        raw = output.getvalue()
        files = [{'path': path, 'size': 7, 'mode': '0644', 'sha256': hashlib.sha256(b'fixture').hexdigest()}]
        return raw, files

    def test_exact_fixture_archive_and_receipt_pass(self):
        raw, files = self.fixture()
        with mock.patch.object(audit, 'NATIVE_ARCHIVE', hashlib.sha256(raw).hexdigest()):
            audit.archive_manifest_exact(raw, files)

    def test_mutated_receipt_member_fails(self):
        raw, files = self.fixture()
        files[0]['sha256'] = '0' * 64
        with mock.patch.object(audit, 'NATIVE_ARCHIVE', hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(audit.AuditHold):
                audit.archive_manifest_exact(raw, files)

    def test_traversal_in_archive_fails_even_when_hash_matches(self):
        raw, files = self.fixture('../escape')
        with mock.patch.object(audit, 'NATIVE_ARCHIVE', hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(audit.AuditHold):
                audit.archive_manifest_exact(raw, files)

    def test_extra_receipt_member_fails(self):
        raw, files = self.fixture()
        files.append(dict(files[0], path='unexpected'))
        with mock.patch.object(audit, 'NATIVE_ARCHIVE', hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(audit.AuditHold):
                audit.archive_manifest_exact(raw, files)

class LatePhaseTests(unittest.TestCase):
    def test_secret_bearing_failure_after_credentials_are_held_is_redacted(self):
        import contextlib
        import types
        raw_archive = ARCHIVE.read_bytes()
        with tarfile.open(fileobj=io.BytesIO(raw_archive)) as archive:
            payloads = {name: archive.extractfile('jeeb-msi-runtime-activation-bootstrap-v9/payload/jeeb-msi-' + name + '-admin').read()
                        for name in audit.HELPERS}
            policy = archive.extractfile('jeeb-msi-runtime-activation-bootstrap-v9/payload/jeeb-msi-runtime-activation.sudoers').read()
        class P:
            def __init__(self, value): self.value = value
            def __str__(self): return self.value
            def __truediv__(self, value): return P(self.value + '/' + value)
            def exists(self): return False
            def is_symlink(self): return self.value.endswith('/current')
            def iterdir(self): return [types.SimpleNamespace(name=name) for name in ('receipt', 'staged-artifact', 'versions', 'current')]
        layout = types.SimpleNamespace(hostname=audit.HOST, ipv4='192.168.2.39', unit=audit.UNIT,
                                       bundle_root=P('/bundle'), fragment=P('/fragment'))
        fields = ('PasswordResetSmtp__Host', 'PasswordResetSmtp__Port', 'PasswordResetSmtp__Username', 'PasswordResetSmtp__Password', 'PasswordResetSmtp__FromAddress')
        def fail_after_values(_layout, _system, _release, values, _firebase):
            self.assertEqual(set(values), set(fields))
            self.assertEqual(set(values.values()), {'SECRET-CANARY'})
            raise RuntimeError('SECRET-CANARY')
        reached = mock.Mock(side_effect=fail_after_values)
        module = types.SimpleNamespace(PRODUCTION=layout, SOURCE_COMMIT=audit.SOURCE,
             NATIVE_ARCHIVE_SHA256=audit.NATIVE_ARCHIVE, RECEIPT_NAME='receipt', ARCHIVE_NAME='native.tar',
             VERSION='v1', FIELDS=fields, FIREBASE_TARGET=P('/firebase'),
             ProductionSystem=types.SimpleNamespace(process_cwd=lambda p: None, ready=lambda *a: True),
             current_stage=lambda x: types.SimpleNamespace(release=P('/release')),
             superseded_stage=lambda x: types.SimpleNamespace(release=P('/superseded')),
             read_stage_receipt=lambda x: (P('/release'), {'files': [{}] * 38}),
             validate_installed_bundle=lambda x: P('/bundle/versions/v1'), verify_candidate=reached)
        def read(path, **_kw):
            if path.startswith('/usr/local/sbin/jeeb-msi-'):
                return payloads[path[len('/usr/local/sbin/jeeb-msi-'):-len('-admin')]]
            if path == audit.POLICY: return policy
            if path.startswith('/root/jeeb-msi-runtime-activation-bootstrap'): return raw_archive
            if path.rsplit('/', 1)[-1] in fields: return b'SECRET-CANARY'
            return b'{}'
        def cmd(*args): return b'192.168.2.39' if args[0].endswith('hostname') else b''
        with contextlib.ExitStack() as stack:
            patches = [(audit.sys, 'argv', [audit.FIXED_SCRIPT]),
                       (audit.sys, 'flags', types.SimpleNamespace(isolated=1, dont_write_bytecode=1)),
                       (audit, '__file__', audit.FIXED_SCRIPT)]
            for obj, name, value in patches: stack.enter_context(mock.patch.object(obj, name, value))
            for obj, name, value in ((audit.os,'geteuid',0), (audit.socket,'gethostname',audit.HOST),
                                     (audit,'require_empty_stdin',None), (audit,'protected_directory',None),
                                     (audit.resource,'setrlimit',None), (audit.signal,'signal',None),
                                     (audit.signal,'alarm',None), (audit.sys,'addaudithook',None),
                                     (audit.fcntl,'flock',None), (audit,'bounded_tree',None),
                                     (audit,'archive_manifest_exact',None), (audit,'load_pinned_module',module),
                                     (audit.os,'readlink','versions/v1')):
                stack.enter_context(mock.patch.object(obj, name, return_value=value))
            stack.enter_context(mock.patch.object(audit,'read_file',side_effect=read))
            stack.enter_context(mock.patch.object(audit,'command',side_effect=cmd))
            stack.enter_context(mock.patch.object(audit,'protected_fd',side_effect=lambda *a,**k: os.open('/dev/null',os.O_RDONLY)))
            stack.enter_context(mock.patch.object(audit,'show',return_value={'FragmentPath':'/fragment','NRestarts':'0','MainPID':'123'}))
            result = audit.run_audit()
        reached.assert_called_once()
        self.assertEqual(result['failurePhase'], 'um-runtime')
        self.assertEqual(result['checks']['um-credentials'], 'passed')
        self.assertEqual(result['checks']['um-runtime'], 'failed')
        self.assertEqual(result['checks']['chat-stage'], 'not-run')
        self.assertNotIn('SECRET-CANARY', str(result))
        self.assertFalse(result['cutoverGo'])
