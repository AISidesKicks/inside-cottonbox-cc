# AI Sandbox Demo Lab: bubblewrap

A hands-on lab for running AI coding agents inside bubblewrap. We start from the smallest possible sandbox and build up to a wrapper you can actually use: isolated home, read-only system tree, dropped capabilities, a seccomp deny-list, an audit log, and a probe script that proves the confinement works.

The examples are generic - swap in whichever agent CLI you use. The same ground is covered for the other three approaches in [the microsandbox lab](microsandbox.md), [the nanvix lab](nanvix.md), and [the Docker Sandboxes lab](dockersandboxes.md), including how each one blocks the network connections an agent should not make.

## Why bubblewrap for AI

AI agents execute code we did not write and often cannot fully predict. A bad tool call, a prompt injection, or a plain mistake should not be able to read your SSH keys, rewrite a sibling project, or load a kernel module. We want separation, not a vault: something slim, fast, and easy to layer around every agent we start.

bubblewrap fits that shape well:

- unprivileged - no daemon, no root, no setuid helper required
- tiny - one binary, the policy is just command-line flags
- fast - a new mount namespace and a few bind mounts, milliseconds
- layerable - you can nest it with other tools and wrap only what you need

Upstream project: https://github.com/containers/bubblewrap

## What bubblewrap is (and is not)

bubblewrap creates a new mount namespace whose root is an empty tmpfs that disappears when the last process exits. It then binds in exactly the parts of the filesystem you ask for, plus the namespaces and filters you enable.

It uses user namespaces so an unprivileged user can build this, and it sets `PR_SET_NO_NEW_PRIVS`, which turns off setuid binaries - the classic way out of a chroot.

The important part: bubblewrap is not a ready-made sandbox. The level of protection is entirely determined by the flags you pass. This lab is mostly about choosing those flags well.

## Requirements

- Linux with user namespaces enabled. Verify with:

```sh
unshare --user --pid echo ok
```

- `bubblewrap` (this lab was written against 0.9.0)
- `bash` 4.4 or newer (the wrapper uses arrays and `set -u`)
- optional: `python3` plus `python3-libseccomp` for the seccomp lab, and `seccomp-tools` to disassemble a generated filter

Install:

```sh
# Fedora, RHEL, Rocky, Alma, Amazon Linux 2023
sudo dnf install -y bubblewrap python3 python3-libseccomp

# Debian, Ubuntu
sudo apt-get install -y bubblewrap python3 python3-seccomp
```

## Lab layout

We will put four small files in place:

```
~/.local/bin/ai-sandbox        # the wrapper that launches a sandboxed command
~/.local/bin/ai-sandbox-shell  # interactive shell inside the same sandbox view
~/.local/bin/seccomp-deny.py   # emits the BPF seccomp filter
~/.local/bin/ai-lab-test       # probe runner that asserts the confinement

~/.local/share/ai-lab/home/    # the isolated HOME the agent sees
~/.local/share/ai-lab/log/     # invocation log
```

## Lab 1: the smallest sandbox

This is the trimmed upstream demo. It runs a shell that reuses the host `/usr`:

```sh
bwrap \
  --ro-bind /usr /usr \
  --symlink usr/lib64 /lib64 \
  --proc /proc \
  --dev /dev \
  --unshare-pid \
  --new-session \
  bash
```

Things to notice once you are inside:

- `/usr` is the host tree, mounted read-only
- `/` is otherwise empty, because the root is a fresh tmpfs
- the process table only shows the sandbox, thanks to the PID namespace
- `--new-session` calls `setsid()`, which protects the host shell from TIOCSTI keystroke injection (CVE-2017-5226)

This is incomplete for real use: there is no `/etc`, no writable home, and no `/tmp`. It is a good first look at the mechanism.

## Lab 2: assemble an agent-grade root

Now the full invocation. This is the shape the wrapper in Lab 3 uses, verified on bubblewrap 0.9.0:

```sh
LAB_HOME="$HOME/.local/share/ai-lab/home"
PROJECT="$(pwd)"
mkdir -p "$LAB_HOME"

bwrap \
  --unshare-all --unshare-user --share-net \
  --ro-bind /usr /usr \
  --ro-bind-try /etc /etc \
  --symlink usr/bin /bin \
  --symlink usr/sbin /sbin \
  --symlink usr/lib /lib \
  --symlink usr/lib64 /lib64 \
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --dir /run \
  --bind "$LAB_HOME" "$HOME" \
  --ro-bind-try "$HOME/.gitconfig" "$HOME/.gitconfig" \
  --bind "$PROJECT" "$PROJECT" \
  --chdir "$PROJECT" \
  --clearenv \
  --setenv HOME "$HOME" \
  --setenv PATH "$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" \
  --setenv TERM "${TERM:-xterm-256color}" \
  --new-session \
  --die-with-parent \
  --cap-drop ALL \
  --disable-userns \
  --assert-userns-disabled \
  --hostname ai-lab \
  bash
```

What each group does:

| Flags | Effect |
|---|---|
| `--unshare-all` | fresh user, mount, PID, IPC, UTS, cgroup and network namespaces |
| `--unshare-user` | explicit user namespace. Needed before `--disable-userns`, since bubblewrap only implies it when not setuid |
| `--share-net` | keep the host network. Drop this flag for a fully offline sandbox |
| `--ro-bind /usr /usr` | read-only system tree, so the agent can run its own binaries but not patch them |
| `--ro-bind-try /etc /etc` | config files the agent needs: passwd, ssl certs, resolv.conf. `-try` keeps it working on unusual systems |
| `--symlink ...` | the usual merged-usr links so the dynamic loader and shebangs resolve |
| `--proc /proc`, `--dev /dev` | a fresh procfs and a fresh devtmpfs, not the host ones |
| `--tmpfs /tmp` | private scratch space, discarded on exit |
| `--bind "$LAB_HOME" "$HOME"` | the isolated home. The agent sees a clean `$HOME`, never yours |
| `--bind "$PROJECT" "$PROJECT"` | the one directory the agent may read and write |
| `--clearenv` + `--setenv` | a clean environment. Note that `--clearenv` must come before any `--setenv` |
| `--new-session` | blocks TIOCSTI keystroke injection |
| `--die-with-parent` | the sandbox dies with the wrapper, no orphan agents |
| `--cap-drop ALL` | drop every capability. Matters most when the wrapper runs as root, for example in CI |
| `--disable-userns` + `--assert-userns-disabled` | no nested user namespaces from inside, and fail loudly if that could not be enforced |
| `--hostname ai-lab` | the sandbox gets its own hostname |

Two deliberate omissions:

- no `--dev-bind /dev /dev`, so GPU and similar device integrations are unavailable
- no `--ro-bind /var /var`, so package databases are not visible. Add `--ro-bind-try` lines if a tool needs them

## Lab 3: the wrapper

Save this as `~/.local/bin/ai-sandbox` and make it executable. It adds the isolated home, the invocation log, and the seccomp filter from Lab 6:

```bash
#!/usr/bin/env bash
# ai-sandbox: run a command (an agent, a test, a shell) in a bubblewrap sandbox
set -euo pipefail

LAB="${AI_LAB_HOME:-$HOME/.local/share/ai-lab}"
PROJECT="$(pwd)"
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

mkdir -p "$LAB/home" "$LAB/log"

# network: shared by default, dropped with AI_LAB_NO_NET=1
net=()
if [[ "${AI_LAB_NO_NET:-0}" != "1" ]]; then
  net=(--share-net)
fi

# seccomp: on by default, off with AI_LAB_SECCOMP=0
seccomp=()
filter=""
if [[ "${AI_LAB_SECCOMP:-1}" == "1" ]]; then
  if python3 -c 'import seccomp' 2>/dev/null; then
    filter="$LAB/seccomp.bpf"
    python3 "$SCRIPT_DIR/seccomp-deny.py" > "$filter"
    seccomp=(--seccomp 3)
  else
    printf 'ai-sandbox: python3-libseccomp missing, continuing without seccomp\n' >&2
  fi
fi

status=off
if [[ -n "$filter" ]]; then
  status=on
fi

# invocation log: when the wrapper ran, where, with what
printf '%s pid=%s cwd=%s seccomp=%s argv=%s\n' \
  "$(date -Is)" "$$" "$PROJECT" "$status" "$*" \
  >> "$LAB/log/invocations.log"

if [[ -n "$filter" ]]; then
  exec 3< "$filter"
fi

exec bwrap \
  --unshare-all --unshare-user "${net[@]}" \
  --ro-bind /usr /usr \
  --ro-bind-try /etc /etc \
  --symlink usr/bin /bin \
  --symlink usr/sbin /sbin \
  --symlink usr/lib /lib \
  --symlink usr/lib64 /lib64 \
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --dir /run \
  --bind "$LAB/home" "$HOME" \
  --ro-bind-try "$HOME/.local/bin" "$HOME/.local/bin" \
  --ro-bind-try "$HOME/.gitconfig" "$HOME/.gitconfig" \
  --bind "$PROJECT" "$PROJECT" \
  --chdir "$PROJECT" \
  --clearenv \
  --setenv HOME "$HOME" \
  --setenv PATH "$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" \
  --setenv TERM "${TERM:-xterm-256color}" \
  --setenv LANG "${LANG:-C.UTF-8}" \
  --new-session \
  --die-with-parent \
  --cap-drop ALL \
  --disable-userns \
  --assert-userns-disabled \
  --hostname ai-lab \
  "${seccomp[@]}" \
  "$@"
```

Notes:

- the `--ro-bind-try "$HOME/.local/bin"` line exposes agent binaries installed in your real home, read-only. Remove it if you install the agent inside the sandbox home instead
- `--seccomp 3` reads the filter from file descriptor 3, which the `exec 3< "$filter"` line opens just before the final `exec`
- if `python3-libseccomp` is not installed the wrapper prints a warning and runs without seccomp; the other layers still apply

Environment variables:

| Variable | Default | Effect |
|---|---|---|
| `AI_LAB_HOME` | `~/.local/share/ai-lab` | where the isolated home and logs live |
| `AI_LAB_NO_NET` | `0` | `1` drops the network namespace entirely |
| `AI_LAB_SECCOMP` | `1` | `0` disables the seccomp filter, for debugging |

## Lab 4: look around from inside

Save this as `~/.local/bin/ai-sandbox-shell`:

```bash
#!/usr/bin/env bash
exec "$(dirname "$(readlink -f "$0")")/ai-sandbox" bash
```

Then, from any project directory:

```sh
cd ~/code/my-project
ai-sandbox-shell
```

Try the same commands in two terminals, one sandboxed and one not:

```sh
ls ~/.ssh              # sandbox: No such file or directory, host: your keys
cat /etc/shadow        # sandbox: Permission denied
keyctl list @s         # sandbox: Operation not permitted (seccomp)
unshare --user echo nope   # sandbox: Operation not permitted
touch /usr/.probe      # sandbox: Read-only file system
```

The sandboxed prompt has a clean `$HOME`, so anything the agent writes there stays in the lab and persists between runs. Delete `~/.local/share/ai-lab/home` to reset it.

## Lab 5: prove the confinement

A sandbox you have not tested is a guess. This script runs probes through the wrapper and asserts each access denial. Save it as `~/.local/bin/ai-lab-test`:

```bash
#!/usr/bin/env bash
# ai-lab-test: assert that the sandbox confines what we claim it does.
# Exits non-zero if any probe leaks. Use --no-net-check for offline runs.
set -uo pipefail

SANDBOX="${AI_LAB_SANDBOX:-ai-sandbox}"
NET_CHECK=1
if [[ "${1:-}" == "--no-net-check" ]]; then
  NET_CHECK=0
fi

pass=0
fail=0

denied() {
  local desc="$1"; shift
  if "$SANDBOX" bash -c "$*" >/dev/null 2>&1; then
    printf 'FAIL  %s\n' "$desc"; fail=$((fail+1))
  else
    printf 'PASS  %s\n' "$desc"; pass=$((pass+1))
  fi
}

allowed() {
  local desc="$1"; shift
  if "$SANDBOX" bash -c "$*" >/dev/null 2>&1; then
    printf 'PASS  %s\n' "$desc"; pass=$((pass+1))
  else
    printf 'FAIL  %s\n' "$desc"; fail=$((fail+1))
  fi
}

printf '[filesystem confinement]\n'
denied  'host ~/.ssh is invisible'         'test -e "$HOME/.ssh"'
denied  'host ~/.gnupg is invisible'       'test -e "$HOME/.gnupg"'
denied  'host shell history is invisible'  'test -e "$HOME/.bash_history"'
denied  '/etc/shadow is not readable'      'test -r /etc/shadow'
denied  '/usr is read-only'                'touch /usr/.probe'
allowed 'sandbox HOME is writable'         'touch "$HOME/.probe" && rm -f "$HOME/.probe"'
allowed 'project dir is visible'           'test -d "$PWD"'

printf '[capability and namespace confinement]\n'
denied  'mount is denied'                  'mkdir -p /tmp/m && mount -t tmpfs none /tmp/m'
allowed 'effective capabilities are empty' 'grep -Eq "^CapEff:[[:space:]]+0+$" /proc/self/status'
allowed 'PID namespace is small'           'test "$(ls -d /proc/[0-9]* | wc -l)" -le 5'
allowed 'uid mapping is sane'              'id -u'

printf '[seccomp filter]\n'
if [[ "${AI_LAB_SECCOMP:-1}" == "1" ]]; then
  denied 'keyctl(2) denied' \
    'python3 -c "import ctypes,sys; l=ctypes.CDLL(None,use_errno=True); sys.exit(0 if l.keyctl(0,0,0,0,0)==0 else 1)"'
  denied 'ptrace(2) denied' \
    'python3 -c "import ctypes,sys; l=ctypes.CDLL(None,use_errno=True); sys.exit(0 if l.ptrace(0,0,0,0)==0 else 1)"'
else
  printf 'SKIP  seccomp disabled (AI_LAB_SECCOMP=0)\n'
fi

printf '[positive path]\n'
if [[ "$NET_CHECK" == "1" ]]; then
  allowed 'DNS works'          'getent hosts example.com'
  allowed 'outbound TCP works' 'timeout 5 bash -c "exec 3<>/dev/tcp/1.1.1.1/443"'
fi

printf '\n%d/%d probes passed, %d failed\n' "$pass" "$((pass+fail))" "$fail"
if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
```

Run it from a project directory:

```sh
cd ~/code/my-project
ai-lab-test
```

Sample output:

```
[filesystem confinement]
PASS  host ~/.ssh is invisible
PASS  host ~/.gnupg is invisible
PASS  host shell history is invisible
PASS  /etc/shadow is not readable
PASS  /usr is read-only
PASS  sandbox HOME is writable
PASS  project dir is visible
[capability and namespace confinement]
PASS  mount is denied
PASS  effective capabilities are empty
PASS  PID namespace is small
PASS  uid mapping is sane
[seccomp filter]
PASS  keyctl(2) denied
PASS  ptrace(2) denied
[positive path]
PASS  DNS works
PASS  outbound TCP works

15/15 probes passed, 0 failed
```

If a probe fails, run the wrapper with `AI_LAB_SECCOMP=0` to isolate whether seccomp is the cause, and re-read the flag list in Lab 2.

## Lab 6: seccomp deny-list

Namespaces and bind mounts decide what the sandbox can see. Seccomp decides which kernel entry points it can use. The filter below is a deny-list with a default of ALLOW, which keeps the sandbox usable while removing the syscalls that show up in exploit chains and in accidental self-harm.

Save it as `~/.local/bin/seccomp-deny.py`:

```python
#!/usr/bin/env python3
"""Emit a BPF seccomp deny-list to stdout. Default action: ALLOW."""
import sys

try:
    import seccomp
except ImportError:
    sys.stderr.write("python3-libseccomp is not installed\n")
    sys.exit(2)

# Syscalls denied outright, grouped by what they are abused for.
DENY = [
    # kernel keyring
    "keyctl", "add_key", "request_key",
    # exploit primitives
    "userfaultfd",
    # eBPF
    "bpf",
    # module loading
    "init_module", "finit_module", "delete_module",
    "create_module", "query_module", "get_kernel_syms",
    # kernel re-execution and power
    "kexec_load", "kexec_file_load", "reboot",
    # swap
    "swapon", "swapoff",
    # legacy I/O
    "iopl", "ioperm",
    # mount manipulation (namespaces already block these)
    "mount", "umount", "umount2", "pivot_root", "chroot",
    "move_mount", "open_tree", "mount_setattr",
    "fsmount", "fsopen", "fspick", "fsconfig",
    # hostname
    "sethostname", "setdomainname",
    # process introspection
    "ptrace", "process_vm_readv", "process_vm_writev",
    # perf, accounting, time, file handles, quota
    "perf_event_open", "acct",
    "clock_settime", "clock_adjtime", "settimeofday", "stime", "adjtimex",
    "name_to_handle_at", "open_by_handle_at",
    "quotactl", "quotactl_fd",
    # old and unused
    "sysfs", "_sysctl", "uselib", "ustat", "vm86", "vm86old",
    "nfsservctl", "kcmp", "lookup_dcookie",
]

EPERM = seccomp.ERRNO(1)
flt = seccomp.SyscallFilter(defaction=seccomp.ALLOW)

for name in DENY:
    try:
        flt.add_rule(EPERM, name)
    except RuntimeError:
        pass  # syscall does not exist on this architecture

# TIOCSTI: terminal keystroke injection
TIOCSTI = 0x5412
try:
    flt.add_rule(EPERM, "ioctl",
                 seccomp.Arg(1, seccomp.MASKED_EQ, 0xFFFFFFFF, TIOCSTI))
except RuntimeError:
    pass

# no nested user namespaces via clone or unshare
CLONE_NEWUSER = 0x10000000
for name in ("clone", "unshare"):
    try:
        flt.add_rule(EPERM, name,
                     seccomp.Arg(0, seccomp.MASKED_EQ, CLONE_NEWUSER, CLONE_NEWUSER))
    except RuntimeError:
        pass

flt.export_bpf(sys.stdout.buffer)
```

How it works:

- `MASKED_EQ` tests `(arg & mask) == value`, which is how we match the `CLONE_NEWUSER` flag inside the `clone` and `unshare` arguments
- unknown syscall names raise `RuntimeError`, which we swallow so the same script works on x86_64, aarch64, and others
- the filter is written as raw BPF to stdout and loaded by bwrap through `--seccomp 3`

Inspect it without running anything:

```sh
# write the compiled filter, then disassemble it
python3 ~/.local/bin/seccomp-deny.py > /tmp/filter.bpf
seccomp-tools disasm /tmp/filter.bpf
```

The generator writes only the BPF program to stdout, so any stderr you see is a real warning, not filter noise.

To debug a syscall that your agent genuinely needs, disable the filter for one run:

```sh
AI_LAB_SECCOMP=0 ai-sandbox-shell
```

## Lab 7: audit logging

There are two useful logs.

Wrapper-level: every sandboxed launch appends a line to `~/.local/share/ai-lab/log/invocations.log`. It records the timestamp, wrapper PID, working directory, whether seccomp was active, and the raw argv. Tail it to see what you have been running:

```sh
tail -f ~/.local/share/ai-lab/log/invocations.log
```

Agent-level: the wrapper records when you launched the agent, not what the agent did next. Most agent CLIs can run a hook before a tool call. Point that hook at a script inside the isolated home so the log stays in the sandbox:

```bash
#!/usr/bin/env bash
# log-agent-tool.sh: append one tool call as JSON to the sandbox log
printf '{"ts":"%s","tool":"%s","input":%s}\n' \
  "$(date -Is)" "$1" "${2:-null}" \
  >> "$HOME/.local/share/ai-lab/tool-calls.log"
```

Wire it into your agent's pre-tool hook, then watch it work:

```sh
tail -f ~/.local/share/ai-lab/home/.local/share/ai-lab/tool-calls.log
```

