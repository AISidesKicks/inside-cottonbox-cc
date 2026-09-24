# AI Sandbox Demo Lab: microsandbox

A hands-on lab for running AI agents and untrusted code inside microsandbox, a local-first microVM runtime. It follows the same shape as the bubblewrap lab: start small, then add the pieces that make a sandbox usable for agents - resource limits, an egress allowlist, secrets, snapshots, and agent integrations.

Everything here was verified on Linux with microsandbox 0.7.2, KVM enabled, and the runtime installed through the Python SDK.

## What microsandbox is

Each sandbox is a lightweight virtual machine with its own Linux kernel, filesystem, and network stack. It is not a set of namespaces on your host kernel: the boundary is hardware virtualization.

- **Hardware isolation.** The guest gets its own kernel, so a container-style kernel bug is not automatically a host bug.
- **Local and embeddable.** The SDK boots the VM as a child process. There is no daemon and no server to run.
- **Docker-like inputs.** Sandboxes start from standard OCI images (Docker Hub, GHCR, ECR, GCR, and others), and the workflow is image, command, shell, volume.
- **Fast and cheap enough to create per task.** Vendor figures put average boot under 100 ms; in this lab a sandbox is ready in a couple of seconds including image checks.
- **Programmable.** CPUs, memory, volumes, network policy, secrets, scripts, patches, and lifecycle are all configurable from the CLI or an SDK.
- **Multi-language SDKs.** TypeScript, Rust, Python, Go, and Ruby expose the same model. This lab uses Python, because this repo runs a Python environment through pixi.

The comparison to the bubblewrap lab is useful:

| | bubblewrap | microsandbox |
|---|---|---|
| Isolation | namespaces + seccomp, shared host kernel | own guest kernel, KVM or libkrun |
| Start cost | milliseconds | tens to hundreds of milliseconds, plus image checks |
| Inputs | paths you bind in by hand | OCI images, disk images, host directories |
| Best at | slim separation around one process | running untrusted or generated code end to end |
| Failure mode | a host kernel bug can cross the boundary | a hypervisor or guest kernel bug is needed |

Both are local, both skip the daemon, and they layer well: use microsandbox when the workload itself is hostile, and bubblewrap when you only need to trim what a process can see.

## The Vagrant parallel

If you ran Vagrant in the 2010s, microsandbox will feel familiar. The mental model is the same: describe a machine, bring it up, run things in it, snapshot it, throw it away. The vocabulary changed.

| Vagrant | microsandbox |
|---|---|
| `Vagrantfile` | `sandbox.yaml`, CLI flags, or an SDK builder |
| box | OCI image or disk image |
| `vagrant up` | `msb create`, `msb run`, or `Sandbox.create()` |
| `vagrant ssh` | `msb ssh`, `msb run ... -- sh`, or `sb.attach_shell()` |
| provisioner (shell, Ansible) | `scripts`, `patches`, `--init` |
| `vagrant halt` | `msb stop` |
| `vagrant destroy` | `msb rm`, `sb.destroy()` |
| `vagrant snapshot save` | `msb snap create` |
| `vagrant snapshot restore` | `msb snap restore`, `Sandbox.restore()` |
| `vagrant suspend` / `resume` | full snapshots with memory, or `msb stop` / `msb start` |
| `config.vm.synced_folder` | volumes: `bind`, `named`, `tmpfs` |
| `config.vm.network forwarded_port` | published ports and network policy |
| `vagrant box update` | `msb pull` |

Two differences matter for agents:

1. The VM is a library, not a CLI you drive by hand. `Sandbox.create(...)` boots a machine inside your program, so an agent framework can ask for a machine per task.
2. Snapshots and branches are first class and fast. Capturing a prepared toolchain and starting clean workers from it is a normal loop, not a rare operation.

## Requirements

- Linux with KVM (glibc 2.28 or newer), Apple Silicon macOS, or Windows 10+ with Windows Hypervisor Platform. Windows support is in preview.
- The `msb` runtime and the `libkrunfw` firmware library. The Python SDK wheel bundles both, so installing the SDK is enough.
- For this repo, the `ctnb` pixi environment already has the SDK.

Check the host once before anything else:

```sh
msb doctor
```

Sample output on this machine:

```
info Platform: Linux x86_64
info Version: v0.7.2
info MSB_HOME: /home/roro/.microsandbox
   ✓ msb          .../.pixi/envs/default/lib/python3.12/site-packages/microsandbox/_bundled/bin/msb
   ✓ libkrunfw    .../microsandbox/_bundled/lib/libkrunfw.so.5.6.1
   ! Root clone   copy fallback - reflink unavailable
   ✓ CPU virt     svm
   ✓ KVM device   /dev/kvm
   ✓ KVM access   read/write
   ! KVM AVIC     disabled - optional acceleration
done Host setup is ready.
```

The two warnings are safe to ignore for a lab:

- **Root clone fallback.** If the filesystem under `MSB_HOME` does not support reflinks, flat sandbox roots use independent sparse copies. Correctness is unaffected; creation is slower and uses more disk. Use a reflink-capable filesystem (for example Btrfs or XFS with reflink) if that matters.
- **KVM AVIC.** A host-wide AMD acceleration knob. Optional.

Runtime state lives in `~/.microsandbox`: cached images, sandboxes, and snapshots. Set `MSB_HOME` to move it.

### Install the SDK and runtime in this repo

```sh
pixi add --pypi microsandbox
msb doctor
```

`pixi add` places `msb` on the env path and installs the bundled runtime. The SDK resolves the runtime in this order: explicit path overrides, then `MSB_HOME`, then the binaries bundled in the SDK package. Because the wheel bundles a matching `msb` and `libkrunfw`, no download step is needed.

## Lab 1: hello microVM from the CLI

Run a one-off command. The sandbox is ephemeral and removed when the command exits:

```sh
msb run alpine -- sh -c 'uname -r; head -n 1 /etc/os-release; id -u'
```

Verified output:

```
6.12.109
NAME="Alpine Linux"
0
```

The kernel string is the giveaway: `uname -r` reports the guest kernel, not the host one. This is a real VM with its own kernel, which is the whole point.

A Python one-liner works the same way:

```sh
msb run python:3.12 -- python -c "print('hello from a microVM')"
```

The first run pulls the image; later runs reuse the cache. Expect the first `python:3.12` run to take a while, since that image is a few hundred megabytes.

### Interactive shell

`msb` detects whether your terminal is interactive, so there are no `-it` flags:

```sh
msb run alpine -- sh
```

## Lab 2: lifecycle from the terminal

Named sandboxes persist across commands.

```sh
# create and start
msb create --name dev alpine

# run commands inside
msb exec dev -- uname -r
msb exec dev -- sh -c "echo hello > /tmp/hello && cat /tmp/hello"

# inspect
msb ls                 # all sandboxes
msb ps                 # running only
msb metrics dev        # live CPU, memory, network
msb logs dev           # captured stdout and stderr, works when stopped
msb logs dev -f        # follow live

# lifecycle
msb stop dev
msb start dev
msb rm dev
```

`msb ls` on this machine, showing a leftover sandbox from earlier experiments:

```
NAME        IMAGE     STATUS     CREATED
tb-probe    python    stopped    2026-08-23 15:00:32
```

## Lab 3: the Python SDK

The SDK boots a microVM from your program. Save this as `hello.py`:

```python
import asyncio

from microsandbox import Sandbox


async def main() -> None:
    async with await Sandbox.create("hello", image="alpine") as sb:
        print("name:", await sb.name)

        out = await sb.exec("sh", ["-c", "echo hello-from-microvm; uname -r"])
        print("stdout:", out.stdout_text.strip())
        print("exit_code:", out.exit_code, "success:", out.success)

        shell = await sb.shell("id -u; head -n 1 /etc/os-release")
        print("shell:", shell.stdout_text.strip())


asyncio.run(main())
```

Run it inside the pixi environment:

```sh
python hello.py
```

Verified output:

```
name: hello
stdout: hello-from-microvm
6.12.109
exit_code: 0 success: True
shell: 0
NAME="Alpine Linux"
```

Two API details for 0.7.2 that differ from the published docs:

- `name` and `id` are awaitable properties, so write `await sb.name`, not `await sb.name()`.
- `exec` and `shell` return an `ExecOutput` with `stdout_text`, `stderr_text`, `stdout_bytes`, `stderr_bytes`, `exit_code`, and `success`.

Key methods used above:

| Call | Purpose |
|---|---|
| `Sandbox.create(name, **kwargs)` | boot a sandbox; usable as `async with` for automatic cleanup |
| `sb.exec(cmd, args, *, cwd, env, timeout, tty)` | run a command and capture output |
| `sb.shell(script, *, cwd, env, timeout)` | run a shell script string |
| `sb.fs.write(path, data)` / `sb.fs.read_text(path)` | move bytes and text in and out |
| `sb.fs.copy_from_host(host, guest)` / `copy_to_host` | transfer files |
| `await sb.metrics()` / `await sb.logs()` | resource usage and captured output |
| `sb.stop()` / `sb.kill()` / `sb.destroy()` | graceful stop, force stop, stop and remove |
| `await sb.attach_shell()` | bridge your terminal into the VM |

Creating a sandbox context manager is the recommended shape: on local sandboxes, leaving the `async with` block kills and removes the sandbox, so a crash cannot leave orphans behind.

## Lab 4: constrain egress

By default a sandbox gets public networking with private ranges and metadata endpoints blocked, which already covers the common SSRF and cloud-metadata cases. For an agent you usually want to go further and allow only the hosts it genuinely needs.

This policy denies all egress except HTTPS to `example.com`:

```python
from microsandbox import (
    Action,
    Direction,
    Network,
    NetworkDestination,
    NetworkDestinationKind,
    NetworkPolicy,
    Protocol,
    Rule,
    Sandbox,
)

net = Network(
    policy=NetworkPolicy(
        default_egress=Action.DENY,
        rules=(
            Rule(
                Action.ALLOW,
                Direction.EGRESS,
                NetworkDestination(NetworkDestinationKind.DOMAIN, "example.com"),
                Protocol.TCP,
                443,
            ),
        ),
    )
)

sb = await Sandbox.create("net-check", image="alpine", network=net)
try:
    allowed = await sb.shell("wget -qO- -T 5 https://example.com >/dev/null 2>&1; echo $?")
    blocked = await sb.shell("wget -qO- -T 5 https://example.org >/dev/null 2>&1; echo $?")
    print("allowed host exit:", allowed.stdout_text.strip())
    print("blocked host exit:", blocked.stdout_text.strip())
finally:
    await sb.stop()
    await sb.destroy()
```

Verified output:

```
allowed host exit: 0
blocked host exit: 1
```

The destination kinds are `ANY`, `CIDR`, `IP`, `DOMAIN`, `DOMAIN_SUFFIX`, and `GROUP`; protocols are `TCP`, `UDP`, `ICMPV4`, and `ICMPV6`. Suffix matching is how you allow a family of hosts such as `*.githubusercontent.com`. `Network` also carries `deny_domains`, `dns` and `tls` configuration, rate limits, and connection caps.

For stricter work, where the agent must not reach the internet at all, drop networking entirely by omitting any allow rules with `default_egress=Action.DENY` and an empty rule set, or keep the network off and pass data in with volumes.

## Lab 5: secrets that do not enter the VM

Agents need API keys, and a key pasted into a VM is a key exposed to everything running in that VM. microsandbox replaces the value with a placeholder inside the guest and substitutes the real value only for the hosts you allow.

```python
from microsandbox import Sandbox, Secret

sb = await Sandbox.create(
    "secret-check",
    image="alpine",
    secrets=[
        Secret.env(
            "LAB_TOKEN",
            value="s3cr3t-value",
            allow=["example.com"],
        ),
    ],
)
```

Inside the guest, `LAB_TOKEN` exists as a placeholder, so `test -n "$LAB_TOKEN"` succeeds, but reading the variable does not reveal the credential and the value is only injected on requests to `example.com`. The security model page is explicit that the guarantee is a boundary property: the secret never enters guest memory, and substitution happens on the allowed egress path. Treat any host that is not in `allow` as unable to see the secret, and audit `violation_action` if you want blocked attempts logged.

Verified: with the secret configured, `test -n "$LAB_TOKEN"` returns present inside the sandbox.

## Lab 6: snapshots and branches

This is the part that maps most directly onto `vagrant snapshot`, but it happens in seconds and works on running machines.

Prepare a sandbox, then capture it:

```python
from microsandbox import Sandbox, Snapshot

sb = await Sandbox.create("baseline", image="python:3.12")
try:
    await sb.shell("pip install --quiet requests")
finally:
    await sb.stop()

snap = await Snapshot.create("ready", from_sandbox="baseline")
print("snapshot:", snap.reference)
```

