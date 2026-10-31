use std::collections::HashMap;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use bollard::Docker;
use bollard::query_parameters::StatsOptionsBuilder;
use futures::stream::{self, StreamExt, TryStreamExt};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use tokio::runtime::Runtime;
use tokio::time::timeout;

// One runtime for the whole process instead of one per request
static RUNTIME: OnceLock<Runtime> = OnceLock::new();

// Same cap as the Python fallback, so hosts with hundreds of containers don't
// flood the Docker daemon with simultaneous stats requests
const MAX_CONCURRENT_REQUESTS: usize = 32;

// A hung daemon or container must not hang the request forever
const DOCKER_TIMEOUT: Duration = Duration::from_secs(10);

// Gap between the two samples taken for engines that return only one (Podman)
const PODMAN_SAMPLE_INTERVAL: Duration = Duration::from_secs(1);

fn runtime() -> PyResult<&'static Runtime> {
    if let Some(rt) = RUNTIME.get() {
        return Ok(rt);
    }
    // The work is all I/O wait, so a couple of threads is plenty; the default
    // (one per CPU core) would park dozens of idle threads on big hosts
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    Ok(RUNTIME.get_or_init(|| rt))
}

/// Fetch stats for all running containers concurrently.
///
/// `host` is the engine's API address (e.g. unix:///run/podman/podman.sock);
/// without it DOCKER_HOST or the default Docker socket is used.
///
/// Returns the same list of dicts as the Python implementation in dStats/views.py:
/// name, cpu_percent, memory_usage, network_io.
#[pyfunction]
#[pyo3(signature = (host=None))]
fn get_container_stats_parallel(
    py: Python<'_>,
    host: Option<String>,
) -> PyResult<Vec<HashMap<&'static str, String>>> {
    let rt = runtime()?;
    // Release the GIL while waiting on the engine
    let stats = py
        .detach(|| rt.block_on(fetch_all_stats(host)))
        .map_err(PyRuntimeError::new_err)?;

    Ok(stats
        .into_iter()
        .map(|stat| {
            HashMap::from([
                ("name", stat.name),
                ("cpu_percent", stat.cpu_percent),
                ("memory_usage", stat.memory_usage),
                ("network_io", stat.network_io),
            ])
        })
        .collect())
}

struct ContainerStat {
    name: String,
    cpu_percent: String,
    memory_usage: String,
    network_io: String,
}

impl ContainerStat {
    fn unavailable(name: String) -> Self {
        Self {
            name,
            cpu_percent: "N/A".to_string(),
            memory_usage: "N/A".to_string(),
            network_io: "N/A".to_string(),
        }
    }
}

async fn fetch_all_stats(host: Option<String>) -> Result<Vec<ContainerStat>, String> {
    let docker = match host {
        Some(host) => Docker::connect_with_host(&host),
        // Honours DOCKER_HOST like docker.from_env() does
        None => Docker::connect_with_defaults(),
    }
    .map_err(|e| e.to_string())?;

    // Running containers only, same as client.containers.list()
    let containers = timeout(DOCKER_TIMEOUT, docker.list_containers(None))
        .await
        .map_err(|_| "Timed out listing containers".to_string())?
        .map_err(|e| e.to_string())?;

    // buffered() keeps the original container order, like the Python fallback
    Ok(stream::iter(containers)
        .map(|container| {
            let docker = docker.clone();
            let id = container.id.unwrap_or_default();
            let name = container
                .names
                .and_then(|names| names.into_iter().next())
                .unwrap_or_default()
                .trim_start_matches('/')
                .to_string();
            fetch_single_stat(docker, id, name)
        })
        .buffered(MAX_CONCURRENT_REQUESTS)
        .collect()
        .await)
}

async fn fetch_single_stat(docker: Docker, id: String, name: String) -> ContainerStat {
    let Some(mut stat) = sample_stats(&docker, &id).await else {
        return ContainerStat::unavailable(name);
    };

    let total = |s: Option<&bollard::models::ContainerCpuStats>| {
        s.and_then(|s| s.cpu_usage.as_ref())
            .and_then(|u| u.total_usage)
            .unwrap_or(0)
    };

    // Docker samples twice for stream=false and fills precpu_stats; Podman returns a
    // single sample with it empty, so take the second sample ourselves
    let has_previous = stat
        .precpu_stats
        .as_ref()
        .and_then(|p| p.system_cpu_usage)
        .is_some_and(|usage| usage > 0);

    let cpu_percent = if has_previous {
        let (cpu, precpu) = (stat.cpu_stats.as_ref(), stat.precpu_stats.as_ref());
        let cpu_delta = total(cpu).saturating_sub(total(precpu)) as f64;
        let system_delta = cpu
            .and_then(|c| c.system_cpu_usage)
            .unwrap_or(0)
            .saturating_sub(precpu.and_then(|p| p.system_cpu_usage).unwrap_or(0))
            as f64;
        let online_cpus = cpu.and_then(|c| c.online_cpus).unwrap_or(1) as f64;
        if system_delta > 0.0 {
            (cpu_delta / system_delta) * 100.0 * online_cpus
        } else {
            0.0
        }
    } else {
        // Podman's system_cpu_usage isn't comparable to Docker's, so measure CPU time
        // against wall-clock time between our two samples, like `podman stats` does
        let first_total = total(stat.cpu_stats.as_ref());
        let started = Instant::now();
        tokio::time::sleep(PODMAN_SAMPLE_INTERVAL).await;
        let Some(second) = sample_stats(&docker, &id).await else {
            return ContainerStat::unavailable(name);
        };
        let elapsed_ns = started.elapsed().as_nanos() as f64;
        stat = second;
        let cpu_delta = total(stat.cpu_stats.as_ref()).saturating_sub(first_total) as f64;
        cpu_delta / elapsed_ns * 100.0
    };

    let (mem_usage, mem_limit) = stat
        .memory_stats
        .as_ref()
        .map(|mem| (mem.usage.unwrap_or(0) as f64, mem.limit.unwrap_or(1) as f64))
        .unwrap_or((0.0, 1.0));
    let mem_percent = (mem_usage / mem_limit) * 100.0;
    let mem_mb = mem_usage / (1024.0 * 1024.0);

    let (network_in, network_out) = stat
        .networks
        .iter()
        .flat_map(|networks| networks.values())
        .fold((0u64, 0u64), |(rx, tx), net| {
            (
                rx + net.rx_bytes.unwrap_or(0),
                tx + net.tx_bytes.unwrap_or(0),
            )
        });

    ContainerStat {
        name,
        cpu_percent: format!("{:.2}%", cpu_percent),
        memory_usage: format!("{:.2} MB ({:.2}%)", mem_mb, mem_percent),
        network_io: format!(
            "IN: {:.2} KB / OUT: {:.2} KB",
            network_in as f64 / 1024.0,
            network_out as f64 / 1024.0
        ),
    }
}

async fn sample_stats(
    docker: &Docker,
    id: &str,
) -> Option<bollard::models::ContainerStatsResponse> {
    // stream=false: Docker takes two samples so precpu_stats is populated; with
    // streaming the first sample has empty precpu_stats and the CPU % is wrong
    let options = StatsOptionsBuilder::default()
        .stream(false)
        .one_shot(false)
        .build();
    match timeout(DOCKER_TIMEOUT, docker.stats(id, Some(options)).try_next()).await {
        Ok(Ok(Some(stat))) => Some(stat),
        _ => None,
    }
}

#[pymodule]
#[pyo3(name = "_rust")]
fn dstats_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_container_stats_parallel, m)?)?;
    Ok(())
}
