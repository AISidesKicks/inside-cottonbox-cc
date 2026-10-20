# inside-cottonbox-cc

Most flexible Linux sandbox for diverse AI tests (integrations, agentic infra, benchmarks, evals) is ...

**Site:** [inside.cottonbox.cc](https://inside.cottonbox.cc)

## Sandbox labs

Three hands-on labs, one per sandboxing approach. Each follows the same shape: what it is, how to run it, how to constrain it, and where it breaks.

1. **bubblewrap** - the slim, hand-built boundary. Namespaces and seccomp around a single process, no daemon and no root, for trimming what a process can see. [bubblewrap lab](labs/bubblewrap.md)
2. **microsandbox** - the SDK-first microVM runtime. Each sandbox gets its own guest kernel and is created from your own code, with live snapshots and branching. [microsandbox lab](labs/microsandbox.md)
3. **Docker Sandboxes** - the managed, agent-first microVM. The `sbx` CLI runs coding agents unattended with a private Docker Engine, workspace modes, and a credential proxy. [Docker Sandboxes lab](labs/dockersandboxes.md)

One layer above all three sits **MXC** (Microsoft eXecution Container), a higher wrapper framework: it drives an engine behind one policy model, so the same filesystem, network, and UI rules work whether the host offers bubblewrap, LXC, a microVM, or hyperlight. [MXC lab](labs/mxc.md)