Restore into a new sandbox, leaving the source untouched:

```python
child = await Sandbox.restore("baseline:ready", name="worker")
print(await child.name)
await child.stop()
await child.destroy()
```

Verified: snapshot creation produced a local artifact, and `Sandbox.restore` booted a second sandbox from it.

Two snapshot types:

| Type | Saves | On restore |
|---|---|---|
| **disk** (default) | files and owned volumes | boots a new VM from the saved disk |
| **full** | disk, memory, and running processes | resumes execution where it stopped |

Branching is a snapshot that you do not need to keep: it clones a running or paused sandbox directly, with copy-on-write memory sharing, so several children can diverge from one prepared state.

```sh
msb branch baseline --name experiment-a
msb branch baseline --names experiment-b experiment-c
```

Local snapshots use `group:member` selectors such as `baseline:ready`, and a group can carry a head pointer so `msb snap restore work` picks the latest capture. Snapshots export to portable `.msb` archives for moving between machines.

## Lab 7: warm workers

The pattern worth stealing from the Vagrant era: provision once, bless an image, then start identical workers from it instead of provisioning every time.

1. Create a sandbox from a base image.
2. Install the toolchain and dependencies.
3. Stop it and capture a disk snapshot.
4. For every task, restore a private copy and run the job.
5. Throw the copy away.

```python
from microsandbox import Sandbox

worker = await Sandbox.restore("toolchain:ready", name="worker-42")
try:
    out = await worker.shell("./run-task.sh")
    print(out.stdout_text)
finally:
    await worker.stop()
    await worker.destroy()
```

Each restore gets its own copy of the disk, so workers cannot contaminate each other. This is the same idea as a Vagrant box plus a provisioner, with the snapshot standing in for the long build step.

## Lab 8: hand it to an AI agent

There are two ways to connect agents to microsandbox, and they compose.

### Pattern A: the agent stays outside, the sandbox is its tool

The MCP server exposes sandbox lifecycle, command execution, filesystem access, volumes, and monitoring as structured tool calls. Any MCP client can use it.

Claude Code:

```sh
claude mcp add --transport stdio microsandbox -- npx -y microsandbox-mcp
```

Cursor (`~/.cursor/mcp.json`), VS Code (`.vscode/mcp.json`), and OpenCode (`.opencode.json`):

```json
{
  "mcpServers": {
    "microsandbox": {
      "command": "npx",
      "args": ["-y", "microsandbox-mcp"]
    }
  }
}
```

Agent Skills are the lighter option: no server, just files that teach the agent how to drive the CLI and SDK.

```sh
npx skills add superradcompany/skills
```

This works with Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, and other agents that read the skills format. Once installed, the agent can create sandboxes, run commands, manage files, and control lifecycle through natural language.

### Pattern B: the agent runs inside the microVM

Here the agent itself is the untrusted workload. Give it a dedicated machine and only the project directory:

```sh
msb run --name agent -v "$PWD":/work python:3.12 -- bash
```

Then, inside the sandbox, start the agent CLI of your choice and let it work against `/work`. The agent can install packages, run tests, and rewrite files without seeing your real home directory, your SSH keys, or your browser profile, because none of them are in the VM. When it is done:

```sh
msb stop agent
msb rm agent
```

The documented example library covers this shape for Claude Code, Codex CLI, OpenCode, OpenClaw, Goose, Gemini CLI, Hermes Agent, and Pi, plus browser agents such as Browser Use and Playwright running against isolated Chromium.

## Lab 9: terminal and desktop access

There is no separate TUI. The `msb` CLI is the terminal interface, and it detects whether it is talking to a TTY, so `msb run alpine -- sh` gives you an interactive session without extra flags. For visual work, the pieces exist:

```sh
msb ssh authorize --file ~/.ssh/id_ed25519.pub
msb ssh devbox                 # interactive SSH
msb ssh devbox -- uname -a     # one-off over SSH
msb ssh serve devbox --host 127.0.0.1 --port 2222   # expose for Remote-SSH
```

From there you can point VS Code Remote-SSH at a sandbox, or run the documented browser options: `code-server` for an isolated VS Code workspace, JupyterLab for token-authenticated notebooks, and a VNC desktop with LXQt, TigerVNC, and noVNC when you need a full desktop. The SDK equivalent of an interactive shell is `await sb.attach_shell()`.

