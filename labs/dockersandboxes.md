# AI Sandbox Demo Lab: Docker Sandboxes

A hands-on style guide to Docker Sandboxes, Docker's microVM sandbox for AI coding agents. It is the **microVM approach**, the same family as [the microsandbox lab](microsandbox.md) and [the nanvix lab](nanvix.md), delivered as a managed service instead of a runtime you drive yourself. [The bubblewrap lab](bubblewrap.md) covers the cheaper namespace approach, and [the MXC lab](mxc.md) covers the policy layer over the engines.

> **Status of this page.** The policy, approval, and audit sections were verified live against `sbx` 0.48.0 on Ubuntu 26.04 with KVM, using the `shell` agent and real sandboxes. The workflow, templates, MCP, and editor sections are built from Docker's own documentation and are illustrative rather than transcripts.

## What Docker Sandboxes is

Docker Sandboxes runs AI coding agents inside disposable microVMs. Each sandbox gets its own Linux kernel, its own Docker Engine, its own filesystem, and its own network. The agent can install packages, edit configs, and build and run containers without touching your host beyond the workspace you explicitly share.

The important design choice is the audience: this is not a generic sandbox builder, it is a product built around coding agents. That shows up everywhere.

- **MicroVM per agent.** The primary trust boundary is the hypervisor, not a namespace or a seccomp filter.
- **Docker inside, not the host socket.** Agents that need to build images or run Compose get a private Docker Engine inside the VM.
- **Agent-first CLI.** `sbx run claude` is the whole getting-started experience. No daemon to configure, no Docker Desktop required.
- **YOLO mode by default.** Agents are expected to run with permission prompts off, because the sandbox, not the prompt, is the control.
- **Supported agents out of the box.** Claude Code, Copilot CLI, Codex CLI, Gemini CLI, OpenCode, and Kiro, with a template and kit system for custom ones.
- **Governance as the paid tier.** The `sbx` CLI is free, including commercial use. Centrally managed policies and MCP governance are a separate subscription.

It runs on macOS (Sonoma 14+, Apple silicon), Windows 11 with Windows Hypervisor Platform, and Ubuntu 24.04+. There is also a cloud variant that runs the same sandboxes remotely.

## How the four labs compare

| | bubblewrap | microsandbox | nanvix | Docker Sandboxes |
|---|---|---|---|---|
| Approach | namespaces on the host kernel | microVM, Linux guest | microVM, own guest OS | microVM, Linux guest |
| Role | the engine | the engine | the engine | the managed service |
| Isolation | namespaces + seccomp, shared host kernel | microVM, own guest kernel | microVM, own guest kernel | microVM, own guest kernel |
| Guest userland | the host's Linux | Linux | Nanvix, not Linux | Linux |
| Interface | `bwrap` flags you assemble | SDK-first, `msb` CLI | the `nanvixd` binary | `sbx` CLI, agent-first |
| Docker inside | no | yes, by default | no | yes, private Engine per sandbox |
| Network control | hand-built, via flags and seccomp | policy objects in the SDK | syscalls blocked outright | presets plus `sbx policy` rules |
| Credentials | you keep them out by hand | secret substitution to allowed hosts | you keep them out by hand | host proxy injects into outbound headers |
| Workspace | bind mounts you choose | volumes you choose | live host mount, path sandboxed | direct mount, clone mode, or mountless |
| Best at | slim, scriptable separation | embedding sandbox creation in code | a guest OS you control | running coding agents unattended |
| Cost | free, DIY | free, DIY plus cloud option | free, but the workload needs porting | CLI free, governance paid |

Roughly: reach for bubblewrap when you want to trim what one process can see, microsandbox when you want to boot machines from your own code, nanvix when the workload needs a guest operating system that is not Linux, and Docker Sandboxes when you want to hand a coding agent a machine and walk away. The first two approaches are the fork; the choice inside the microVM family is about the guest and the ergonomics.

## The Vagrant parallel

Docker Sandboxes is arguably the closest thing to "Vagrant for agents" among the four, because it owns the whole workflow: image, config, provisioning, and cleanup.

