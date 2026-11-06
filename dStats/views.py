import asyncio
import docker
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decouple import config
from dataclasses import asdict, dataclass
from typing import List, Dict
import random
from graphviz import ExecutableNotFound, Graph
import base64
from io import BytesIO
from django.views.generic import TemplateView
from asgiref.sync import sync_to_async
from django.http import JsonResponse, StreamingHttpResponse
from django.core.cache import cache
from django.contrib.auth import authenticate, login
from dStats.settings import is_auth_enabled
from dStats.engines import (
    ENGINE_LABELS,
    START_HINTS,
    EngineUnavailable,
    configured_engines,
    engine_names,
)
from django.contrib.auth.models import User

# Native accelerator, present in the platform wheels; pure-Python installs use the fallback below
try:
    from dStats import _rust
except ImportError:
    _rust = None

# Seconds before a Docker API call is abandoned, so a hung daemon can't hang requests forever
DOCKER_TIMEOUT = 10

# Gap between the two samples taken for engines that return only one (Podman)
PODMAN_SAMPLE_INTERVAL = 1

LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 300


class SharedResult:
    """Share one computed result between all requests for `ttl` seconds.

    Every open browser tab polls once a second; without this each tab would trigger
    its own round of Docker API calls. Concurrent callers wait for the computation
    already in flight instead of starting another one.
    """

    def __init__(self, ttl):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._value = None
        self._computed_at = 0.0

    def get(self, compute):
        with self._lock:
            if self._value is None or time.monotonic() - self._computed_at >= self.ttl:
                self._value = compute()
                self._computed_at = time.monotonic()
            return self._value


STATS_RESULT = SharedResult(ttl=1.0)
GRAPH_RESULT = SharedResult(ttl=1.0)

logger = logging.getLogger(__name__)


class Broadcaster:
    """Run `compute` once per `interval` while anyone is listening and push each
    result to every listener.

    Docker is queried at the same rate whether one browser or a hundred are
    connected, and not at all when nobody is.
    """

    def __init__(self, compute, interval=1.0):
        self.compute = compute
        self.interval = interval
        self._listeners = set()
        self._latest = None
        self._task = None
        self._failing = False

    async def listen(self):
        # maxsize=1: a slow client only ever gets the newest result, never a backlog
        queue = asyncio.Queue(maxsize=1)
        if self._latest is not None:
            queue.put_nowait(self._latest)
        self._listeners.add(queue)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        try:
            while True:
                yield await queue.get()
        finally:
            self._listeners.discard(queue)

    async def _run(self):
        loop = asyncio.get_running_loop()
        while self._listeners:
            started = loop.time()
            try:
                # Off the event loop: the Docker calls and graphviz are blocking
                self._latest = await sync_to_async(
                    self.compute, thread_sensitive=False
                )()
                self._failing = False
            except EngineUnavailable as e:
                # Already logged once per outage; tell the page instead of going quiet
                self._latest = {"error": str(e)}
            except Exception:
                if not self._failing:
                    logger.exception("Collecting dashboard data failed")
                self._failing = True
                self._latest = {"error": "Collecting data failed; see the server log."}
            for queue in self._listeners:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(self._latest)
            await asyncio.sleep(max(0.0, self.interval - (loop.time() - started)))
        # Don't serve stale data to whoever connects next
        self._latest = None


@dataclass
class Network:
    name: str
    gateway: str
    internal: bool
    isolated: bool
    color: str


@dataclass
class Interface:
    endpoint_id: str
    address: str
    aliases: List[str]
    network: str = ""


@dataclass
class PortMapping:
    internal: int
    external: int
    protocol: str


@dataclass
class Container:
    container_id: str
    name: str
    interfaces: List[Interface]
    ports: List[PortMapping]


@dataclass
class Link:
    container_id: str
    endpoint_id: str
    network_name: str


COLORS = [
    "#1f78b4",
    "#33a02c",
    "#e31a1c",
    "#ff7f00",
    "#6a3d9a",
    "#b15928",
    "#a6cee3",
    "#b2df8a",
    "#fdbf6f",
    "#cab2d6",
    "#ffff99",
]
HOST_NETWORK_COLOR = "#808080"


