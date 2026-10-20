use std::io::{Read, Write};

use mxc_sdk::v1::{
    self, Containment, ContainerRequest, FilesystemPolicy, NetworkAction, NetworkEgressPolicy,
    NetworkPeerPolicy, NetworkPolicy, NetworkPortPolicy, NetworkProtocol, NetworkRulePolicy,
    SpawnWithPtyOptions,
};

fn show(label: &str, output: &mxc_sdk::v1::ExecutionResult) {
    println!("--- {label} ---");
    println!("outcome: {:?}", output.outcome);
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if !stdout.is_empty() {
        println!("stdout: {stdout}");
    }
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !stderr.is_empty() {
        println!("stderr: {stderr}");
    }
    for warning in &output.warnings {
        println!("warning: {warning}");
    }
}

fn host() {
    let support = v1::platform_support();
    println!("supported: {}", support.is_supported);
    if let Some(reason) = &support.reason {
        println!("reason: {reason}");
    }
    println!("available_methods: {:?}", support.available_methods);
    if let Some(network) = &support.bubblewrap_network {
        println!("bubblewrap proxy enforcement: {:?}", network.proxy_enforcement);
        for warning in &network.warnings {
            println!("bubblewrap warning: {warning}");
        }
    }
    for backend in v1::available_backends() {
        println!(
            "backend: {} tier={:?} capabilities={:?}",
            backend.backend, backend.tier, backend.capabilities
        );
        for warning in &backend.warnings {
            println!("  warning: {warning}");
        }
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let request = ContainerRequest {
        timeout_ms: Some(20_000),
        ..ContainerRequest::new("sh -c 'echo hello-from-mxc; uname -r; id'")
    };
    let output = v1::run(request, Default::default())?;
    show("default containment", &output);
    Ok(())
}

fn filesystem() -> Result<(), Box<dyn std::error::Error>> {
    let request = ContainerRequest {
        timeout_ms: Some(20_000),
        containment: Containment::Bubblewrap,
        filesystem: Some(FilesystemPolicy {
            readonly_paths: vec!["/usr".into(), "/etc".into()],
            readwrite_paths: vec!["/tmp".into()],
            denied_paths: vec!["/home".into()],
            clear_policy_on_exit: None,
        }),
        ..ContainerRequest::new(
            "sh -c 'echo -n home:; ls /home 2>&1 | head -1; \
             echo -n tmp:; touch /tmp/probe && echo writable; \
             echo -n usr:; touch /usr/probe 2>&1 | head -1'",
        )
    };
    let output = v1::run(request, Default::default())?;
    show("filesystem policy", &output);
    Ok(())
}

fn network_deny() -> Result<(), Box<dyn std::error::Error>> {
    let request = ContainerRequest {
        timeout_ms: Some(20_000),
        containment: Containment::Bubblewrap,
        network: Some(NetworkPolicy {
            egress: Some(NetworkEgressPolicy {
                default: Some(NetworkAction::Deny),
                allow: None,
                deny: None,
            }),
            ingress: None,
            runtime_config: None,
        }),
        ..ContainerRequest::new(
            "sh -c 'curl -sS -m 8 -o /dev/null -w code=%{http_code} https://example.com; echo exit=$?'",
        )
    };
    let output = v1::run(request, Default::default())?;
    show("egress denied", &output);
    Ok(())
}

fn network_allow(cidr: &str, dns_cidr: &str) -> Result<(), Box<dyn std::error::Error>> {
    let request = ContainerRequest {
        timeout_ms: Some(30_000),
        containment: Containment::Bubblewrap,
        network: Some(NetworkPolicy {
            egress: Some(NetworkEgressPolicy {
                default: Some(NetworkAction::Deny),
                allow: Some(vec![
                    NetworkRulePolicy {
                        to: Some(vec![NetworkPeerPolicy::new(cidr)]),
                        ports: Some(vec![NetworkPortPolicy {
                            protocol: Some(NetworkProtocol::Tcp),
                            port: Some(443),
                            end_port: None,
                        }]),
                    },
                    NetworkRulePolicy {
                        to: Some(vec![NetworkPeerPolicy::new(dns_cidr)]),
                        ports: Some(vec![NetworkPortPolicy {
                            protocol: Some(NetworkProtocol::Any),
                            port: Some(53),
                            end_port: None,
                        }]),
                    },
                ]),
                deny: None,
            }),
            ingress: None,
            runtime_config: None,
        }),
        ..ContainerRequest::new(
            "sh -c 'curl -sS -m 10 -o /dev/null -w code=%{http_code} https://example.com; echo exit=$?'",
        )
    };
    let output = v1::run(request, Default::default())?;
    show(&format!("egress allow {cidr}:443 and dns {dns_cidr}:53"), &output);
    Ok(())
}

fn terminal() -> Result<(), Box<dyn std::error::Error>> {
    let request = ContainerRequest {
        timeout_ms: Some(30_000),
        containment: Containment::Bubblewrap,
        ..ContainerRequest::new("bash")
    };
    let process = v1::spawn_with_pty(request, SpawnWithPtyOptions::default())?;
    {
        let mut writer = process.take_writer()?;
        writer.write_all(b"echo hello-from-pty\nexit\n")?;
        writer.flush()?;
    }
    let mut reader = process.try_clone_reader()?;
    let mut text = String::new();
    reader.read_to_string(&mut text)?;
    let outcome = process.wait()?;
    println!("--- pty session ---");
    println!("outcome: {outcome:?}");
    println!("output: {}", text.trim());
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("host") => host(),
        Some("run") => run()?,
        Some("fs") => filesystem()?,
        Some("net-deny") => network_deny()?,
        Some("net-allow") => network_allow(
            args.get(1).map(String::as_str).unwrap_or("0.0.0.0/0"),
            args.get(2).map(String::as_str).unwrap_or("10.0.2.3/32"),
        )?,
        Some("pty") => terminal()?,
        other => {
            eprintln!(
                "usage: mxc-demo <host|run|fs|net-deny|net-allow [cidr] [dns-cidr]|pty>"
            );
            std::process::exit(if other.is_some() { 2 } else { 0 });
        }
    }
    Ok(())
}