| Vagrant | Docker Sandboxes |
|---|---|
| `Vagrantfile` | `sbxenv.yaml` environment files, kits, or CLI flags |
| box | agent template image (OCI) |
| `vagrant up` | `sbx run` or `sbx create` |
| `vagrant ssh` | `sbx exec -it <name> bash` |
| provisioner (shell, Ansible) | built-in agent kits, env files, template save/load |
| `vagrant halt` | `sbx stop` |
| `vagrant destroy` | `sbx rm` |
| `vagrant up` again | `sbx run --name` re-attaches to the same sandbox |
| `config.vm.synced_folder` | direct workspace mount, or `--clone` for a private clone |
| `config.vm.network forwarded_port` | `--publish` and `sbx ports` |
| `vagrant box update` | template updates, or `sbx template load` |

One honest difference: the snapshot story is not the same. Vagrant snapshots a machine and can restore it in place. Docker Sandboxes saves a sandbox's container filesystem as a reusable template image, and mounted filesystems plus the Docker store are not included. That is closer to `vagrant package` than to `vagrant snapshot`. If you want live machine snapshots and branching, that is microsandbox's `msb snap` and `msb branch`.

## Requirements and install

Prerequisites by platform:

- **macOS:** Sonoma 14 or later, Apple silicon.
- **Windows:** Windows 11, 64-bit Intel or AMD, Windows Hypervisor Platform enabled for local sandboxes.
- **Linux:** Ubuntu 24.04 or later, 64-bit Intel, AMD, or Arm, KVM available, and your user in the `kvm` group. Docker explicitly does not test Ubuntu derivatives such as Linux Mint or Pop!_OS.

You do not need Docker Desktop or Docker Engine on the host. Install the `sbx` CLI:

```sh
# macOS
brew trust docker/tap
brew install docker/tap/sbx

# Windows (PowerShell)
winget install -h Docker.sbx

# Ubuntu, sbx only
curl -fsSL https://get.docker.com | sudo REPO_ONLY=1 sh
sudo apt install docker-sbx

# Ubuntu, Docker Engine and sbx together
curl -fsSL https://get.docker.com | sudo SBX=1 sh
```

Enable Windows Hypervisor Platform from an elevated PowerShell prompt, then sign in:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -All
```

```sh
sbx login
```

On Linux, verify KVM and group membership first:

```sh
lsmod | grep kvm                 # expect kvm_intel, kvm_amd, kvm_arm64, or kvm
sudo usermod -aG kvm $USER       # then sign out and back in, or run: newgrp kvm
```

Inside a VM or VDI environment, local sandboxes additionally need nested virtualization. Cloud sandboxes skip that requirement.

## Lab 1: your first sandbox

From a project directory, launch an agent:

```sh
cd ~/my-project
sbx run --name my-sandbox claude
```

The first run pulls the agent image and asks you to pick a global network policy:

```
Initialize the global network policy for your sandboxes:

  Applies to all sandboxes, current and future - change it later with
  "sbx policy allow/deny/rm". Kits, including built-in agent kits, may
  also add per-sandbox rules.

     1. Open         - All network traffic allowed, no restrictions.
  >  2. Balanced     - Default deny, with common dev sites allowed.
     3. Locked Down  - All network traffic blocked unless you allow it.