## Threat model worksheet

| Threat | Covered by |
|---|---|
| Prompt injection runs destructive commands | the workload is confined to one VM; host home, SSH keys, and browser data are not in it |
| Kernel exploit from generated code | the guest has its own kernel; a shared-kernel bug is not automatically reachable |
| Cloud metadata and private-range access | default networking blocks private, link-local, and metadata destinations |
| Exfiltration to arbitrary hosts | a `default_egress=DENY` policy with an explicit allowlist |
| Credential exposure inside the workload | secret substitution keeps values out of the guest and only for allowed hosts |
| Cross-project contamination | bind only the target project directory as a volume |
| Dirty state between tasks | each restore or branch is a private copy; destroy the worker when done |

| Not covered | Why |
|---|---|
| A hypervisor or guest-kernel escape | hardware isolation shrinks the surface; it does not make it zero |
| Network exfiltration to a host you allowed | an allowlisted host is trusted by definition |
| Image supply chain | the OCI image you pull is part of your trust base; pin digests for serious work |
| Side channels between host processes | out of scope for a local microVM |
| Data buffered by your application during a snapshot | flush and commit before capture; flushing does not include application buffers |

## Gotchas

1. **Reflink warnings are about storage, not security.** Without a reflink-capable `MSB_HOME`, flat roots use sparse copies. Expect slower creation and more disk use.
2. **The first image pull dominates startup.** Boot is fast; the network is not. Pre-pull with `msb pull` when latency matters.
3. **Snapshots do not capture host connections or external mounts.** Restore supplies host paths again, and applications must reconnect.
4. **Full snapshots need matching CPU and memory settings.** Keep the capture settings, or restore with `--disk-only`.
5. **`Sandbox.create` resolves an existing runtime; it does not install one.** If the runtime is missing or partial, call `ensure_runtime()` or install it explicitly.
6. **API drift is real in a beta project.** This lab was verified against 0.7.2, where `sb.name` is awaitable and the docs still show the callable form. Pin the SDK version in a lab you want to keep working.
7. **`msb rm` fails while a sandbox runs.** Stop first, or use `sb.destroy()` which stops and removes.
8. **Mount only what the task needs.** A bind mount of `$HOME` or of the repo root throws away most of the isolation you just paid for.

## Ecosystem

| Resource | What it is |
|---|---|
| [superradcompany/microsandbox](https://github.com/superradcompany/microsandbox) | the runtime, CLI, and SDKs |
| [docs.microsandbox.dev](https://docs.microsandbox.dev) | documentation, including the full config and security model |
| [superradcompany/microsandbox-mcp](https://github.com/superradcompany/microsandbox-mcp) | the MCP server used in Lab 8 |
| [superradcompany/skills](https://github.com/superradcompany/skills) | Agent Skills that teach agents to drive microsandbox |
| [ya-luotao/awesome-microsandbox](https://github.com/ya-luotao/awesome-microsandbox) | curated list of SDKs, integrations, and tools |
| [microsandbox cloud](https://docs.microsandbox.dev/cloud/overview) | the same SDK against hosted infrastructure, with an API key as the only change |

Community integrations worth knowing about include Eve by Vercel (an agent framework with microsandbox as a sandbox backend), `langchain-microsandbox` for LangChain Deep Agents, `wrap` by Tobi Lütke for running coding agents in isolated Arch Linux microVMs, and Agent VM by Wiren Board for folder-scoped agent VMs.

## Operations and cleanup

```sh
msb ls                     # list sandboxes
msb snap ls                # list snapshots
msb images                 # cached images
msb image rm python        # drop a cached image
msb metrics                # live resource stats
msb rm --force <name>      # remove a sandbox
rm -rf ~/.microsandbox      # nuclear option: all cached state
```

To remove the SDK from this repo:

```sh
pixi remove microsandbox
```

## Where this goes next

- Wrap `Sandbox.create` behind a small helper so every agent task gets a fresh VM, an allowlist, and a snapshot-derived base.
- Move the allowlist into version control next to the agent config, not in ad hoc shell history.
- Turn Lab 7 into a queue: one prepared snapshot, many disposable workers.
- Keep the bubblewrap lab for the cheap cases and reach for microsandbox when the code under test is the threat, not just the process.