def color_sequence():
    """Fresh palette for each graph, so network colors stay stable between refreshes."""
    yield from COLORS
    while True:
        yield "#%06x" % random.randint(0, 0xFFFFFF)


# Engines currently unreachable, so each outage is logged once rather than every second
_unreachable_engines = set()


def collect_from_engines(fetch, name=None):
    """Run fetch(engine) for the named engine, or for every configured engine at once.

    Returns (engine, result) pairs. With several engines, one being down only
    drops its part; EngineUnavailable is raised only if every engine fails.
    """
    engines = [e for e in configured_engines() if name is None or e.name == name]
    if not engines:
        raise ValueError(f"Engine {name!r} is not enabled")

    with ThreadPoolExecutor(max_workers=len(engines)) as pool:
        futures = [(engine, pool.submit(fetch, engine)) for engine in engines]

    results, errors = [], []
    for engine, future in futures:
        try:
            results.append((engine, future.result()))
        except Exception as e:
            label = ENGINE_LABELS[engine.name]
            errors.append(
                EngineUnavailable(
                    f"Cannot reach {label} at {engine.url}. {START_HINTS[engine.name]}"
                )
            )
            if engine.name not in _unreachable_engines:
                _unreachable_engines.add(engine.name)
                logger.warning("Cannot reach %s at %s: %s", label, engine.url, e)
        else:
            if engine.name in _unreachable_engines:
                _unreachable_engines.discard(engine.name)
                logger.warning(
                    "%s at %s is reachable again",
                    ENGINE_LABELS[engine.name],
                    engine.url,
                )
    if not results:
        raise errors[0]
    return results


