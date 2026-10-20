# AI Sandbox Demo Lab: MXC

A hands-on lab for Microsoft eXtension Container (MXC), the layer that sits *above* the sandbox engines. The other labs in this series each teach you one engine: bubblewrap, microsandbox, Docker Sandboxes. MXC is the wrapper framework: one policy model, and it drives whichever engine the host happens to offer.

Everything in the "Verified output" blocks was produced on this machine, on Linux, with the Rust SDK `mxc-sdk` 1.0.1, bubblewrap 0.11.1, and the `ctnb` pixi environment from this repo. The other three approaches have their own labs: [bubblewrap](bubblewrap.md), [microsandbox](microsandbox.md), and [Docker Sandboxes](dockersandboxes.md).

## What MXC is

MXC is a sandboxed code execution system for running untrusted code: model output, plugins, and tools. It is not a daemon and not a service. It is a library that links into your program, plus a set of executor binaries.

- **One policy model, many engines.** You write filesystem, network, and UI restrictions once. The host picks the backend: `bubblewrap` on Linux, `seatbelt` on macOS, `processcontainer` on Windows.
- **Typed SDKs.** Rust (`mxc-sdk`), .NET (`Microsoft.Mxc.Sdk`), and Node/TypeScript (`@microsoft/mxc-sdk`). All three are 1.0.1.
- **In-process.** The Rust SDK runs the engine inside your process. There is no sidecar to supervise.
- **Default-deny.** An omitted policy field means the most restrictive thing, not the most permissive.
- **Lifecycle optional.** Create-and-run is the simple path; provision, start, execute, stop, deprovision is the long-lived path.

Upstream project: https://github.com/microsoft/mxc

### There is no Python SDK

This is the first thing to know before you plan around it. The SDKs are Rust, .NET, and Node/TypeScript. There is no `mxc` package on PyPI that does this, and there is no conda-forge package called `mxc`.

The PyPI project named `mxc` is an unrelated 2021 package. Installing it into this repo would be a mistake, so it is deliberately absent from `pixi.lock`.

The distribution route that works is Cargo. This repo already gets Rust through pixi, and `mxc-sdk` 1.0.1 has no C library dependencies, so it builds with nothing but the toolchain:

```sh
pixi add rust slirp4netns
```

`slirp4netns` is not optional decoration. On the bubblewrap backend, MXC reaches the network through slirp, and without it the sandbox gets no connectivity at all - and the proxy-only mode is reported as unsupported.

### The policy model

Everything hangs off one request type. `ContainerRequest` carries the workload and the cross-backend restrictions:

| Field | Meaning |
|---|---|
| `command` | the program to run |
| `filesystem` | `FilesystemPolicy`: `readwrite_paths`, `readonly_paths`, `denied_paths` |
| `network` | `NetworkPolicy`: `egress`, `ingress`, `runtime_config` |
| `ui` | `UiPolicy`: `disable`, `clipboard`, `allow_input_injection` |
| `timeout_ms` | wall-clock budget for the run |
| `containment` | which backend runs it |
| `working_directory`, `environment`, `inherit_default_environment` | process-level settings |

The network section is where the interesting shape shows up. `NetworkEgressPolicy` has a `default` action, plus `allow` and `deny` rule lists. Each rule is a set of peers and a set of ports, and **a peer is a CIDR, not a hostname**:

```rust
NetworkRulePolicy {
    to: Some(vec![NetworkPeerPolicy::new("104.20.23.154/32")]),
    ports: Some(vec![NetworkPortPolicy {
        protocol: Some(NetworkProtocol::Tcp),
        port: Some(443),
        end_port: None,
    }]),
}
```

So MXC is good at "this address range on this port" and bad at "this domain name". Per-host control is the proxy's job, and the proxy is a separate runtime value (`network.runtime_config.network_proxy`).

### The backend table

`Containment` is a plain field on the request, not an option. You either take the host default or name a backend.

