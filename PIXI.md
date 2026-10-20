# Why pixi

This repo runs its labs out of a pixi environment: one manifest, one lockfile, one command to enter it. This file explains why, because the answer is more interesting than "it is convenient".

## The short version

Every lab in this series needs a different toolchain, and they do not get along:

| Lab | What it needs |
|---|---|
| bubblewrap | the system `bwrap` binary, and bash |
| microsandbox | Python 3.12 and the `microsandbox` SDK |
| nanvix | nothing but a pinned release bundle on disk |
| MXC | Rust and cargo for the SDK, plus `slirp4netns` for the bubblewrap network modes |

Installing those into a system Python and a shared `PATH` would give every lab a different answer on every machine, and it would leave the reader's environment worse than it found it. pixi puts them in one place instead: `pixi.toml` says what is needed, `pixi.lock` pins exactly what that resolves to, and `pixi run` puts the result on the `PATH` for a single command.

## The lockfile is the point

The labs in this repo all argue for the same property: the boundary has to be pinned, auditable, and reproducible. A policy that means something different on Tuesday than it meant on Monday is not a boundary, it is a suggestion.

The tooling that builds the boundary deserves the same treatment. `pixi.lock` records the exact conda and PyPI resolution, so the environment that runs the microsandbox SDK today is the environment that runs it next month. The repo does not even depend on the host's system Python being a particular version.

That is the whole argument for a lockfile-driven environment manager over a `pip install` in a README.

## It keeps the boundary honest

There is a second reason, and it is the one that matters for a sandboxing repo.

Everything needed to *run* a lab lives in one directory, outside every sandbox. The tool that builds the microVM is outside the microVM. The compiler that builds the MXC SDK is outside the MXC sandbox. The Python that drives microsandbox is outside the microsandbox guest.

A sandbox that can see the toolchain that made it is not much of a sandbox. So the environment is deliberately a separate thing from the guest, and the labs never mix the two up.

## It is disposable

The environment is a build artifact, not a source of truth. `pixi.toml` and `pixi.lock` are the source of truth, and the environment can be thrown away:

```sh
rm -rf .pixi
pixi install
```

That restores it exactly, from the lockfile, with nothing left over on the host. The same goes for the bulky artifacts: the cargo build output and the Nanvix bundle live in `$SCRATCH`, which is a directory on disk that nobody has to think about, and `$TMPDIR` points at a tmpfs for the small stuff.

For an archive that has to work without a package server, copy `pixi.toml` and `pixi.lock` and re-install on the target machine. Do not copy `.pixi` and expect it to run: the environment records its absolute prefix, so a verbatim copy of the folder does not carry over.

## What pixi adds beyond the lockfile

- **Speed.** The solver is written in Rust and the downloads run in parallel, so resolving and materialising an environment is quick rather than the minutes a conda solve of the same set can take. That matters here because the labs are meant to be run, not admired.
- **One manifest, several platforms.** `pixi.toml` declares its target platforms, so the same definition can cover a Linux CI box and a workstation. This repo pins `linux-64`, because that is what the labs were verified on.
- **Several environments from one project.** Features and an `[environments]` table let a project define more than one dependency set, and you install only the one you activate. This repo needs exactly one, so it has the plain `default` environment.

## What is in it today

The environment is named `ctnb`, it targets `linux-64`, and it pulls from conda-forge:

```toml
[dependencies]
python = "3.12.*"
rust = ">=1.99.0,<1.100"
slirp4netns = ">=1.3.6,<2"

[pypi-dependencies]
microsandbox = ">=0.7.2, <0.8"
```

Three things worth noting about that list:

- **`slirp4netns` is not optional decoration.** On the bubblewrap backend, MXC reaches the network through slirp. Without it the sandbox gets no connectivity at all, and the SDK reports the proxy enforcement as unsupported.
- **`rust` arrives as a tool, not as a library.** pixi reaches conda and PyPI, not crates.io, so the MXC SDK is built by cargo inside the environment rather than installed into it.
- **`microsandbox` comes from PyPI** because it has no conda-forge package. Its wheel bundles a matching `msb` runtime and `libkrunfw`, so no separate download step is needed.

The tasks are thin wrappers, so the raw command is always one step away:

```toml
[tasks]
nanvix-fetch = "scripts/nanvix-fetch.sh"
nanvix = { cmd = "scripts/nanvix-run.sh", depends-on = ["nanvix-fetch"] }
nanvix-shell = { cmd = "scripts/nanvix-run.sh --shell", depends-on = ["nanvix-fetch"] }
```

## How to use it

```sh
pixi shell                # enter the environment interactively
pixi run nanvix           # fetch the bundle if needed, then run a workload
pixi run nanvix-shell     # the guest REPL
pixi run cargo build --manifest-path src/mxc-demo/Cargo.toml
pixi add --pypi something # add to the environment and update the lockfile
```

Every lab in `labs/` assumes the environment is active. If a command in a lab looks like `pixi run cargo ...`, it is because the cargo binary belongs to the environment, not to your shell.

## What pixi does not do here

- **It is not a sandbox.** It confines nothing. The labs confine.
- **It does not replace the host tools the labs need.** `bwrap` comes from the distro, `/dev/kvm` comes from the kernel, and Docker comes from Docker.
- **It does not hold the Nanvix bundle.** That is 560 MB of runtime, and it belongs on disk in `$SCRATCH`, not in an environment directory.
- **It is not the only way to run the labs.** The labs state the raw commands as well, so a reader with their own setup can follow along. pixi is the reproducible path, not a gate.

## See also

- [AGENTS.md](AGENTS.md) for the conventions this repo follows inside the environment, including `$SCRATCH` and `$TMPDIR`.
- [the microsandbox lab](labs/microsandbox.md) for the lab that installs its SDK with `pixi add --pypi`.
- [the MXC lab](labs/mxc.md) for the lab that installs a Rust toolchain with `pixi add rust slirp4netns`.
- [the nanvix lab](labs/nanvix.md) for the lab that needs no packages at all, only a pinned bundle.
