#!/usr/bin/env python3
"""One-shot, target-bound stdin transport for the reviewed protected inventory."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import stat
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[3]
COLLECTOR = "deploy/staging/scripts/protected-ingress-collector.py"
RUNNER = "deploy/staging/scripts/protected-ingress-transport.py"
COLLECTOR_SHA256 = "43274ffb8a2aa3dffeff9e481328d586b456a443062f7d480728a23d70bc3ad4"
CLOUDFLARED_SHA256 = "fcfb02b575a52ca1af2e3267af4e1517bcdeb30ac48c834c69abaed3c0576ad2"
SSH = "/usr/bin/ssh"
CHILD_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "HOME": "/home/runner"}
LIMIT = 262144
TIMEOUT = 90
PREFLIGHT = {"host": "olivium-ephemerals", "address": "192.168.2.20", "user": "ec2-user"}
PREFLIGHT_SOURCE = '''import json,os,pwd,selectors,socket,subprocess,sys,time
try:
 p=subprocess.Popen(["/usr/sbin/ip","-j","-4","address","show"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 s=selectors.DefaultSelector();s.register(p.stdout,selectors.EVENT_READ);b=b"";end=time.monotonic()+5
 while s.get_map():
  if time.monotonic()>end: raise ValueError()
  for k,_ in s.select(0.1):
   x=os.read(k.fd,4096)
   if not x:s.unregister(k.fileobj)
   b+=x
   if len(b)>65536:raise ValueError()
 if p.wait(timeout=1)!=0:raise ValueError()
 rows=json.loads(b);addresses={a.get("local") for r in rows for a in r.get("addr_info",[]) if a.get("family")=="inet"}
 if socket.gethostname()!="olivium-ephemerals" or pwd.getpwuid(os.getuid()).pw_name!="ec2-user" or "192.168.2.20" not in addresses:raise ValueError()
 print(json.dumps({"host":"olivium-ephemerals","address":"192.168.2.20","user":"ec2-user"},sort_keys=True),flush=True)
except BaseException:
 if "p" in globals() and p.poll() is None:p.kill()
 sys.exit(73)
'''


class TransportError(Exception):
    def __init__(self, stage=None, remote_failure="unknown"):
        self.stage = stage
        self.remote_failure = remote_failure


REMOTE_FAILURES = frozenset(("sudo-authentication-failed", "sudo-policy-denied",
                           "tty-required", "remote-interpreter", "unknown"))


def classify_remote_failure(raw, source):
    """Project bounded stderr indications, never authentication/authority proof."""
    if len(raw) > LIMIT:
        return "unknown"
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n")
    except UnicodeError:
        return "unknown"
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        return "unknown"
    lines, found = text.split("\n"), set()
    if any(re.fullmatch(r"sudo: (?:1 incorrect password attempt|(?:[2-9]|[1-9][0-9]{1,2}) incorrect password attempts)", line) for line in lines):
        found.add("sudo-authentication-failed")
    policy_lines = (
        "ec2-user is not in the sudoers file.",
        "ec2-user is not in the sudoers file.  This incident will be reported.",
        "ec2-user is not allowed to run sudo on olivium-ephemerals.",
        "Sorry, user ec2-user may not run sudo on olivium-ephemerals.",
    )
    if any(line in policy_lines or line.removeprefix("sudo: ") in policy_lines for line in lines):
        found.add("sudo-policy-denied")
    # sudo's command denial contains the complete multi-line source argument.
    # Match only our actual reviewed invocation, not arbitrary command strings.
    denial = ("Sorry, user ec2-user is not allowed to execute '/usr/bin/python3 -I -B -c "
              + source + "' as root on olivium-ephemerals.")
    if re.search(r"(?m)^(?:sudo: )?" + re.escape(denial) + r"$", text):
        found.add("sudo-policy-denied")
    if "sudo: sorry, you must have a tty to run sudo" in lines:
        found.add("tty-required")
    if any(re.fullmatch(r"sudo: unable to execute /usr/bin/python3: (?:No such file or directory|Permission denied|Exec format error)", line) for line in lines):
        found.add("remote-interpreter")
    frame = any(re.fullmatch(r'  File "<string>", line [1-9][0-9]{0,5}(?:, in [A-Za-z_<>][A-Za-z0-9_<>]*)?', line) for line in lines)
    syntax = any(re.fullmatch(r"(?:SyntaxError|IndentationError|TabError):[^\n]*", line) for line in lines)
    runtime = any(re.fullmatch(r"(?:ImportError|ModuleNotFoundError|NameError|TypeError|AttributeError|ValueError|RuntimeError|OSError):[^\n]*", line) for line in lines)
    if frame and (syntax or ("Traceback (most recent call last):" in lines and runtime)):
        found.add("remote-interpreter")
    return next(iter(found)) if len(found) == 1 else "unknown"


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TransportError()
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(TransportError()))


def regular(path, mode=None):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise TransportError()
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise TransportError()


def provenance():
    expected = {"GITHUB_REPOSITORY": "olivium-dev/jeeb-infrastructure",
                "GITHUB_REF": "refs/heads/main", "SOURCE_REF_PROTECTED": "true",
                "SOURCE_DEFAULT_BRANCH": "main", "PROTECTED_INGRESS": "true",
                "GITHUB_ACTOR": "oudaykhaled", "GITHUB_TRIGGERING_ACTOR": "oudaykhaled",
                "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1"}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise TransportError()
    sha, run = os.environ.get("GITHUB_SHA", ""), os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"[1-9][0-9]{0,19}", run):
        raise TransportError()
    if os.environ.get("REVIEWED_SHA") != sha:
        raise TransportError()
    def git(*args):
        return subprocess.run(["/usr/bin/git", *args], cwd=ROOT, env=CHILD_ENV,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              check=True, timeout=10).stdout
    if git("rev-parse", "HEAD").decode().strip() != sha:
        raise TransportError()
    for name in (RUNNER, COLLECTOR):
        path = ROOT / name
        regular(path)
        if path.stat().st_size > LIMIT or path.read_bytes() != git("show", sha + ":" + name):
            raise TransportError()
    source = (ROOT / COLLECTOR).read_bytes()
    if hashlib.sha256(source).hexdigest() != COLLECTOR_SHA256:
        raise TransportError()
    return {"reviewedSourceSha": sha, "runId": run, "runAttempt": 1,
            "repository": expected["GITHUB_REPOSITORY"]}, source.decode("utf-8")


def configuration():
    temp = os.environ.get("RUNNER_TEMP", "")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", temp) or ".." in Path(temp).parts:
        raise TransportError()
    directory = Path(temp) / "jeeb-readiness-transport"
    if directory.resolve() != directory or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise TransportError()
    for name in ("config", "key", "known_hosts"):
        regular(directory / name, 0o600)
        if not 0 < (directory / name).stat().st_size <= LIMIT:
            raise TransportError()
    regular(directory / "cloudflared", 0o700)
    if not 0 < (directory / "cloudflared").stat().st_size <= 100 * 1024 * 1024:
        raise TransportError()
    if hashlib.sha256((directory / "cloudflared").read_bytes()).hexdigest() != CLOUDFLARED_SHA256:
        raise TransportError()
    expected = ["Host jeeb-staging-readiness", "  HostName jeeb-staging-ssh.fds-1.com",
                "  User ec2-user", f"  IdentityFile {directory}/key",
                f"  UserKnownHostsFile {directory}/known_hosts",
                f"  ProxyCommand {directory}/cloudflared access ssh --hostname %h",
                "  IdentitiesOnly yes", "  BatchMode yes", "  StrictHostKeyChecking yes",
                "  ConnectTimeout 20", "  ServerAliveInterval 10", "  ServerAliveCountMax 2"]
    if (directory / "config").read_text() != "\n".join(expected) + "\n":
        raise TransportError()
    return directory / "config"


def session(config, source, password):
    remote = ("/usr/bin/python3 -I -B -c " + shlex.quote(PREFLIGHT_SOURCE)
              + " && exec /usr/bin/sudo -S -p '' -u root -- /usr/bin/python3 -I -B -c " + shlex.quote(source))
    argv = [SSH, "-F", str(config), "-T", "-o", "NumberOfPasswordPrompts=0",
            "-o", "ClearAllForwardings=yes", "jeeb-staging-readiness", remote]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=CHILD_ENV, bufsize=0)
    except OSError:
        raise TransportError("transport") from None
    selector = selectors.DefaultSelector()
    stdout, stderr, total, verified = bytearray(), bytearray(), 0, False
    end = time.monotonic() + TIMEOUT
    try:
        selector.register(proc.stdout, selectors.EVENT_READ)
        selector.register(proc.stderr, selectors.EVENT_READ)
        while selector.get_map():
            if time.monotonic() >= end:
                raise TransportError()
            for key, _ in selector.select(min(0.1, max(0, end - time.monotonic()))):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > LIMIT:
                    raise TransportError()
                if key.fileobj is proc.stderr:
                    stderr.extend(chunk)
                if key.fileobj is proc.stdout:
                    stdout.extend(chunk)
                    if not verified:
                        newline = stdout.find(b"\n")
                        if (newline < 0 and len(stdout) > 1024) or newline > 1024:
                            raise TransportError()
                        if newline >= 0:
                            line, rest = bytes(stdout).split(b"\n", 1)
                            if strict_json(line) != PREFLIGHT:
                                raise TransportError()
                            verified = True
                            stdout[:] = rest
                            try:
                                # Cached/passwordless sudo can already be emitting
                                # the report. Never send a password into that stream.
                                if not rest:
                                    line = password + b"\n"
                                    if proc.stdin.write(line) != len(line):
                                        raise TransportError("transport")
                            except BrokenPipeError:
                                # The reviewed collector closes stdin immediately.
                                # No retry or password-acceptance claim; final report
                                # schema and exit/status still decide acceptance.
                                pass
                            finally:
                                proc.stdin.close()
        code = proc.wait(timeout=max(0.01, end - time.monotonic()))
        if not verified:
            raise TransportError("preflight")
        if code not in (0, 1):
            raise TransportError("remote-command", classify_remote_failure(stderr, source))
        try:
            return strict_json(stdout), code
        except (ValueError, TypeError, TransportError):
            if code == 0:
                raise TransportError("output") from None
            raise TransportError("remote-command", classify_remote_failure(stderr, source)) from None
    except TransportError as error:
        if error.stage:
            raise
        raise TransportError("preflight" if not verified else "transport") from None
    except BaseException:
        raise TransportError("preflight" if not verified else "transport") from None
    finally:
        selector.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()


def main():
    stage = "source"
    try:
        if len(sys.argv) != 1:
            raise TransportError()
        metadata, source = provenance()
        metadata["collectorSha256"] = COLLECTOR_SHA256
        stage = "configuration"
        config = configuration()
        stage = "secret"
        secret = os.environ.pop("STAGING_SUDO_PASSWORD", None)
        if not isinstance(secret, str):
            raise TransportError()
        password = secret.encode("utf-8")
        del secret
        if not 1 <= len(password) <= 4096 or any(byte in password for byte in (0, 10, 13)):
            raise TransportError()
        stage = "source"
        module = types.ModuleType("protected_collector")
        exec(compile(source, COLLECTOR, "exec"), module.__dict__)
        stage = "output"
        raw_report, exit_code = session(config, source, password)
        report = module.validate_report(raw_report)
        if (exit_code, report["status"]) not in ((0, "observed-local-consistency"), (1, "unverified")):
            raise TransportError()
        del password
        print(json.dumps({"transportStatus": "collected", "collectionResult": "complete" if exit_code == 0 else "partial",
                          "provenance": metadata, "report": report},
                         sort_keys=True, separators=(",", ":")))
        return 0
    except BaseException as error:
        if isinstance(error, TransportError) and error.stage in ("preflight", "transport", "remote-command", "output"):
            stage = error.stage
        projection = {"transportStatus": "unverified", "failureStage": stage}
        if stage == "remote-command":
            indication = error.remote_failure if isinstance(error, TransportError) else "unknown"
            projection["remoteFailure"] = indication if isinstance(indication, str) and indication in REMOTE_FAILURES else "unknown"
        failure = json.dumps(projection, separators=(",", ":"))
        print(failure)
        # The workflow redirects stdout to a report file. Preserve only this
        # fixed projection in failure logs, never remote stderr or exceptions.
        print(failure, file=sys.stderr)
        return 1
    finally:
        os.environ.pop("STAGING_SUDO_PASSWORD", None)


if __name__ == "__main__":
    sys.exit(main())