| Backend | Platform | Notes |
|---|---|---|
| `bubblewrap` | Linux | the Linux default. Unprivileged, no root |
| `lxc` | Linux | native LXC. Needs root or a configured subuid delegation |
| `microvm` | Linux, Windows | Nanvix. Experimental, needs the `microvm` cargo feature |
| `hyperlight` | Linux, Windows | Hyperlight plus Unikraft. Experimental |
| `processcontainer` | Windows | the Windows default. AppContainer or BaseContainer |
| `windows_sandbox` | Windows | full Windows Sandbox VM |
| `wslc` | Windows | Linux containers through the WSL Container SDK |
| `isolation_session` | Windows | an isolated user account in its own OS session |
| `seatbelt` | macOS | the macOS default. Needs macOS 15 or later |

Two of these deserve a warning label. The `microvm` and `hyperlight` backends are experimental, so the SDK refuses them unless you also pass the experimental flag - and you cannot get that flag from a config file, because it is an API parameter rather than a request field. And `--audit` mode on the executor binaries **turns off all sandbox security** for the workload it analyses. It exists so a policy author can watch what a trusted tool tries to open. Never point it at untrusted code.

Telemetry is opt-in and lives on the operation options, not on the request. Omit it and nothing is collected.

## Requirements

- Linux with user namespaces enabled, plus `bubblewrap` on PATH
- `slirp4netns` on PATH for the bubblewrap network modes
- Rust toolchain, which this repo gets from pixi

Check the host prerequisites:

```sh
bwrap --version
slirp4netns --version
unshare --user --pid echo ok
```

## Lab 1: build the demo

The demo lives in this repo, so you can read every line before you run it:

```
src/mxc-demo/Cargo.toml      # one dependency: mxc-sdk = "1.0.1"
src/mxc-demo/src/main.rs     # six subcommands, one per lab below
src/mxc-demo/Cargo.lock      # pinned, so the build is reproducible
```

Build it inside the pixi environment:

```sh
pixi run cargo build --manifest-path src/mxc-demo/Cargo.toml
```

The first build compiles the whole dependency tree: 140 packages, 15 seconds cold on this machine.

Where the build output goes matters less than you would think, and this repo has an opinion about it. The pixi environment sets `CARGO_TARGET_DIR` to `$SCRATCH/cargo-target`, so the compiler artifacts land in the scratch directory instead of inside `src/mxc-demo/`. That is about 600 MB of build output, and it has no business sitting in a working tree. Scratch is disposable: wipe it and the next build re-creates it.

## Lab 2: discover what the host can run

Before you write a policy, ask the host what it has:

```sh
pixi run cargo run --quiet --manifest-path src/mxc-demo/Cargo.toml -- host
```

Verified output on this machine:

```
supported: true
available_methods: ["bubblewrap"]
bubblewrap proxy enforcement: Supported
backend: bubblewrap tier=None capabilities=[ProxyEnforcement]
```

Four things to read out of that:

- `supported: true` means MXC can run here at all.
- `available_methods` is what the SDK itself can launch. It is narrower than "what is installed on this machine": it lists `lxc` only when the tooling is usable, and it says nothing about whether your process is privileged enough to reach it.
- `bubblewrap proxy enforcement: Supported` is the slirp4netns check. It is `Unsupported` on a host without slirp, and the reason is in the warnings list.
- `available_backends` is the wider question: every backend the host could run, with its isolation tier and capabilities. On Linux it is a single line here.

`platform_support` answers "is MXC usable", `available_backends` answers "what could it use". Call both once at startup, not in a hot loop.

## Lab 3: run something and capture the output

The simplest entry point is `v1::run`: it runs the request to completion and hands back the captured streams.

```rust
let request = ContainerRequest {
    timeout_ms: Some(20_000),
    ..ContainerRequest::new("sh -c 'echo hello-from-mxc; uname -r; id'")
};
let output = v1::run(request, Default::default())?;
```

```sh
pixi run cargo run --quiet --manifest-path src/mxc-demo/Cargo.toml -- run
```

Verified output:

```
--- default containment ---
outcome: Exited(0)
stdout: hello-from-mxc
7.0.0-38-generic
uid=1000(roro) gid=1000(roro) groups=1000(roro),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup),65534(nogroup)
```

Read that carefully, because it is the whole story of what a bubblewrap sandbox is:

