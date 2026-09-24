# inside-cottonbox-cc

Most flexible Linux sandbox for diverse AI tests (integrations, agentic infra, benchmarks, evals) is ...

**Site:** https://inside.cottonbox.cc

## Sandbox labs

Three hands-on labs, one per sandboxing approach. Each follows the same shape: what it is, how to run it, how to constrain it, and where it breaks.

1. **bubblewrap** - the slim, hand-built boundary. Namespaces and seccomp around a single process, no daemon and no root, for trimming what a process can see. [Lab](mds/bubblewrap.md)
2. **microsandbox** - the SDK-first microVM runtime. Each sandbox gets its own guest kernel and is created from your own code, with live snapshots and branching. [Lab](mds/microsandbox.md)
3. **Docker Sandboxes** - the managed, agent-first microVM. The `sbx` CLI runs coding agents unattended with a private Docker Engine, workspace modes, and a credential proxy. [Lab](mds/dockersandboxes.md)
