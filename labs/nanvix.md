# AI Sandbox Demo Lab: Nanvix

A hands-on lab for Nanvix, a purpose-built microVM with a purpose-built operating system inside it. Not a Linux VM, not a container, and not a namespace sandbox: a different kernel and a different OS, running your Python workload behind a hardware boundary.

Everything in the "Verified output" blocks was produced on this machine, on Linux, with KVM, using the pinned `nanvix-python` bundle from the upstream release. Nanvix is the **microVM approach**, the same family as [microsandbox](microsandbox.md) and [Docker Sandboxes](dockersandboxes.md), but with a guest operating system that is not Linux: the guest kernel is Nanvix's own microkernel, and that is the whole point. [bubblewrap](bubblewrap.md) covers the cheaper namespace approach, and [MXC](mxc.md) covers the policy layer that can drive Nanvix as a backend.

## What Nanvix is

Nanvix is two things at once, and the second one is the interesting one.

- **A microVM.** Each workload runs in its own lightweight virtual machine, with its own guest kernel and a hardware-enforced boundary from the host.
- **A multikernel OS.** The guest kernel is a *micro-kernel* that implements threads and memory and forwards every I/O request. The device drivers live in a *macro-kernel* in a separate system VM, shared by all the invocations of one tenant.

The split is the whole idea. The micro-kernel stays tiny and is easy to verify, while the expensive part (drivers, filesystems, networking) is written once and shared. The paper calls this disaggregating ephemeral execution state from long-lived persistent state.

The cost is a communication channel. The micro-kernel in the user VM talks to the macro-kernel in the system VM over **IKC**, inter-kernel communication, with a host-side worker doing the actual I/O on the host filesystem. You can see that worker in action in Lab 5.

The micro-VM itself is deliberately bare: a virtual processor and memory, and no device emulation at all. Everything a device would normally do is a software switch in the macro-kernel, reachable over IKC. That is what keeps the start-up cost low, and it is also why the guest has no `/dev` beyond three console-ish nodes.

From the paper, *Nanvix: A Multikernel OS Design for High-Density Serverless Deployments* (arXiv:2604.11669, Carlos Segarra, Pedro Henrique Penna, Enrique Saurez, Inigo Goiri, Peter Pietzuch, Shan Lu, and Rodrigo Fonseca): order-of-magnitude lower application start-up times, and 20 to 100 times fewer host servers on a production trace.

Upstream's own comparison puts the numbers next to the alternatives:

| Feature | Nanvix | Unikraft | Firecracker | gVisor | Docker | WebAssembly |
|---|---|---|---|---|---|---|
| Flexible component placement | yes | no | no | no | no | no |
| Multiple guest processes | yes | no | yes | yes | yes | no |
| Hardware isolation | yes | yes | yes | no | no | no |
| Startup time | ~30ms | ~320ms | ~70ms | ~160ms | ~1s | ~1ms |
| Memory footprint | ~10MB | ~10MB | 10 to 100MB | 10 to 50MB | ~100MB | ~1MB |
| Deployment density | ~10k | ~1k | ~1k | ~1k | ~100 | ~10k |
| Full Linux compatibility | no | no | yes | yes | yes | no |

Their startup number is a p50 to the first HTTP echo response, measured with snapshot restore, the production serverless configuration. The 0.2 seconds you will measure in Lab 2 is the cold boot, and on Linux there is no snapshot path to make it warm.