- `outcome: Exited(0)` is the `WaitResult` enum. `TimedOut` is the other variant, and it means the deadline elapsed and the process is gone.
- `uname -r` reports `7.0.0-38-generic`, which is the **host** kernel. MXC on Linux gives you namespaces on the host kernel, not a guest kernel. That is the trade you make for a 5 millisecond start.
- `id` shows the same uid and gid as outside the sandbox, because the sandbox is unprivileged. What changed is the supplementary groups: they are all mapped to `65534(nogroup)`, so the sandbox holds no group privileges.

The `run` and `spawn` pair is worth internalising. `run` captures everything and returns when the process ends. `spawn` returns a live `MxcProcess` with separate pipes, so you can feed stdin, watch output while it runs, and kill it. Use `run` for batch work, `spawn` when you are driving an interactive agent.

## Lab 4: the filesystem policy

Three lists, and the order of precedence is the whole game: `denied_paths` beats `readonly_paths`, and `readwrite_paths` beats both.

```rust
let request = ContainerRequest {
    timeout_ms: Some(20_000),
    containment: Containment::Bubblewrap,
    filesystem: Some(FilesystemPolicy {
        readonly_paths: vec!["/usr".into(), "/etc".into()],
        readwrite_paths: vec!["/tmp".into()],
        denied_paths: vec!["/home".into()],
        clear_policy_on_exit: None,
    }),
    ..ContainerRequest::new("sh -c 'echo -n home:; ls /home 2>&1 | head -1; echo -n tmp:; touch /tmp/probe && echo writable; echo -n usr:; touch /usr/probe 2>&1 | head -1'")
};
```

```sh
pixi run cargo run --quiet --manifest-path src/mxc-demo/Cargo.toml -- fs
```

Verified output:

```
--- filesystem policy ---
outcome: Exited(0)
stdout: home:tmp:writable
usr:touch: cannot touch '/usr/probe': Read-only file system
```

The three results:

- `/home` is denied. It is not merely unreadable, it is masked - the directory is replaced with an empty tmpfs, so `ls /home` succeeds and prints nothing. That is the difference between "denied" and "does not exist", and it matters: a denial that returns an error tells the workload it was blocked, a mask tells it nothing is there.
- `/tmp` is writable. The sandbox gets a private tmpfs there by default.
- `/usr` is read-only. The error is the kernel's, not MXC's.

Notice what is *not* in the output. Your home directory, `/root`, `/var`, `/sys`, `/opt` are all invisible by default. The bubblewrap backend binds only a deny-by-default baseline - `/bin`, `/sbin`, the `/lib*` family, `/usr/bin`, `/usr/sbin`, `/usr/lib`, `/usr/share`, `/etc`, and the DNS stub-resolver directories - and nothing else until you ask for it. That is the same philosophy as the bubblewrap lab, expressed as a policy object instead of a command line.

One field deserves a note: `clear_policy_on_exit` defaults to `true`, which means the filesystem policy is torn down when the shell exits. Leave it alone unless you are deliberately building a persistent container.

## Lab 5: the network policy

### Default deny

Egress defaults to deny. The simplest way to say "no network" is to say it explicitly:

```rust
network: Some(NetworkPolicy {
    egress: Some(NetworkEgressPolicy {
        default: Some(NetworkAction::Deny),
        allow: None,
        deny: None,
    }),
    ingress: None,
    runtime_config: None,
}),
```

```sh
pixi run cargo run --quiet --manifest-path src/mxc-demo/Cargo.toml -- net-deny
```

Verified output:

```
--- egress denied ---
outcome: Exited(0)
stdout: code=000exit=6
stderr: curl: (6) Could not resolve host: example.com
```

Exit code 6 from curl is "could not resolve host". The sandbox has a network namespace with no route out and no resolver, so the name never becomes an address. The request failed at DNS, which is the earliest possible failure and the cheapest one.

### Allowing one address range

Now the interesting case. Peers are CIDR, so an allow rule is an address range plus a port range:

```rust
allow: Some(vec![
    NetworkRulePolicy {
        to: Some(vec![NetworkPeerPolicy::new("104.20.23.154/32")]),
        ports: Some(vec![NetworkPortPolicy {
            protocol: Some(NetworkProtocol::Tcp),
            port: Some(443),
            end_port: None,
        }]),
    },
    NetworkRulePolicy {
        to: Some(vec![NetworkPeerPolicy::new("10.0.2.3/32")]),
        ports: Some(vec![NetworkPortPolicy {
            protocol: Some(NetworkProtocol::Any),
            port: Some(53),
            end_port: None,
        }]),
    },
]),
```

```sh
pixi run cargo run --quiet --manifest-path src/mxc-demo/Cargo.toml -- net-allow 104.20.23.154/32
```

Verified output:

```
--- egress allow 104.20.23.154/32:443 and dns 10.0.2.3/32:53 ---
outcome: Exited(0)
stdout: code=200exit=0
```

HTTP 200. The address is reachable on port 443 and nothing else is.

### The DNS rule you will forget

Drop the second rule and run it again:

```sh
pixi run cargo run --quiet --manifest-path src/mxc-demo/Cargo.toml -- net-allow 104.20.23.154/32 203.0.113.9/32
```

The request is refused before it starts, with this warning:

```
WARNING: Bubblewrap pointed the sandbox at slirp's DNS forwarder 10.0.2.3 because the host resolves through a loopback nameserver, but network.egress does not admit UDP or TCP port 53 to it, so queries are dropped and names will not resolve. Add an allow rule for '10.0.2.3/32' on port 53 with protocol 'any' if the workload needs to resolve names; a resolver falls back to TCP for answers that do not fit a datagram.
```

This is the single most useful thing MXC told me during this lab, and it is worth understanding rather than memorising.

On the bubblewrap backend the sandbox network is a slirp4netns namespace. slirp forwards DNS to `10.0.2.3`, the standard slirp resolver address. Your egress policy filters *that* address too, so a policy that allows only your target address silently kills name resolution. The failure looks like "the network is broken", but the network is working exactly as configured.

The fix is the second rule: allow `10.0.2.3/32` on port 53 with protocol `any`. The `any` matters because a resolver falls back to TCP for answers that do not fit in a datagram, and a UDP-only rule breaks on the large-answer path.

This is the price of a CIDR-only policy model, and it is a real one. Your allowlist is a set of addresses, and addresses move. `104.20.23.154` was the address `example.com` resolved to on this host when the lab was written; a CDN front end can hand out a different one a minute later.

### Hostnames need a proxy

Because peers are CIDR only, per-host control is the proxy's job. Point the sandbox at a proxy with `network.runtime_config.network_proxy`, and the proxy decides what the hostname is allowed to be:

```rust
network: Some(NetworkPolicy {
    egress: Some(NetworkEgressPolicy {
        default: Some(NetworkAction::Deny),
        allow: None,
        deny: None,
    }),
    ingress: None,
    runtime_config: Some(NetworkRuntimeConfig {
        network_proxy: Some("http://127.0.0.1:8080".into()),
    }),
}),
```

On the bubblewrap backend this turns the sandbox into proxy-only mode: slirp is still there to carry the traffic, but the only reachable endpoint is the pinned proxy, and the proxy address must be localhost, `127.0.0.1`, or `[::1]`. The proxy then makes the hostname decision. That is the same shape as the microsandbox lab's proxy story, with a different vocabulary.

If you skip the proxy, you are in CIDR land, and CIDR land is a blunt instrument: the address list is the allowlist, and it drifts.

## Lab 6: an interactive terminal

An agent needs a terminal, not just pipes. `v1::spawn_with_pty` gives the sandbox a pseudo-terminal that the caller controls:

```rust
let request = ContainerRequest {
    timeout_ms: Some(30_000),
    containment: Containment::Bubblewrap,
    ..ContainerRequest::new("bash")
};
let process = v1::spawn_with_pty(request, SpawnWithPtyOptions::default())?;
let mut writer = process.take_writer()?;
writer.write_all(b"echo hello-from-pty\nexit\n")?;
writer.flush()?;
let mut reader = process.try_clone_reader()?;
let mut text = String::new();
reader.read_to_string(&mut text)?;
let outcome = process.wait()?;
```

```sh
pixi run cargo run --quiet --manifest-path src/mxc-demo/Cargo.toml -- pty
```