class DockerStatsView(TemplateView):
    template_name = "dStats/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["auth_enabled"] = is_auth_enabled()
        # The navbar names the engine, or offers a toggle when several are enabled
        context["engines"] = [
            {"name": name, "label": ENGINE_LABELS[name]} for name in engine_names()
        ]
        return context

    def get_network_data(self, engine):
        client = docker.DockerClient(base_url=engine.url, timeout=DOCKER_TIMEOUT)
        networks = self.get_networks(client)
        containers, links = self.get_containers(client)
        return networks, containers, links

    def get_graph_data(self, engine=None):
        """Topology for the interactive graph: container and network nodes, and an
        edge for every container's connection to a network."""
        results = collect_from_engines(self.get_network_data, engine)
        multiple = len(results) > 1
        nodes, edges = [], []

        for engine, (networks, containers, links) in results:
            # IDs carry the engine when combined, so both can have e.g. a "bridge" network
            prefix = f"{engine.name}:" if multiple else ""
            # Only networks something is attached to; skips Docker's empty none/host/bridge
            used = {
                link.network_name
                for link in links
                if link.network_name in networks and link.network_name != "none"
            }

            for net in networks.values():
                if net.name in used:
                    nodes.append(
                        {
                            "data": {
                                "id": f"{prefix}net:{net.name}",
                                "kind": "network",
                                "name": net.name,
                                "subnet": net.gateway,
                                "internal": net.internal,
                                "isolated": net.isolated,
                            }
                        }
                    )

            for container in containers:
                nodes.append(
                    {
                        "data": {
                            "id": f"{prefix}ctr:{container.container_id}",
                            "kind": "container",
                            "name": container.name,
                            # host port -> container port, like `docker ps`
                            "ports": [
                                f"{p.external}\u2192{p.internal}/{p.protocol}"
                                for p in container.ports
                            ],
                            "interfaces": [
                                {
                                    "network": i.network,
                                    "address": i.address,
                                    "aliases": i.aliases or [],
                                }
                                for i in container.interfaces
                            ],
                        }
                    }
                )

            for link in links:
                if link.network_name in used:
                    edges.append(
                        {
                            "data": {
                                "id": f"{prefix}link:{link.container_id}:{link.network_name}",
                                "source": f"{prefix}ctr:{link.container_id}",
                                "target": f"{prefix}net:{link.network_name}",
                                "network": link.network_name,
                            }
                        }
                    )

        return {"nodes": nodes, "edges": edges}

    def generate_network_graph(self, engine=None):
        results = collect_from_engines(self.get_network_data, engine)
        # Only a combined graph (the JSON API without an engine) needs engine labels
        multiple = len(results) > 1
        colors = color_sequence()

        g = Graph(
            comment="Docker Network Graph",
            engine="sfdp",
            format="png",
            graph_attr={
                "splines": "true",
                "overlap": "false",
                "nodesep": "2.0",
                "ranksep": "2.0",
            },
        )

        for engine, (networks, containers, links) in results:
            # Node IDs carry the engine, so both engines can have e.g. a "host" network
            prefix = f"{engine.name}_"
            suffix = f" ({engine.name})" if multiple else ""

            for network in networks.values():
                if network.color is None:
                    network.color = next(colors)
                self.draw_network(g, network, prefix, suffix)

            for container in containers:
                self.draw_container(g, container, prefix, suffix)

            for link in links:
                # Skip "none" and networks that weren't listed (e.g. no IPAM config)
                if link.network_name != "none" and link.network_name in networks:
                    self.draw_link(g, networks, link, prefix)

        # Convert graph to base64 image
        img_data = g.pipe()
        encoded_img = base64.b64encode(img_data).decode("utf-8")
        return encoded_img

    def get_networks(self, client):
        networks = {}
        for net in sorted(client.networks.list(), key=lambda k: k.name):
            try:
                config = net.attrs["IPAM"]["Config"]
                gateway = config[0]["Subnet"] if config else "0.0.0.0"
            except (KeyError, IndexError):
                continue

            internal = net.attrs.get("Internal", False)
            isolated = (
                net.attrs.get("Options", {}).get(
                    "com.docker.network.bridge.enable_icc", "true"
                )
                == "false"
            )

            # Colors are assigned while drawing, so they're consistent across engines
            networks[net.name] = Network(net.name, gateway, internal, isolated, None)

        networks["host"] = Network("host", "0.0.0.0", False, False, HOST_NETWORK_COLOR)
        return networks

    def get_containers(self, client):
        containers = []
        links = []

        for container in client.containers.list():
            interfaces = []
            ports = []

            for net_name, net_info in container.attrs["NetworkSettings"][
                "Networks"
            ].items():
                endpoint_id = net_info["EndpointID"]
                aliases = net_info.get("Aliases", [])
                interfaces.append(
                    Interface(endpoint_id, net_info["IPAddress"], aliases, net_name)
                )
                links.append(Link(container.id, endpoint_id, net_name))

            port_mappings = container.attrs["NetworkSettings"]["Ports"]
            if port_mappings:
                for container_port, host_ports in port_mappings.items():
                    if host_ports:
                        for host_port in host_ports:
                            internal_port, protocol = container_port.split("/")
                            ports.append(
                                PortMapping(
                                    int(internal_port),
                                    int(host_port["HostPort"]),
                                    protocol,
                                )
                            )

            containers.append(
                Container(container.id, container.name, interfaces, ports)
            )

        return containers, links

    def draw_network(self, g: Graph, net: Network, prefix="", suffix=""):
        label = f"{{<gw_iface> {net.gateway} | {net.name}{suffix}"
        if net.internal:
            label += " | Internal"
        if net.isolated:
            label += " | Containers isolated"
        label += "}"

        g.node(
            f"network_{prefix}{net.name}",
            shape="record",
            label=label,
            fillcolor=net.color,
            style="filled",
        )

    def draw_container(self, g: Graph, c: Container, prefix="", suffix=""):
        iface_labels = []
        for iface in c.interfaces:
            if iface.aliases:
                iface_labels.append(f"{iface.address} ({', '.join(iface.aliases)})")
            else:
                iface_labels.append(iface.address)

        port_labels = []
        for port in c.ports:
            port_labels.append(f"{port.internal}->{port.external}/{port.protocol}")

        label = f"{c.name}{suffix}\\n"
        label += "Interfaces:\\n" + "\\n".join(iface_labels)
        if port_labels:
            label += "\\nPorts:\\n" + "\\n".join(port_labels)

        g.node(
            f"container_{prefix}{c.container_id}",
            shape="box",
            label=label,
            fillcolor="#ff9999",
            style="filled",
        )

    def draw_link(self, g: Graph, networks: Dict[str, Network], link: Link, prefix=""):
        g.edge(
            f"container_{prefix}{link.container_id}",
            f"network_{prefix}{link.network_name}",
            color=networks[link.network_name].color,
        )

    def get_container_stats(self, engine=None):
        stats = []
        for engine, rows in collect_from_engines(self.get_engine_stats, engine):
            for row in rows:
                row["engine"] = engine.name
            stats.extend(rows)
        return stats

    def get_engine_stats(self, engine):
        if _rust is not None:
            try:
                return _rust.get_container_stats_parallel(engine.url)
            except Exception as e:
                # Debug level: an unreachable engine fails here every second
                logger.debug("Rust stats failed for %s: %s", engine.name, e)

        # stats(stream=False) blocks ~1-2s per container while the daemon samples
        # twice, so fetch them concurrently instead of one after another
        max_workers = 32
        client = docker.DockerClient(
            base_url=engine.url, timeout=DOCKER_TIMEOUT, max_pool_size=max_workers
        )
        containers = client.containers.list()
        if not containers:
            return []

        with ThreadPoolExecutor(max_workers=min(max_workers, len(containers))) as pool:
            return list(pool.map(self.get_single_container_stats, containers))

    def get_single_container_stats(self, container):
        try:
            container_stats = container.stats(stream=False)

            # Docker samples twice for stream=False and fills precpu_stats; Podman
            # returns a single sample with it empty, so take the second sample ourselves
            if container_stats["precpu_stats"].get("system_cpu_usage"):
                # Calculate CPU percentage
                cpu_total = float(
                    container_stats["cpu_stats"]["cpu_usage"]["total_usage"]
                )
                cpu_delta = cpu_total - float(
                    container_stats["precpu_stats"]["cpu_usage"]["total_usage"]
                )
                system_delta = float(
                    container_stats["cpu_stats"]["system_cpu_usage"]
                ) - float(container_stats["precpu_stats"]["system_cpu_usage"])
                online_cpus = container_stats["cpu_stats"].get(
                    "online_cpus",
                    len(
                        container_stats["cpu_stats"]["cpu_usage"].get(
                            "percpu_usage", [1]
                        )
                    ),
                )

                cpu_percent = 0.0
                if system_delta > 0.0:
                    cpu_percent = (cpu_delta / system_delta) * 100.0 * online_cpus
            else:
                # Podman's system_cpu_usage isn't comparable to Docker's, so measure CPU
                # time against wall-clock time between two samples, like `podman stats`
                first_total = container_stats["cpu_stats"]["cpu_usage"]["total_usage"]
                started = time.monotonic()
                time.sleep(PODMAN_SAMPLE_INTERVAL)
                container_stats = container.stats(stream=False)
                elapsed_ns = (time.monotonic() - started) * 1e9
                cpu_delta = (
                    container_stats["cpu_stats"]["cpu_usage"]["total_usage"]
                    - first_total
                )
                cpu_percent = cpu_delta / elapsed_ns * 100.0

            # Memory usage
            mem_usage = container_stats["memory_stats"].get("usage", 0)
            mem_limit = container_stats["memory_stats"].get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100.0
            mem_mb = mem_usage / (1024 * 1024)

            # Network usage
            net_usage = container_stats.get("networks", {})
            network_in = sum([net.get("rx_bytes", 0) for net in net_usage.values()])
            network_out = sum([net.get("tx_bytes", 0) for net in net_usage.values()])

            return {
                "name": container.name,
                "cpu_percent": f"{cpu_percent:.2f}%",
                "memory_usage": f"{mem_mb:.2f} MB ({mem_percent:.2f}%)",
                "network_io": f"IN: {network_in/1024:.2f} KB / OUT: {network_out/1024:.2f} KB",
            }

        except Exception:
            return {
                "name": container.name,
                "cpu_percent": "N/A",
                "memory_usage": "N/A",
                "network_io": "N/A",
            }

    def check_auth(self, request):
        """Check if user is authenticated (only if auth is enabled)"""
        if not is_auth_enabled():
            return True
        return request.user.is_authenticated

    def post(self, request, *args, **kwargs):
        """Handle login via AJAX"""
        if not is_auth_enabled():
            return JsonResponse(
                {"success": False, "error": "Authentication is disabled"}
            )

        # Slow down password guessing: lock out an address after repeated failures
        failures_key = f"login-failures:{request.META.get('REMOTE_ADDR')}"
        if cache.get(failures_key, 0) >= LOGIN_MAX_FAILURES:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Too many failed attempts. Try again in a few minutes.",
                },
                status=429,
            )

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            cache.delete(failures_key)
            login(request, user)
            return JsonResponse({"success": True})
        else:
            cache.add(failures_key, 0, LOGIN_LOCKOUT_SECONDS)
            cache.incr(failures_key)
            return JsonResponse({"success": False, "error": "Invalid credentials"})

    def get(self, request, *args, **kwargs):
        # Handle AJAX requests for stats and graph
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            # Check authentication only if enabled
            if not self.check_auth(request):
                return JsonResponse({"error": "Not authenticated"}, status=401)

            # All enabled engines combined, each stats row tagged with its engine
            if request.GET.get("type") == "stats":
                return JsonResponse(
                    {"stats": STATS_RESULT.get(self.get_container_stats)}
                )
            elif request.GET.get("type") == "graph":
                try:
                    return JsonResponse(
                        {"graph": GRAPH_RESULT.get(self.generate_network_graph)}
                    )
                except ExecutableNotFound:
                    # Graphviz is optional (the container image leaves it out); the
                    # dashboard draws its graph in the browser and doesn't need it
                    return JsonResponse(
                        {
                            "error": "The PNG graph needs Graphviz (the dot command), "
                            "which isn't installed on this server."
                        },
                        status=501,
                    )

        # For normal page loads, render the template
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)