Auditing is also a good way to tighten the sandbox: run for a week, look at what the agent actually touched, then decide which bind mounts you can drop.

## Lab 8: control what the agent can reach

An agent needs a short list of hosts: the model API, a package registry, maybe a git host. Everything else is an exfiltration channel waiting for the wrong tool call. bubblewrap has no allowlist of its own, so the network story is built from three pieces you can combine.

### Level 1: no network at all

`--unshare-net` gives the sandbox an empty network namespace. There is no interface, no route, and no resolver:

```sh
bwrap --unshare-net --unshare-user \
  --ro-bind /usr /usr --symlink usr/lib64 /lib64 \
  --proc /proc --dev /dev \
  bash -c 'cat /proc/net/route; getent hosts example.com; echo "dns_exit=$?"'
```

Verified output:

```
Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask
dns_exit=2
```

The empty routing table is the answer, and `dns_exit=2` shows name resolution is gone too. A direct connect fails with `Network is unreachable`:

```
direct: OSError [Errno 101] Network is unreachable
```

This is the right default for a review agent or a build that has vendored its dependencies. It is useless for an agent that has to call a model API, so the next level matters.

### Level 2: one filtered channel out

Keep the network namespace empty and give the agent exactly one way out: a proxy on the host, exposed to the sandbox as a unix socket. A unix socket crosses the namespace boundary through the filesystem, not through the network, so it works even with no routes.

The proxy decides per host. Here is a complete one that allows a package registry and refuses everything else:

```python
#!/usr/bin/env python3
"""Host-side filtering proxy on a unix socket: only ALLOWED hosts pass."""
import http.server
import os
import select
import socket
import socketserver
import urllib.request

ALLOWED = {"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"}
SOCK = os.environ.get("AGENT_PROXY_SOCK", "/tmp/agent-proxy.sock")


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        host = self.path.split(":")[0]
        if host not in ALLOWED:
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            upstream = socket.create_connection((host, 443), timeout=10)
        except OSError:
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self._pipe(self.connection, upstream)

    def do_GET(self):
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ALLOWED:
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            with urllib.request.urlopen(self.path, timeout=10) as resp:
                body = resp.read()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def _pipe(self, a, b):
        socks = [a, b]
        while True:
            r, _, _ = select.select(socks, [], [], 30)
            if not r:
                break
            for s in r:
                other = b if s is a else a
                try:
                    data = s.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                other.sendall(data)


class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


if __name__ == "__main__":
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    UnixServer(SOCK, Handler).serve_forever()
```

Bind the socket into the sandbox:

```sh
bwrap --unshare-net --unshare-user \
  --ro-bind /usr /usr --symlink usr/lib64 /lib64 \
  --proc /proc --dev /dev \
  --bind /tmp/agent-proxy.sock /run/agent-proxy.sock \
  bash
```

Verified from inside a `--unshare-net` sandbox, talking to the socket directly:

```
allow-host: HTTP/1.1 200 OK
deny-host: HTTP/1.1 403 Forbidden
```

Three details decide whether this works in practice.

The socket must be bind-mounted read-write, because connecting to a unix socket needs write permission on the socket file. A read-only bind gives `EACCES`.

The proxy resolves names on the host, so the sandbox never needs DNS and cannot smuggle data out through queries.

And a unix socket is not something `HTTP_PROXY` can point at. Proxy environment variables carry a `host:port` URL, so tools that speak to a TCP proxy cannot use this socket directly. Python is the exception, with the `requests-unixsocket` package:

```python
import requests

session = requests.Session()
session.trust_env = False
session.proxies = {"https": "http+unix://%2Frun%2Fagent-proxy.sock"}
print(session.get("https://pypi.org/simple/", timeout=10).status_code)
```

If the agent's tooling is curl, pip, npm, or git, you want a TCP proxy instead, and then the filtering has to happen with host firewall rules rather than inside the namespace. Either way the sandbox still has no route of its own, so the allowlist is enforced in one place.

### Level 3: take the internet socket away

Proxy environment variables are a request, not a guarantee. A tool that ignores `HTTPS_PROXY`, or an agent that opens a raw socket, walks straight past the proxy. The durable version is to deny the syscalls that create internet sockets, so the proxy socket is the only channel that physically exists.