Verified output:

```
--- pty session ---
outcome: Exited(0)
output: echo hello-from-pty
exit
[?2004hroro@rorov:/$ echo hello-from-pty
[?2004lhello-from-pty
[?2004hroro@rorov:/$ exit
[?2004lexit
```

The prompt is the giveaway: the sandbox has a working terminal, with the host user name and a host-looking prompt, and the bracketed-paste escape sequences (`[?2004h` and `[?2004l`) that a real terminal-aware program emits. The command ran inside the sandbox and the output came back over the pty.

The size defaults to 24 rows by 80 columns, and `MxcPtyProcess::resize` changes it live when your terminal window moves.

One shell-specific trap, verified here: run the same thing with `sh` instead of `bash` and the sandbox shell fails to start:

```
outcome: Exited(2)
output: ... $ hello-from-pty
$ sh: 2: Cannot set tty process group (No such process)
```

`sh` on this host is dash, and dash turns on job control when its stdin is a terminal. Inside the bubblewrap PID namespace the job-control process group cannot be installed, the shell gives up, and the session ends with exit code 2 - after the command itself already ran. `bash` handles the same situation without complaint. If you drive a PTY session, pick a shell that survives the namespace.

## How MXC compares

| | bubblewrap | microsandbox | Docker Sandboxes | MXC |
|---|---|---|---|---|
| Role | the engine | the engine | the managed service | the wrapper over engines |
| Boundary | namespaces on the host kernel | own guest kernel | own guest kernel | whatever the host offers |
| Isolation control | command-line flags | OCI image plus policy | workspace modes plus presets | one policy object, typed |
| Start cost | milliseconds | tens to hundreds of milliseconds | seconds | milliseconds on bubblewrap, more on a VM backend |
| Network control | you build the filter | domain and group rules | preset plus scope rules | CIDR rules, or a proxy for hostnames |
| Languages | any | Python, TS, Rust, Go, Ruby | the `sbx` CLI | Rust, .NET, Node |
| Bring your own image | paths you bind | OCI images | curated images | backend-specific |
| Best at | the cheapest boundary | running untrusted code end to end | unattended agent fleets | one policy across hosts and engines |

The practical reading: MXC is what you reach for when you do not want to write the bubblewrap command line yourself, when you want the same policy to work on a Linux CI box and a Windows workstation, or when you want to escalate from a namespace sandbox to a microVM without rewriting your policy.

It also sits at a different altitude from the other three. bubblewrap, microsandbox, and Docker Sandboxes are engines, or a service built on an engine. MXC is a library that calls an engine.

## Threat model worksheet

| Threat | Covered by |
|---|---|
| The workload reads files it should not | the filesystem policy masks denied paths and mounts the rest read-only |
| The workload exfiltrates over the network | egress defaults to deny, and allow rules name address and port |
| DNS is used as an exfil channel | the resolver address needs an explicit rule, so nothing resolves unless you said so |
| The workload reaches the host loopback | the sandbox has its own network namespace; the host loopback is not bridged |
| The workload tampers with the host toolchain | the system tree is read-only, and the writable area is a private tmpfs |
| The agent runs away | `timeout_ms` on every request, and `MxcProcess::kill` for a live one |
| A confused deputy in the policy | the SDK refuses a request the backend cannot honour, instead of dropping the rule |
| Supply chain drift in the engine | pin the SDK version and the `Cargo.lock`, and read the backend warnings |

| Not covered | Why |
|---|---|
| A host kernel bug | bubblewrap shares the host kernel; that is the price of the speed |
| DNS rebinding against a CIDR allowlist | the policy pins addresses, so a name that resolves elsewhere is simply not allowed |
| An allowed address turning hostile | an address you allowed is trusted by definition, and CDNs move addresses |
| The proxy being compromised | MXC pins the proxy endpoint, it does not vouch for the proxy |
| Experimental backends | `microvm` and `hyperlight` are flagged experimental in upstream docs |
| Audit mode | `--audit` disables sandbox security entirely; it is a policy-authoring tool, not a runtime |
| The SDK's own bugs | the SDK is in your process, with your privileges |