```

`Balanced` is the sensible default: default deny, with common development hosts allowed. `Locked Down` blocks even the model provider until you allow it, which is what you want for a genuinely untrusted agent. Both are changeable later.

From another terminal, look at what exists:

```sh
sbx ls
```

```
SANDBOX       AGENT    STATUS    PORTS   WORKSPACE
my-sandbox    claude   running           ~/my-project
```

Each row is a sandbox, the agent in it, its status, published ports, and the one host directory it can see.

Sandboxes persist after the agent exits. Stop one and pick it up later:

```sh
sbx stop my-sandbox
sbx run --name my-sandbox        # re-attach from anywhere
sbx rm my-sandbox                # delete it and everything inside
```

`sbx rm` confirms before deleting, accepts `--force` to skip the prompt, and `sbx prune` clears stopped sandboxes (preview with `--dry-run`, filter with `--filter until=168h`).

## Lab 2: workspace modes

This is where a lot of the security decisions live. There are three modes.

**Direct mount (default).** `sbx run` mounts the current directory read-write at the same absolute path inside the sandbox. No sync process: the agent and your host see the same bytes, so a change appears in your working tree as the agent writes it.

```sh
sbx run claude                      # current directory
sbx run claude ~/my-project         # a specific directory
sbx run claude ~/project-a ~/shared-libs:ro ~/docs:ro   # extras, some read-only
```

**Clone mode.** Your repository is mounted read-only at `/run/sandbox/source` and the agent works on a private clone inside the VM. Its edits never reach your host until you fetch them over a `sandbox-<name>` Git remote.

```sh
sbx run --clone claude .
sbx create --clone --name my-sandbox claude .
```

**Mountless.** Omit the workspace path and the sandbox has no host bind mount at all. The agent works in the template's default directory, usually `/home/agent/workspace`, and you move files with `sbx cp`.

```sh
sbx create --name scratch claude
sbx run --name scratch
sbx cp ./config.json scratch:/home/agent/workspace/
sbx cp scratch:/home/agent/workspace/output.log ./
```

Choosing between them:

- Direct mount is the most convenient and the least contained. The agent can write build files, Git hooks, CI config, IDE tasks, and agent settings that execute later. Review before you commit.
- Clone mode protects your repository from modification, but not from inspection: the read-only mount includes untracked and `.gitignore`d files, so a `.env` in your working tree is readable inside the sandbox.
- Mountless is the tightest default when the agent does not need your repo at all.

## Lab 3: network policy

All outbound TCP is blocked unless a rule allows the destination. UDP is off unless you turn on the experimental UDP feature, ICMP is blocked, and DNS goes through an internal resolver that enforces the same policy.

```sh
sbx policy ls                              # show active rules
sbx policy allow network registry.npmjs.org
sbx policy deny network example.com
sbx policy rm network example.com
```

The global preset you chose at first run is just a starting rule set. You can keep `Locked Down` and allow exactly the hosts a task needs, which is the pattern worth copying: start from deny, add the model provider, the package registry, and the Git host, and nothing else.

### The three presets

The preset is the baseline every sandbox inherits:

| Preset | What it does |
|---|---|
| `Open` | all outbound TCP allowed, no restrictions |
| `Balanced` | default deny, with a baseline allowlist covering AI provider APIs, package managers, code hosts, container registries, and common cloud services |
| `Locked Down` | no baseline allow rules, every destination needs an explicit rule from you or a kit |

`Balanced` is not small. On this machine it installs 194 allow rules:

```sh
sbx policy init balanced
```

```console
$ sbx policy ls
POLICY         SOURCE   APPLIES TO   SUMMARY
local-policy   local    all          network: 194 allow; filesystem read: 1 allow; filesystem write: 1 allow
```

For a machine that runs agents unattended, `Locked Down` is the interesting one, because the baseline is exactly the list of hosts you have not thought about yet.

In a non-interactive environment the prompt cannot be shown, so set the preset first:

```sh
sbx policy init deny-all
```

The accepted values are `allow-all`, `balanced`, and `deny-all`. `sbx policy reset` clears the store and prompts again.

### Rules

A rule covers a destination host, and it can be scoped to one sandbox or to every sandbox on the machine:

```sh
sbx policy allow network api.anthropic.com
sbx policy allow network "api.anthropic.com,*.npmjs.org,*.pypi.org"
sbx policy deny network ads.example.com