That is a seccomp rule on `socket(2)`, and it can be written without libseccomp by hand-rolling the BPF program. Save this as `mkfilter.py`:

```python
#!/usr/bin/env python3
"""Write a cBPF filter that denies socket(AF_INET) and socket(AF_INET6).

No libseccomp needed. The result is loaded by bubblewrap with --seccomp.
"""
import struct
import sys

BPF_LD_W_ABS = 0x20
BPF_JEQ_K = 0x15
BPF_RET_K = 0x06

AUDIT_ARCH_X86_64 = 0xC000003E
SYS_SOCKET = 41
AF_INET = 2
AF_INET6 = 10
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000 | 1  # EPERM

# (code, jt, jf, k). Jump offsets are relative to the next instruction.
PROGRAM = [
    (BPF_LD_W_ABS, 0, 0, 4),              # 0: load arch
    (BPF_JEQ_K, 0, 5, AUDIT_ARCH_X86_64),  # 1: not x86_64 -> deny
    (BPF_LD_W_ABS, 0, 0, 0),               # 2: load syscall number
    (BPF_JEQ_K, 0, 4, SYS_SOCKET),         # 3: not socket -> allow
    (BPF_LD_W_ABS, 0, 0, 16),              # 4: load args[0], the address family
    (BPF_JEQ_K, 1, 0, AF_INET),            # 5: AF_INET -> deny
    (BPF_JEQ_K, 0, 1, AF_INET6),           # 6: AF_INET6 -> deny
    (BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO),  # 7: deny
    (BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW),  # 8: allow
]


def main() -> None:
    out = bytearray()
    for code, jt, jf, k in PROGRAM:
        out += struct.pack("HBBI", code, jt, jf, k)
    with open(sys.argv[1], "wb") as fh:
        fh.write(out)
    print(f"wrote {len(out)} bytes to {sys.argv[1]}")


if __name__ == "__main__":
    main()
```

Build it and load it:

```sh
python3 mkfilter.py /run/user/1000/inet.bpf

bwrap --unshare-user \
  --ro-bind /usr /usr --symlink usr/lib64 /lib64 \
  --proc /proc --dev /dev \
  --seccomp 3 3< /run/user/1000/inet.bpf \
  bash
```

The `3<` redirection opens the filter on file descriptor 3, and `--seccomp 3` tells bubblewrap to read it from there. Verified from inside:

```
inet : blocked 1 Operation not permitted
inet6 : blocked 1 Operation not permitted
unix : CREATED
```

That is the shape you want for an agent that still needs a local MCP server: the unix socket keeps working, and every internet socket returns `EPERM` before a packet is sent.

If you prefer libseccomp, the same rule in the generator style of Lab 6 is `Arg(0, seccomp.EQ, AF_INET)` and `Arg(0, seccomp.EQ, AF_INET6)` on the `socket` syscall. The hand-rolled version above needs no packages, which matters on a minimal host.

### What the agent still cannot do

Levels 1 to 3 cover the network, and the network is where exfiltration goes. Two channels stay open on purpose, because an agent needs them:

- **The model API.** That is usually the one host you cannot block. Give it the narrowest possible scope, and remember that anything the agent can read can be sent there.
- **Your MCP servers.** Run them over a unix socket inside the sandbox, so the seccomp rule above does not break them.

## Threat model worksheet

Write this down for your own deployment and check it against reality. A sandbox is only as good as the assumptions behind it.

| Threat | Covered by |
|---|---|
| Prompt injection runs destructive commands | bounded to the project dir and the isolated home |
| Exfiltration of unrelated secrets (SSH, GPG, browser, password store) | those paths are not in the sandbox view |
| Cross-project contamination | only the launch directory is bound |
| Kernel exploit chains needing rare syscalls | seccomp deny-list (`userfaultfd`, `bpf`, `keyctl`, `perf_event_open`) |
| TIOCSTI keystroke injection | `--new-session` plus the `ioctl` rule |
| Module loading, mount manipulation, kernel re-execution | namespaces plus the seccomp deny-list |
| Exfiltration to a host you did not intend to allow | the filtering proxy, or the socket-family seccomp rule |
| Data smuggled out through DNS lookups | no resolver in the sandbox, the proxy resolves on the host |
| Reaching the metadata service or private networks | empty network namespace plus a deny-by-default proxy |