## Gotchas

1. **There is no Python SDK.** Rust, .NET, and Node only. The PyPI project called `mxc` is unrelated and does not belong in this repo.
2. **No conda-forge package either.** `pixi add` reaches conda and PyPI, so the Rust route works because cargo comes in as a tool, not as a dependency.
3. **`slirp4netns` is not optional on Linux.** Without it the sandbox has no connectivity, and `platform_support` reports the proxy enforcement as unsupported with the reason in the warnings.
4. **A CIDR allowlist without a DNS rule resolves nothing.** The slirp forwarder at `10.0.2.3` needs an explicit rule on port 53 with protocol `any`, and the SDK tells you this in a warning if you forget.
5. **Peers are CIDR only.** There is no hostname in the rule shape. Per-host control is the proxy's job.
6. **Address lists drift.** A CDN front end can change the address you allowed. Either allow a wider range and accept the looser policy, or move to a proxy that can see the hostname.
7. **`containment` is a plain field.** `Containment::Bubblewrap` carries no configuration payload, unlike `Containment::Lxc` and `Containment::Seatbelt`, which take their own config type.
8. **A rule with no ports means no ports.** `NetworkRulePolicy.ports` and `.to` are both optional, and an empty rule matches nothing useful. Say the address and the port, every time.
9. **`--audit` turns off sandbox security.** It is for reconstructing a policy for a trusted tool. Never run untrusted code in it.
10. **Telemetry lives on the operation options, not the request.** `RunOptions`, `SpawnOptions`, and `SpawnWithPtyOptions` carry it; `ContainerRequest` does not. Omission leaves it disabled.
11. **Experimental backends need a flag that is not in the config.** The `microvm` and `hyperlight` backends are refused unless the experimental flag is passed as an API parameter, so a config file cannot grant itself that access.
12. **`sh` fails in a PTY session on this host.** dash cannot install its job-control process group inside the bubblewrap PID namespace and exits 2. Use `bash`.
13. **Ingress allow is refused on bubblewrap.** The sandbox network namespace has no inbound route, and `network.ingress.default = allow` is rejected rather than silently ignored.
14. **`run` waits, `spawn` does not.** `run` drains both streams concurrently, so an output-heavy child cannot deadlock. With `spawn`, a stream you do not take is drained and discarded.
15. **A timeout is a successful outcome.** `WaitResult::TimedOut` means the deadline elapsed and the process is gone; it is not an error, and partial output still comes back.

## Ecosystem

| Resource | What it is |
|---|---|
| [microsoft/mxc](https://github.com/microsoft/mxc) | the project, the backends, and the documentation |
| [mxc-sdk on crates.io](https://crates.io/crates/mxc-sdk) | the Rust SDK used in this lab |
| [@microsoft/mxc-sdk on npm](https://www.npmjs.com/package/@microsoft/mxc-sdk) | the Node and TypeScript SDK |
| [Microsoft.Mxc.Sdk on NuGet](https://www.nuget.org/packages/Microsoft.Mxc.Sdk) | the .NET SDK |
| [API reference](https://github.com/microsoft/mxc/blob/main/docs/api-reference/README.md) | the typed V1 contract for every SDK |
| [Sandbox policy design](https://github.com/microsoft/mxc/blob/main/docs/sandbox-policy/v1/policy.md) | why the policy model is shaped the way it is |

The Nanvix lab in this series covers the `microvm` backend's guest side: the purpose-built micro-VM that MXC can drive experimentally, and the multikernel OS inside it.

## Cleanup

The build output is disposable scratch, so removing it is a directory delete:

```sh
rm -rf scratch/cargo-target
```

To drop Rust and slirp from the pixi environment:

```sh
pixi remove rust slirp4netns
```

Nothing else is left behind. MXC has no daemon, no runtime directory, and no host state.

## Where this goes next

- Put the policy in one place and generate the backend-specific configuration from it, instead of hand-writing flags per host.
- Give the agent a proxy endpoint and let the proxy own the hostname allowlist, so the address list stops drifting.
- Pair this with the [microsandbox lab](microsandbox.md): bubblewrap for the cheap case, a microVM when the code under test is the threat.