# scoped to a single sandbox
sbx policy allow network --sandbox my-sandbox api.example.com
sbx policy deny network --sandbox my-sandbox ads.example.com
```

Rules can be narrowed further to an HTTP method and a path, which is the difference between "may talk to the GitHub API" and "may read these repositories":

```sh
sbx policy allow network api.github.com --method GET --path '/repos/org/project/**'
sbx policy allow network api.github.com --method GET,HEAD
sbx policy allow network api.github.com --method ANY
```

Deny rules take precedence over allow rules, so the usual shape is a broad allow with a narrow deny carved out of it:

```sh
sbx policy allow network api.example.com
sbx policy deny network api.example.com --method POST --path '/admin/**'
```

Since version 0.38.0 you can also deny at creation time, which is the cleaner place for it:

```sh
sbx create --deny-network ads.example.com --deny-network "*.openai.com" claude .
sbx run --deny-network ads.example.com claude
```

Verified: two sandboxes created with and without that flag, against the same global policy. The one with the deny got `403` from a host the policy otherwise allows, the one without it reached the host normally.

```console
$ sbx policy ls netlab2
  Policy for sandbox:  netlab2

NETWORK
  • allow 194 hosts from local-policy
  • deny 2 hosts from 38c7a2a0-9c9b-4219-bfea-8a9d79d9afb6
  • http allow 1 host from local-policy
  • http deny 1 host from local-policy
```

### Check before you run

`sbx policy check network` answers the question without starting a sandbox, and it returns a non-zero exit status when the answer is no:

```sh
sbx policy check network api.anthropic.com
sbx policy check network blocked.example.com
sbx policy check network "myhost:22"
sbx policy check network --sandbox my-sandbox api.example.com
```

Verified output:

```
  Allowed:     api.anthropic.com:443
  Governance:  Local policy only
  Context:     global
```

```
  Denied:      blocked.example.com:443
  Governance:  Local policy only
  Context:     global
  Reason:      no matching allow rule (default deny)
```

A bare hostname is evaluated on port 443. `host:port`, an IP, and a URL all work too, and `--json` gives you the same answer in a form a script can read.

### When the agent asks for access

Under `Balanced` and `Locked Down`, a destination with no matching rule is not silently dropped. The sandbox gets a `403`, the destination lands in an approval queue, and a human decides:

```console
$ sbx exec netlab curl -sS -i https://example.com
HTTP/1.1 403 Forbidden
Content-Length: 90
Content-Type: text/plain

Approval required for example.com:443.

Review and respond with:
  sbx policy approval ls
```

The queue lists every pending request with the sandbox that made it:

```console
$ sbx policy approval ls
APPROVAL                                              SANDBOX   TITLE                DETAIL
network:W3eISyIAQ2Wt1bUKNNjEP2faHGQNNqSQoBGRexU7NMg   netlab    example.com:443      Protocol: TCP Resource type: domain no matching allow rule (default deny)   allow (Allow), dismiss (Dismiss)
network:-Ere5cxW9P6NuV_BjwsQtjajKy767xw7D-ebLvg973E   netlab    169.254.169.254:80   Protocol: TCP Resource type: domain no matching allow rule (default deny)   allow (Allow), dismiss (Dismiss)
```

Approving is a policy change, so it applies to later requests rather than the one that was blocked:

```sh
sbx policy approval respond network:W3eISyIAQ2Wt1bUKNNjEP2faHGQNNqSQoBGRexU7NMg --option allow
```

Verified: the same `curl` that returned `403` returned `200` after the approval.

For an unattended fleet, pre-approve the destinations the task needs instead of answering prompts.

### The audit log

`sbx policy log` is the record of what the agents actually did, split into blocked and allowed requests:

```console
$ sbx policy log
BLOCKED REQUESTS
SANDBOX   TYPE      HOST                 PROXY     RULE   REASON                                  LAST SEEN         COUNT
netlab    network   example.com:443      forward   ...     No matching allow rule (default deny)   08:09:54 20-Oct   2

