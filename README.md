# inside-cottonbox-cc

Most flexible Linux sandbox for diverse AI tests (integrations, agentic infra, benchmarks, evals) is ...

**Site:** [inside.cottonbox.cc](https://inside.cottonbox.cc)

## Sandbox labs

Four hands-on labs, three sandboxing approaches. Each follows the same shape: what it is, how to run it, how to constrain it, and where it breaks.

1. **Namespaces on the host kernel** - a boundary made of kernel namespaces around a process.
   - **bubblewrap** - the slim, hand-built boundary. Namespaces and seccomp around a single process, no daemon and no root, for trimming what a process can see. [bubblewrap lab](labs/bubblewrap.md)
2. **A microVM per workload** - a boundary made of hardware virtualization, with its own guest kernel.
   - **microsandbox** - the SDK-first microVM runtime. Each sandbox gets its own Linux guest kernel and is created from your own code, with live snapshots and branching. [microsandbox lab](labs/microsandbox.md)
   - **nanvix** - the same approach with a different guest OS. A purpose-built microkernel, so the guest is not Linux, the workload has to be ported, and the network syscalls are blocked outright. [nanvix lab](labs/nanvix.md)
   - **Docker Sandboxes** - the managed, agent-first microVM. The `sbx` CLI runs coding agents unattended with a private Docker Engine, workspace modes, and a credential proxy. [Docker Sandboxes lab](labs/dockersandboxes.md)
3. **A policy layer over the engines** - one set of rules, written once, that any engine can enforce.
   - **MXC** (Microsoft eXecution Container) - a higher wrapper framework that drives an engine behind one policy model, so the same filesystem, network, and UI rules work whether the host offers bubblewrap, LXC, a microVM, or hyperlight. [MXC lab](labs/mxc.md)

The labs run out of a pixi environment, one manifest and one lockfile for the Python, Rust, and slirp4netns the labs need. [Why pixi](PIXI.md).