Nanvix is MIT licensed and lives at [github.com/nanvix/nanvix](https://github.com/nanvix/nanvix). The Python distribution is a separate repo, [github.com/nanvix/nanvix-python](https://github.com/nanvix/nanvix-python), and the applications that have already been ported are catalogued in [github.com/nanvix/catalog](https://github.com/nanvix/catalog).

### It is not Linux

This is the part that changes how you plan around it.

The guest implements a POSIX API with around 150 syscalls, and it calls itself `nanvix`:

```
uname: posix.uname_result(sysname='nanvix', nodename='localhost', release='0', version='24', machine='microvm')
```

There is no Linux kernel, no `fork`, no `epoll`, no `/proc`, no `apt`. CPython is ported to run on it, which is why the Python distribution exists. But a binary that wants `io_uring`, a C library with Linux-specific syscalls, or a container image will not run here.

The practical rule: Nanvix is a good host for pure-Python workloads and a bad host for anything that expects a Linux userland.

### There is no package for it

No conda-forge package. No PyPI package. The host interface is the `nanvixd` binary, and there is no host-side Python SDK to add to `pixi.toml`. The distribution is a release artifact, and that artifact is what this lab pins and verifies.

## Requirements

- Linux with KVM, and read and write access to `/dev/kvm`
- About 560 MB of disk for the extracted bundle, and 130 MB for the download
- Nothing else. The guest binary is static, and the host tool is a single static ELF

Check the host:

```sh
ls -l /dev/kvm
```

## Lab 1: fetch the bundle with a pinned digest

The fetch script pins the release tag and the sha256 of the asset, verifies it, and is idempotent:

```sh
pixi run nanvix-fetch
```

Verified output on this machine:

```
downloading nanvix-python-linux-x86-microvm-standalone-256mb.tar.gz
digest ok: /home/roro/Workspaces/inside-cottonbox-cc/scratch/nanvix-python/nanvix-python-linux-x86-microvm-standalone-256mb.tar.gz
downloading nanvix.lock
digest ok: /home/roro/Workspaces/inside-cottonbox-cc/scratch/nanvix-python/nanvix.lock
downloading sdk-provenance.json
digest ok: /home/roro/Workspaces/inside-cottonbox-cc/scratch/nanvix-python/sdk-provenance.json
bundle ready: /home/roro/Workspaces/inside-cottonbox-cc/scratch/nanvix-python/3.12.3-nanvix-0.24.46-sdk.1-11739bd
```

Run it a second time and it does nothing:

```
bundle already present: /home/roro/Workspaces/inside-cottonbox-cc/scratch/nanvix-python/3.12.3-nanvix-0.24.46-sdk.1-11739bd
```

The pinning is the point. The release tag is `3.12.3-nanvix-0.24.46-sdk.1-11739bd` and the digest is fixed in `scripts/nanvix-fetch.sh`:

```sh
NANVIX_TAG="3.12.3-nanvix-0.24.46-sdk.1-11739bd"
NANVIX_ASSET="nanvix-python-linux-x86-microvm-standalone-256mb.tar.gz"
NANVIX_SHA256="be9d14786c76bc99cc81c66b0d8aa6c8912cea252ab91941848b5ad3badaa259"
```

The release also ships a `nanvix.lock` and a `sdk-provenance.json`, and the script verifies both. The provenance record is the interesting one, because it says what the guest was actually built from:

```json
{
  "c_abi": "i686-nanvix-sysv-1",
  "package_name": "nanvix-python",
  "package_version": "3.12.3",
  "provider_id": "c-clang",
  "sdk_version": "v0.24.46-sdk.1",
  "source_commit": "11739bd99b08a2556d393b38938f49e341bd2ed0",
  "sysroot_sha256": "4545ea5c5f84e0405877df78e6ac3a95a1cd5622d758faabb7d5b31ca03a6d36"
}
```

That is a supply chain trail from the tarball you run back to the Nanvix commit and the Clang 22.1.8 toolchain image it was built with. Compare that with "pip install something" and think about which one you would want running model output.

Where the bundle lands matters. `$SCRATCH` is a directory on disk, not the tmpfs, because the extracted bundle is about 560 MB and `$TMPDIR` here is a 3 GB tmpfs. Scratch is disposable: delete it and the next fetch re-downloads and re-verifies.

### Why not the upstream script

The [nanvix-python repo](https://github.com/nanvix/nanvix-python) ships its own downloader, `scripts/get-nanvix-python.sh`, and its own quick start:

```sh
gh release download --repo nanvix/nanvix-python --pattern "*.tar.gz" --clobber
tar -xzf microvm-standalone-256mb.tar.gz
cd microvm-standalone-256mb
./bin/nanvixd.elf -ramfs nanvix_rootfs.img -mount ./mnt -- python3.initrd
```

That is the supported path and it works. This lab uses its own fetch script for one reason: the upstream one resolves the **latest** release through the GitHub API and verifies **no digest**, so "run this twice" does not give you the same bytes. Ours pins the tag and the sha256 of all three published assets, which is what you want when the thing being run is model output.

The repo can also build the runtime from source, through the `./z` wrapper:

```sh
git clone --recurse-submodules https://github.com/nanvix/nanvix-python.git
cd nanvix-python
./z setup     # fetch the runtime-only sysroot and the SDK-built CPython
./z build     # install the pure Python packages, generate the ramfs
./z release   # package the standalone bundle into dist/
```

Its prerequisites are Python 3.12 on the host, Docker for the SDK-hosted bytecode generation, and KVM. Notably **no root**: unlike the core `nanvix/nanvix` repo, which builds a kernel and a system toolchain and does need sudo, this one only assembles a Python distribution. `./z` bootstraps `nanvix-zutil` into a private virtualenv if it is not already on PATH, and it uses a global install when the version matches the pin in `.zutils-version`. Since `nanvix-zutil` is published as a GitHub wheel rather than on PyPI or conda-forge, a pixi environment can still take it with a direct URL:

```toml
[pypi-dependencies]
nanvix-zutil = { url = "https://github.com/nanvix/zutils/releases/download/v0.24.0/nanvix_zutil-0.24.0-py3-none-any.whl" }
```

The build also wants `pip` in the environment that runs it, because the package install step shells out to `python -m pip install --target=...` for the pure Python packages.

## Lab 2: boot the guest

The bundle has five things in it:

```
bin/kernel.elf         the guest micro-kernel
bin/nanvixd.elf        the host-side hypervisor
nanvix_rootfs.img      a RAM filesystem with the CPython standard library
python3.initrd         the initrd that boots the runtime
mnt/                   where your workload goes
```

The run script wires them together. It copies your workload into `mnt/` and starts the hypervisor:

```sh
pixi run nanvix /tmp/hello.py
```

with a workload of:

```python
import os
import sys

print("hello from the nanvix guest")
print("uname:", os.uname())
print("python:", sys.version.split()[0])
```

Verified output:

```
[ERROR][dispatcher] do_kcall(): snapshot refused: not enabled or already consumed
hello from the nanvix guest
uname: posix.uname_result(sysname='nanvix', nodename='localhost', release='0', version='24', machine='microvm')
python: 3.12.3
```

Two things in that output deserve attention.

The first line is an error, and it is harmless. The guest asks the hypervisor for a VM snapshot at the end of the run, snapshots are a Windows-only feature, and the host refuses. The refusal is reported on the host's stderr and the run continues normally. Expect it every time on Linux.

The rest is the payload. `machine='microvm'` is the guest telling you it is running on virtual hardware, and `sysname='nanvix'` is the OS telling you it is not Linux.

The cold boot here took **0.2 seconds**:

```
real	0m0,199s
user	0m0,126s
sys	0m0,059s
```

Upstream quotes about 2 seconds on their CI hardware. Snapshots exist to skip the cold boot, but they are Windows and WHP only, and they are tied to the host CPU, so on Linux you always pay the cold boot. At a fifth of a second, that is not the interesting number.

## Lab 3: the workload dispatch protocol

The guest looks for a workload in a fixed order, and knowing the order is the whole API.

1. `mnt/bootstrap.py` is executed directly if it is there.
2. Otherwise `mnt/argv.txt` is read: one argument per line, supporting `-m module` syntax or a path to a script inside `/mnt`.
3. Otherwise you land in an interactive REPL.

### Mode 1: bootstrap.py

That is the mode the run script uses. Any file works, and the guest sees it at `/mnt/bootstrap.py`:

```python
import os

print("argv:", os.sys.argv)
print("cwd:", os.getcwd())
```

### Mode 2: argv.txt

`argv.txt` is one argument per line. The script path has to be the path **inside the guest**, not the host path:

```
/mnt/script.py
--flag
value
```

Verified output:

```
hello from an argv.txt script
argv: ['/mnt/script.py', '--flag', 'value']
cwd: /
mnt: ['argv.txt', 'bootstrap.py', 'script.py']
```

The extra lines become `sys.argv`, so your workload gets its arguments the ordinary way.

The `-m` form works too. Two lines, `-m` and then the module name:

```
-m
this
```

Verified output:

```
The Zen of Python, by Tim Peters

Beautiful is better than ugly.
Explicit is better than implicit.
...
```

One trap here. A bare relative path does not resolve:

```
FileNotFoundError: [Errno 2] No such file or directory: 'script.py'
```

The guest's working directory is `/`, and it does not look in `/mnt` for you. Use `/mnt/script.py`.

### Mode 3: the REPL

With neither file present, the guest drops into a real CPython REPL:

```sh
pixi run nanvix-shell
```

Verified output:

```
Python 3.12.3 (main, Sep 25 2026, 18:11:18) [Clang 22.1.8 ] on nanvix
Type "help", "copyright", "credits" or "license" for more information.
(InteractiveConsole)
>>> print("hello from the nanvix repl")
hello from the nanvix repl
>>> >>> version: 3.12.3 (main, Sep 25 2026, 18:11:18) [Clang 22.1.8 ]
>>>
```

Note the banner: `on nanvix`. That is CPython reporting its platform, and it is the clearest single line in the whole lab that this is not Linux.

## Lab 4: what the guest can see of the host

This is the security question that matters, so measure it rather than assume it.

```python
import os

for path in ("/home", "/proc", "/tmp", "/etc", "/usr", "/root"):
    try:
        print(path, "->", sorted(os.listdir(path))[:6])
    except OSError as error:
        print(path, "-> error", error.errno, error.strerror)
```

Verified output:

```
/home -> error 2 No such file or directory
/proc -> error 2 No such file or directory
/tmp -> error 2 No such file or directory
/etc -> error 2 No such file or directory
/usr -> error 2 No such file or directory
/root -> error 2 No such file or directory
```

Nothing. Not "denied", not "empty", **absent**. The guest root filesystem has three entries:

```
/ -> ['dev', 'lib', 'sysroot']
/dev -> ['console', 'null', 'tty']
/lib -> ['libc.so', 'libm.so']
```

That is the whole guest userland: a device node set, the C library, and the CPython sysroot. No `/proc`, no `/tmp`, no `/etc`, no package manager, no shell binaries. A guest that wants `/bin/ls` does not get one:

```
subprocess -> error FileNotFoundError [Errno 2] No such file or directory: '/bin/ls'
```

The guest's `pid` was 4, inside its own PID namespace, and its cwd is `/`. It is a runtime for one program, not a machine you log into.

## Lab 5: the live host mount

The bundle's `mnt/` directory is the escape hatch, and it is worth understanding because it is unusual.

When you pass `-mount ./mnt`, the host directory appears at `/mnt` inside the guest. But it is not copied in. It is **live**: every guest file operation is forwarded over IKC to a host-side worker that performs the real I/O.

```python
with open("/mnt/live.txt", "w") as handle:
    handle.write("written by the guest")

print(sorted(os.listdir("/mnt")))
```

Verified output:

```
=== live host mount ===
wrote /mnt/live.txt
=== host sees it immediately ===
['bootstrap.py', 'live.txt', 'script.py']
```

And on the host, with no VM shutdown and no copy-back step:

```
-rw-rw-rw- 1 roro roro 20 Oct 20 09:57 live.txt
```

The file is there the moment the guest wrote it. If the VM is killed, the file is still there, because it was never in the VM.

### The path sandbox

A live mount into the host filesystem is exactly the kind of thing that turns into a sandbox escape, so upstream puts a path sandbox in front of it: paths are canonicalised, and anything that resolves outside the mount root is rejected.

```python
for path in ("/mnt/../../etc/passwd", "/mnt/../nanvix_rootfs.img", "/mnt/sub/../../escape.txt"):
    try:
        with open(path) as handle:
            print(path, "-> READ", handle.read()[:40])
    except OSError as error:
        print(path, "-> error", error.errno, error.strerror)
```

Verified output:

```
/mnt/../../etc/passwd -> error 2 No such file or directory
/mnt/../nanvix_rootfs.img -> error 13 Permission denied
/mnt/sub/../../escape.txt -> error 2 No such file or directory
```

The `..` sequences are resolved and then clamped, so they land inside the mount root or nowhere. The second line is the one to look at: escaping to a file that really does exist on the host, one level up, gives `Permission denied` rather than a leak.

Two more limits from the upstream design, which I did not try to break but which you should know before you rely on them: `symlink()` is not supported on mounted paths, and `chmod` is not forwarded, so host permissions are simply the permissions of the `nanvixd` process.

## Lab 6: networking is off by default

The guest's network syscalls are blocked. Not firewalled, blocked at the syscall:

```python
import socket

connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
```

Verified output:

```
socket -> error OSError [Errno 134] Operation not supported
```

Errno 134 is Nanvix's "operation not supported", and it arrives at socket creation, so nothing is ever attempted. This is the strongest default in the whole series: there is no interface, no route, and no resolver inside the guest.

To open the gate, `nanvixd` has a flag:

```sh
./bin/nanvixd.elf -allow-host-networking -ramfs nanvix_rootfs.img -mount ./mnt -- python3.initrd
```

Verified output with the flag:

```
tcp socket created: <socket.socket fd=3, family=2, type=1, proto=0, laddr=('0.0.0.0', 0)>
tcp -> error OSError [Errno 9] Bad file descriptor
dns -> error gaierror [Errno -2] None
```

So the flag does lift the syscall gate, the socket is created, and then the connection does not complete. Name resolution fails as well.

The reason is the shape of the system: the network stack is not a kernel syscall, it is the macro-kernel's job, and the macro-kernel side of the network is not part of this runtime-only bundle. The upstream documentation pairs `-allow-host-networking` with the full Nanvix system image, where the network daemons are present.

Treat this as the honest result: with the Python runtime bundle, the guest has no usable network, and the flag is a demonstration that the gate is a flag rather than a property of the architecture.

## Lab 7: the same bundle as a service

`nanvixd` has a second mode. Instead of running one program and exiting, it becomes a REST server that spawns and kills guests on demand.

```sh
./bin/nanvixd.elf -http-addr 127.0.0.1:8099 -ramfs nanvix_rootfs.img -mount ./mnt
```

Spawning an application:

```sh
curl --silent \
    --header "Content-Type: application/json" \
    --header "X-NVX-Message-Type: NEW" \
    --request POST \
    --data '{"tenant_id":"lab","app_name":"hello","program":"python3.initrd","program_args":""}' \
    http://127.0.0.1:8099
```

Verified output:

```
{"user_vm_id":{"value":1},"gateway_sockaddr":"/tmp/nvx-standalone-gw-1545922.sock"}
```

The response gives you a guest identifier and a Unix socket that carries that guest's stdin and stdout. Talking to it over that socket:

```
guest banner: nanvix python is up
uname: nanvix
socket -> error OSError [Errno 134] Operation not supported
waiting for commands on stdin
2+2
eval: 4
```

And killing it:

```sh
curl --silent \
    --header "Content-Type: application/json" \
    --header "X-NVX-Message-Type: KILL" \
    --request POST \
    --data '{"user_vm_id":{"value":1}}' \
    http://127.0.0.1:8099
```

```
{"exit_code":0}
```

Two details worth knowing. The identifier is a tagged object, so `{"user_vm_id":1}` is rejected with `INVALID_KILL_PAYLOAD` and `{"user_vm_id":{"value":1}}` is the shape that works. And in standalone mode only one guest runs at a time: a second `NEW` while one is alive comes back as `NEW_REQUEST_FAILED` with "a VM is already running in standalone mode".

This mode is the interesting one for an agent fleet, because the hypervisor becomes a service and the guest becomes a disposable resource. The paper's claim about deployment density lives here.

## How Nanvix compares

| | bubblewrap | microsandbox | Docker Sandboxes | MXC | Nanvix |
|---|---|---|---|---|---|
| Approach | namespaces on the host kernel | microVM, Linux guest | microVM, Linux guest | the policy layer over engines | microVM, own guest OS |
| Role | the engine | the engine | the managed service | the wrapper over engines | the engine, with its own OS |
| Boundary | namespaces on the host kernel | own guest kernel | own guest kernel | whatever the host offers | own guest kernel, own OS |
| Guest userland | the host's | Linux | Linux | depends on the backend | **Nanvix, not Linux** |
| Start cost | milliseconds | tens to hundreds of ms | seconds | ms on bubblewrap, more on a VM backend | 0.2 s cold boot here |
| Network control | you build the filter | domain and group rules | preset plus scope rules | CIDR rules, or a proxy | syscalls blocked by default |
| Host filesystem | you bind paths | bind mounts | workspace modes | path policy | live mount, path sandboxed |
| Languages | any | Python, TS, Rust, Go, Ruby | the `sbx` CLI | Rust, .NET, Node | CPython 3.12, pure Python packages |
| Snapshots | no | yes | no | no | Windows and WHP only |
| Best at | the cheapest boundary | running untrusted code end to end | unattended agent fleets | one policy across hosts and engines | a guest OS you control, at serverless density |

The interesting row is the second one. Nanvix, microsandbox, and Docker Sandboxes all give the workload its own guest kernel, so they are one approach, not three. What separates Nanvix is the row under it: every other project in this series runs your code on Linux, which means your code has to be Linux code. Nanvix runs it on something else entirely, and the cost is that porting is on you.

The interesting row is also the fourth. Nanvix's network default is "the syscall is not implemented", which is stronger than any firewall you can configure on top of a Linux guest, because there is no layer to configure.

## Threat model worksheet

| Threat | Covered by |
|---|---|
| The workload reads host files | the guest root filesystem has three entries, and the host is not visible at all |
| The workload escapes the mounted directory | the hostfsd path sandbox canonicalises and rejects anything outside the root |
| The workload phones home | the network syscalls are blocked at creation, errno 134 |
| The workload reads the host kernel | it is a VM guest with its own kernel, and the micro-kernel forwards I/O rather than implementing devices |
| The workload tampers with the host filesystem | the mount is read and write by design, so give it a directory that contains nothing you care about |
| The workload survives the VM | the host owns the hypervisor; the guest cannot reach the host process that holds it |
| The workload tampers with the runtime | the rootfs is a RAM image supplied at boot, and it is read-only from the guest's point of view |

| Not covered | Why |
|---|---|
| A bug in the host-side mount worker | hostfsd runs on the host with the host's privileges; it is the trusted half of the system |
| A bug in the micro-kernel or the macro-kernel | a hypervisor escape in the guest kernel would break the whole model |
| Writes to the mount root | the guest can write wherever the mount points, with the host process's permissions |
| The snapshot path | snapshots are Windows only, so on Linux there is no warm-start path to attack or to trust |
| The host kernel | KVM is the host kernel, so a host kernel bug is still in scope |
| A C extension in the guest | CPython here is a port; a package that needs a native extension needs a Nanvix port of that extension |

## Gotchas

1. **It is not Linux.** `sysname='nanvix'`, no `/proc`, no `/etc`, no `/tmp`, no shell binaries. CPython is ported; your stack may not be.
2. **The `snapshot refused` line is not a failure.** The guest asks for a snapshot at the end of every run, snapshots are Windows only, and the host refuses. The run is fine.
3. **`argv.txt` needs the guest path.** `script.py` fails, `/mnt/script.py` works. The guest's cwd is `/` and it does not search `/mnt`.
4. **`argv.txt` is one argument per line, not a shell command line.** `-c` on its own line does not run a one-liner; the guest tries to open a file called `-c`.
5. **The mount is live, not copied.** A guest write appears on the host immediately, and survives a VM kill. Treat the mount root as shared writable state.
6. **The mount root is the sandbox.** Mount a directory that contains nothing sensitive, because the guest has the host process's permissions inside it.
7. **No `symlink()` and no `chmod` on mounted paths.** The guest cannot create a symlink out of the mount, and it cannot change permissions either.
8. **Networking needs a flag, and the flag is not enough here.** `-allow-host-networking` lifts the syscall gate, but the runtime-only bundle has no network stack behind it, so connections still fail.
9. **Only one guest at a time in standalone mode.** A second `NEW` over HTTP is refused while one is running.
10. **The HTTP identifier is a tagged object.** `{"user_vm_id":{"value":1}}`, not `{"user_vm_id":1}`.
11. **The bundle is about 560 MB extracted and 130 MB compressed.** It belongs on disk, not in a tmpfs.
12. **Building from source does not need root, but it does need Docker and pip.** The `nanvix-python` build pulls the SDK toolchain image and shells out to `python -m pip install` for the pure Python packages, so the environment running `./z` needs pip. It is the core `nanvix` repo, which builds a kernel and a system toolchain, that needs sudo.
13. **Upstream CI is the reference for portability.** Their bundle targets Ubuntu 24.04; this run was on Ubuntu 26.04 with kernel 7.0.0-38-generic and worked, but a kernel change can break a microVM boot in ways a namespace sandbox cannot.
14. **The runtime has no conda-forge or PyPI package.** Nothing to add to `pixi.toml` for the runtime itself, and nothing for a host-side script to import. The `nanvixd` binary is the interface. Only the build tooling is a package, and only as a GitHub wheel.

## Ecosystem

| Resource | What it is |
|---|---|
| [nanvix/nanvix](https://github.com/nanvix/nanvix) | the microkernel, the macrokernel, and the host tooling |
| [nanvix/nanvix-python](https://github.com/nanvix/nanvix-python) | the CPython 3.12 distribution this lab uses, and the repo the bundle is released from |
| [the upstream downloader](https://github.com/nanvix/nanvix-python/blob/main/scripts/get-nanvix-python.sh) | the supported "grab the latest release" script, and what this lab's fetch script deviates from |
| [the paper](https://arxiv.org/abs/2604.11669) | the multikernel design and the density numbers |
| [running Nanvix on Linux](https://github.com/nanvix/nanvix/blob/dev/doc/run-linux.md) | the `nanvixd` flags, the HTTP API, and the kernel arguments |
| [the host mount design](https://github.com/nanvix/nanvix/blob/dev/doc/host-mount.md) | the hostfsd protocol, the path sandbox, and the supported operations |
| [supported Python packages](https://github.com/nanvix/nanvix-python/blob/main/doc/packages.md) | the full list of what is preinstalled |
| [nanvix/catalog](https://github.com/nanvix/catalog) | the applications already ported to the Nanvix toolchain |
| [the MXC lab](mxc.md) | driving Nanvix as the experimental `microvm` backend |

### Nanvix inside MXC

The [MXC lab](mxc.md) covers the wrapper framework. Its `microvm` backend is this same Nanvix, packaged for a sandbox SDK. The upstream docs mark it experimental, and the shape differs from what you just ran:

- It needs the `microvm` cargo feature and the experimental flag, which is an API parameter rather than a config file setting.
- The guest gets 256 MB, the same as this bundle.
- Host paths are **copied** into a private staging directory and copied back after a normal exit. That is a snapshot-style mount, not the live mount you saw in Lab 5.
- `denied_paths` is not supported, symlinks are rejected, and `workingDirectory` is not supported.
- Networking is all or nothing: the egress default, the ingress default, and host loopback must agree, or the request is refused. With networking off, guest socket creation fails with `OSError: [Errno 134]`, the same errno you saw in Lab 6.

## Cleanup

Everything is in scratch:

```sh
rm -rf scratch/nanvix-python
```

The next `pixi run nanvix-fetch` re-downloads and re-verifies it.

## Where this goes next

- Try the `nanvix-python` package set against a real workload. The preinstalled pure-Python set is wide enough for most agent tooling, and it is the cheapest way to find out whether your stack needs Linux.
- Put a workload behind the HTTP mode and measure the start-up cost yourself. The paper's density claim is about exactly this loop.
- Read the host mount design document next to Lab 5. It is the part of the system where a mistake becomes a host compromise.
- Pair this with the [MXC lab](mxc.md): Nanvix when the workload needs its own kernel, bubblewrap when it does not, and one policy model either way.