ALLOWED REQUESTS
SANDBOX   TYPE      HOST                      PROXY            RULE   REASON   LAST SEEN         COUNT
netlab    network   api.anthropic.com:443     forward-bypass                   08:09:49 20-Oct   1
netlab    network   archive.ubuntu.com:80     forward                          08:09:41 20-Oct   1
```

Read this after a run. Destinations that show up here but not in your policy are the ones your agent wanted and you did not know about. The count column tells you whether it was one request or a stream.

### What the agent cannot reach

Verified from inside a running sandbox:

```
anthropic=401          # allowed host, reachable
example=403            # not in the policy
metadata=403           # 169.254.169.254
hostinternal=403       # host.docker.internal
```

The `401` is the point worth reading: the host was reachable, and the API answered because no key was presented. Reachability and authorization are separate problems, and the policy only settles the first.

The metadata service and `host.docker.internal` are refused by the policy, not by luck. Note that the second line is also why a sandbox cannot be used to attack services on your machine.

Docker itself is not a way out either. The socket inside the sandbox looks like a Docker socket, and it is one, but it belongs to the sandbox's own private engine:

```console
$ sbx exec netlab docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS   PORTS   NAMES
```

Empty, while the host engine has running containers. The agent has a Docker daemon, and it is not yours.

### Kits and their rules

Agent kits add per-sandbox allow rules on top of the preset, including under `Locked Down`. That is convenient, and it means the effective policy is not only what you wrote. Inspect it:

```sh
sbx policy ls my-sandbox --source kit --type network --wide
```

To block something a kit allowed, add an explicit deny rule, which takes precedence:

```sh
sbx policy deny network --sandbox my-sandbox openrouter.ai
```

## Lab 4: credentials and the sentinel proxy

No credentials reach a sandbox by default. When you do provide them, they never enter the VM. Instead the agent sees a sentinel value, and a host-side proxy replaces it with the real credential on the way out, only for the hosts you allowed.

```sh
# Store a supported service credential
sbx secret set github --command 'gh auth token'

# Use an API key interactively
sbx secret set openai