def sse_event(data, event=None):
    lines = [f"event: {event}"] if event else []
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"


_view = DockerStatsView()
COLLECTORS = {
    "stats": lambda engine: {"stats": _view.get_container_stats(engine)},
    "graph": lambda engine: {"graph": _view.get_graph_data(engine)},
}

# One broadcaster per (type, engine), created when first watched: an engine
# nobody is looking at is never queried
BROADCASTERS = {}


def get_broadcaster(data_type, engine):
    key = (data_type, engine)
    if key not in BROADCASTERS:
        collect = COLLECTORS[data_type]
        BROADCASTERS[key] = Broadcaster(lambda: collect(engine))
    return BROADCASTERS[key]


async def stats_stream(request):
    """Server-Sent Events stream of one engine's container stats or network graph,
    pushed every second."""
    data_type = request.GET.get("type")
    if data_type not in COLLECTORS:
        return JsonResponse({"error": "type must be 'stats' or 'graph'"}, status=400)
    enabled = engine_names()
    engine = request.GET.get("engine") or enabled[0]
    if engine not in enabled:
        return JsonResponse(
            {"error": f"engine must be one of: {', '.join(enabled)}"}, status=400
        )
    broadcaster = get_broadcaster(data_type, engine)

    if is_auth_enabled() and not (await request.auser()).is_authenticated:
        # EventSource can't read status codes, so say why in the stream itself;
        # the page then closes it and shows the login form
        async def unauthorized():
            yield sse_event({"error": "Not authenticated"}, event="unauthorized")

        events = unauthorized()
    else:

        async def updates():
            # Reconnect after 3s if the connection drops
            yield "retry: 3000\n\n"
            async for data in broadcaster.listen():
                yield sse_event(data)

        events = updates()

    response = StreamingHttpResponse(events, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    # Stop nginx and similar reverse proxies from buffering the stream
    response["X-Accel-Buffering"] = "no"
    return response