| Not covered | Why |
|---|---|
| Network exfiltration of project files | the agent needs the network by default. Use `AI_LAB_NO_NET=1` for strict offline runs |
| Sending secrets through an allowed host | an allowlisted host can still be used to exfiltrate |
| A tool that ignores proxy variables | only the socket-family seccomp rule closes this, and it breaks tools that need the internet |
| Kernel exploits using only allowed syscalls | a deny-list cannot remove unknown bugs |
| Side channels against other host processes | out of scope for a namespace-based sandbox |
| A malicious MCP server or plugin | it runs inside the sandbox and inherits exactly this policy, no more and no less |

## Gotchas

1. Agent auto-update fails silently. The binary is on a read-only mount. Update it outside the sandbox.
2. MCP servers and plugins run inside the sandbox. They share its filesystem view, capabilities, and seccomp filter. If one needs a path outside the project, add it with an extra `--ro-bind-try`.
3. `sudo`, `su`, and `pkexec` do not work. The user namespace maps only your UID. This is intentional.
4. Job control can surprise you. `--new-session` calls `setsid()`, so `Ctrl-Z`, `bg`, and `fg` may behave differently. That is the trade-off for TIOCSTI protection.
5. `strace`, `gdb`, and `perf` fail inside the sandbox because `ptrace` and `perf_event_open` are denied. Use `AI_LAB_SECCOMP=0` when you need them.
6. Files outside the project directory are invisible to the agent. Bind specific paths, or launch from a parent directory.
7. Credential caches need care. Anything the agent stores in its isolated `$HOME` is separate from your real one, so you log in again once per sandbox. That is by design.
8. `/dev` is fresh, not shared. GPU access and similar device integrations are unavailable.
9. `clone3` cannot be inspected by BPF, so the filter targets `clone` and `unshare` instead. `--disable-userns` is what actually prevents nested user namespaces regardless of how they are requested.
10. `--clearenv` must come before `--setenv`, otherwise you clear the variables you just set.
11. bubblewrap has no host allowlist. Filtering is a proxy or a firewall job, and the sandbox has no opinion about which host is fine.
12. A bind-mounted unix socket must be read-write. Connecting needs write permission on the socket file, and a read-only bind fails with `EACCES`.
13. Proxy environment variables do not stop a tool that ignores them. The socket-family seccomp rule does, at the cost of every internet tool in the sandbox.
14. The hand-rolled BPF filter in Lab 8 is x86_64 only, because it checks the audit architecture. On other architectures, build the equivalent with libseccomp.

## Ecosystem

Ready-made tools built on the same primitives, useful as reference or as a shortcut:

| Project | What it is |
|---|---|
| [bubblewrap](https://github.com/containers/bubblewrap) | the sandbox builder this lab is built on |
| [bubblewrap-tui](https://github.com/reubenfirmin/bubblewrap-tui) | a terminal UI that generates `bwrap` commands, with optional network filtering via pasta |
| [bubblejail](https://github.com/igo95862/bubblejail) | a bubblewrap-based alternative to Firejail, built around per-application home directories |
| [bubblewrap-ai](https://github.com/umago/bubblewrap-ai) | a small wrapper for AI coding agents: read-only host filesystem, clean environment, whitelisted dotfiles |

## Cleanup

```sh
rm ~/.local/bin/ai-sandbox ~/.local/bin/ai-sandbox-shell
rm ~/.local/bin/seccomp-deny.py ~/.local/bin/ai-lab-test
rm -rf ~/.local/share/ai-lab
```

## Next steps

- wrap the wrapper: put `ai-sandbox` in front of every agent you start, not just the risky ones
- add a second layer for network control, for example a filtered proxy or a network namespace with only a loopback device
- turn the probe list in Lab 5 into a CI job, so a flag change that weakens the sandbox fails the build