# Registry credentials for non-Docker-Hub pulls
gh auth token | sbx secret set --registry ghcr.io --password-stdin
```

For Claude Code with a Claude subscription, no setup is needed: run `/login` inside the sandbox and the OAuth session token stays on the host.

Two related defaults are worth knowing:

- **SSH agent forwarding is on by default.** Your private keys stay on the host, but any process in the sandbox can ask the forwarded agent to sign.
- **Environment variables are visible to the sandbox.** Use `sbx secret` for credentials, not `-e`. Use `-e` and `--env-file` for non-secrets such as `LOG_LEVEL`.

## Lab 5: Docker inside the sandbox

This is the feature that distinguishes Docker Sandboxes from a plain container-with-socket-mount approach. Each sandbox runs its own Docker Engine, so `docker build` and `docker compose up` execute against that engine, not your host daemon.

```sh
sbx exec -it my-sandbox bash
docker build -t app .
docker compose up -d
```

There is no path from the sandbox to your host Docker daemon, which is exactly the hole that makes socket-mounting risky. The trade is overhead: you pay for a VM plus its own daemon.

One boundary detail: a local stdio MCP server registered through the MCP gateway runs on the host, outside the VM. If that server starts a container, it uses host Docker.

## Lab 6: templates

A saved template captures a sandbox's container filesystem, so you can prepare a toolchain once and reuse it.

```sh
sbx template save my-sandbox my-template:v1
sbx template ls
sbx run -t my-template:v1 claude
sbx template save my-sandbox my-template:v1 --output my-template.tar
sbx template load my-template.tar
sbx template rm my-template:v1
```

Limits worth internalizing:

- Mounted filesystems, including host workspaces and the Docker store at `/var/lib/docker`, are not included.
- Agent configuration files are recreated at create time, so changes to files such as `/home/agent/.claude/settings.json` do not survive in a template.
- Anything you manually wrote into the sandbox filesystem, including API keys, is captured. Use `sbx secret` so credentials never touch the filesystem.

This is the closest analogue to packaging a Vagrant box, and the warnings are the same ones you would give about baking secrets into an image.

## Lab 7: MCP gateway

Supported agents connect to a single MCP gateway endpoint. The gateway runs on the host side of the boundary and brokers access to registered MCP servers, which can be remote endpoints or local stdio servers launched on the host.

Because enforcement happens at the gateway, governed MCP requests are checked before tool calls, resource reads, prompt retrieval, or gateway meta-tools run. If you already gate agent tool use, the gateway is the natural insertion point, and it is one of the things organization governance centralizes.

## Lab 8: editors and integrations

Editors connect over SSH rather than sharing your filesystem, so the sandbox stays the boundary:

```sh
sbx exec -it my-sandbox bash          # shell inside the VM
# then point VS Code Remote-SSH or Cursor at the sandbox
```

The documented integrations cover VS Code and Cursor. Published ports let a dev server inside the sandbox be reached from your host browser:

```sh
sbx run --publish 8080:3000 --name my-sandbox claude
sbx ports my-sandbox --publish 8080:3000     # on an existing sandbox
sbx ports my-sandbox --unpublish 8080:3000
sbx ports my-sandbox                          # show mappings
```

Re-attaching with `sbx run` ignores `--publish`, so use `sbx ports` for an existing sandbox.

## Lab 9: the interactive dashboard

Unlike microsandbox, Docker Sandboxes ships a real terminal UI. Run `sbx` with no subcommands:

```
sbx
```

You get a dashboard of every sandbox as cards with live status, CPU, and memory. From there you can create (`c`), start or stop (`s`), attach to an agent (`Enter`), open a shell (`x`), and remove (`r`) sandboxes. `tab` switches to a network governance panel where you can watch outbound connections and add or remove rules, and `?` lists the shortcuts.

## Lab 10: governance

The free tier manages sandboxes on one machine. The paid tier, Docker AI Governance, pushes network, filesystem, and MCP policies from a central place onto every developer's machine. Organization rules take precedence over local ones. If you are rolling agents out to a team, this is the difference between "everyone configures it well" and "it is configured".

## Threat model worksheet

Default posture, per Docker's own security documentation:

| Control | Default |
|---|---|
| Outbound TCP | denied unless a rule allows the destination |
| Outbound UDP | disabled (experimental toggle plus rules) |
| ICMP | blocked |
| DNS | internal resolver that enforces policy |
| Host filesystem | only explicitly mounted workspaces plus the shared skills store |
| Host Docker daemon | unreachable |
| Sandbox to sandbox | no direct network communication |
| Credentials | none by default; injected by the host proxy when configured |

What the sandbox defends against:

| Threat | Covered by |
|---|---|
| Prompt injection runs destructive commands | the workload is confined to one VM; host home, SSH keys, and browser data are not in it |
| Agent builds or runs containers | private Docker Engine, no host socket |
| Kernel exploit from generated code | guest has its own kernel |
| Cloud metadata and arbitrary egress | default-deny TCP, internal DNS, blocked ICMP |
| API key theft from the sandbox | sentinel plus host-side proxy injection; values never enter the VM |
| Exfiltration to a host you did not allow | default-deny policy, approval queue, and the audit log |
| Reaching services on your machine | `host.docker.internal` and private ranges are refused by policy |
| Reusing the host Docker daemon to escape | the sandbox has its own engine; the host socket is not mounted |

What it does not cover, or where the default is weaker than it sounds:

| Limitation | Why |
|---|---|
| Direct mount has no boundary | the agent can write hooks, CI config, build files, IDE tasks, and agent settings that execute later |
| Clone mode protects from modification, not inspection | untracked and ignored files, including `.env`, are readable in the sandbox |
| Hard links in a direct-mounted workspace | a workspace file hard-linked outside the workspace can be modified through the authorized path |
| Clipboard is write-only | a sandbox can write text to your host clipboard; review before pasting on the host |
| SSH agent forwarding is on | the sandbox can request signatures from the forwarded agent |
| Templates can capture secrets | anything written to the sandbox filesystem is saved into the template |
| Local MCP stdio servers | run on the host, outside the VM boundary |
| A destination you allowlisted | an allowed host can carry anything the agent reads |
| Kits that add their own rules | a kit can allow hosts you never approved; check `sbx policy ls --source kit` |
| Hypervisor and guest kernel escapes | reduced surface, not zero |

The practical takeaway is the same as the other labs: the boundary is real, but it is the boundary you configured. Direct mount plus `Balanced` networking plus a broad MCP list is a very different risk posture from clone mode plus `Locked Down` plus nothing extra.

## Gotchas

1. **Linux is Ubuntu 24.04+ only.** Derivatives are explicitly untested, and the convenience script can misconfigure their package repositories.
2. **KVM and the `kvm` group are required for local sandboxes.** Without them, local sandboxes will not start; cloud sandboxes still work.
3. **`sbx` does not add `docker.io` to image references.** Pass the full reference for non-Docker-Hub registries.
4. **Registry credentials are per registry.** Docker Hub reuses your `sbx login` session; GHCR, ECR, ACR, and friends need `sbx secret set --registry`.
5. **Re-attach ignores `--publish`.** Use `sbx ports` on an existing sandbox.
6. **Updating `sbx` or templates does not update agents inside existing sandboxes.** Run the agent's own update command inside the sandbox, then restart the session.
7. **Clone mode is fixed at create time** and must be set up from the main repository checkout, not a secondary Git worktree. Removing the sandbox also removes its `sandbox-<name>` remote.
8. **Avoid network-attached storage as a workspace.** Workspaces are a filesystem passthrough, so NFS, SMB, and cloud-synced folders make every read and write a network round trip.
9. **Each sandbox has its own Docker image cache.** Sandboxes do not share images or layers except where the shared skills store is mounted.
10. **Virtiofs caching is on by default.** If you suspect stale reads, recreate with `DOCKER_SANDBOXES_ENABLE_VIRTIOFS_CACHE=0`.
11. **Upstream proxy support is experimental,** and only HTTP and HTTPS can be forwarded to it.
12. **UDP egress is experimental.** If a tool needs UDP, enable it and add rules; do not assume it works because TCP does.
13. **Approving a request does not retry it.** The approval applies to later connections, so run the blocked operation again.
14. **`sbx policy check network` ignores HTTP method and path.** It reports the decision for the host, which can differ from the decision for one method on that host. Use `sbx policy ls --type http` for those.
15. **`sbx policy rm` and `sbx rm` want a terminal.** In a script, pass `--force`.
16. **A `Balanced` preset is broad.** Its 194 rules cover AI providers, registries, code hosts, and common cloud services, which is convenient and not what a locked-down deployment wants.

## Ecosystem

| Resource | What it is |
|---|---|
| [docker.com/products/docker-sandboxes](https://www.docker.com/products/docker-sandboxes/) | product page and positioning |
| [docs.docker.com/ai/sandboxes](https://docs.docker.com/ai/sandboxes/) | official documentation, including architecture and security model |
| [Docker Sandboxes blog posts](https://www.docker.com/blog/docker-sandboxes-run-claude-code-and-other-coding-agents-unsupervised-but-safely/) | launch write-ups and design rationale |
| [docker/sbx-releases](https://github.com/docker/sbx-releases) | release artifacts and manual install instructions |
| [Comparing sandboxing approaches for AI agents](https://www.docker.com/blog/comparing-sandboxing-approaches-ai-agents/) | Docker's own comparison against containers and VMs |

Related labs in this repo: [bubblewrap](bubblewrap.md) for the slim, hand-built boundary, [microsandbox](microsandbox.md) for the SDK-first microVM runtime with live snapshots and branching, and [nanvix](nanvix.md) for the microVM that brings its own operating system.

## Cleanup

```sh
sbx ls                       # list sandboxes
sbx stop my-sandbox
sbx rm my-sandbox
sbx prune --dry-run          # preview removal of stopped sandboxes
sbx prune                    # remove all stopped sandboxes
sbx template ls
sbx template rm my-template:v1
sbx reset                    # clear the local image cache
```

## When to reach for it

- You want to run a coding agent unattended and treat the sandbox, not permission prompts, as the control.
- The task needs Docker inside the agent's environment.
- You want a managed workspace story (direct, clone, or mountless) without building one yourself.
- You need the same policy enforced across a team.

Reach for bubblewrap when the goal is to shrink what a single process can see, and microsandbox when you want to create machines from your own code with live snapshots. Docker Sandboxes sits at the top of the convenience curve, and charges for it in overhead and, for governance, in licensing.
