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
from graphviz import Graph
import base64
from io import BytesIO
from django.views.generic import TemplateView
from asgiref.sync import sync_to_async
from django.http import JsonResponse, StreamingHttpResponse
from django.core.cache import cache
from django.contrib.auth import authenticate, login
from dStats.settings import is_auth_enabled
from django.contrib.auth.models import User

# Native accelerator, present in the platform wheels; pure-Python installs use the fallback below
try:
    from dStats import _rust
except ImportError:
    _rust = None

# Seconds before a Docker API call is abandoned, so a hung daemon can't hang requests forever
DOCKER_TIMEOUT = 10

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
            except Exception:
                logger.exception("Collecting dashboard data failed")
            else:
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
color_index = 0


def get_unique_color() -> str:
    global color_index
    if color_index < len(COLORS):
        c = COLORS[color_index]
        color_index += 1
    else:
        c = "#%06x" % random.randint(0, 0xFFFFFF)
    return c


class DockerStatsView(TemplateView):
    template_name = "dStats/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["auth_enabled"] = is_auth_enabled()
        return context

    def generate_network_graph(self):
        client = docker.from_env(timeout=DOCKER_TIMEOUT)
        networks = self.get_networks(client)
        containers, links = self.get_containers(client)

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

        # Draw networks and containers
        for network in networks.values():
            self.draw_network(g, network)

        for container in containers:
            self.draw_container(g, container)

        for link in links:
            if link.network_name != "none":
                self.draw_link(g, networks, link)

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

            color = get_unique_color()
            networks[net.name] = Network(net.name, gateway, internal, isolated, color)

        networks["host"] = Network("host", "0.0.0.0", False, False, "#808080")
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
                    Interface(endpoint_id, net_info["IPAddress"], aliases)
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

    def draw_network(self, g: Graph, net: Network):
        label = f"{{<gw_iface> {net.gateway} | {net.name}"
        if net.internal:
            label += " | Internal"
        if net.isolated:
            label += " | Containers isolated"
        label += "}"

        g.node(
            f"network_{net.name}",
            shape="record",
            label=label,
            fillcolor=net.color,
            style="filled",
        )

    def draw_container(self, g: Graph, c: Container):
        iface_labels = []
        for iface in c.interfaces:
            if iface.aliases:
                iface_labels.append(f"{iface.address} ({', '.join(iface.aliases)})")
            else:
                iface_labels.append(iface.address)

        port_labels = []
        for port in c.ports:
            port_labels.append(f"{port.internal}->{port.external}/{port.protocol}")

        label = f"{c.name}\\n"
        label += "Interfaces:\\n" + "\\n".join(iface_labels)
        if port_labels:
            label += "\\nPorts:\\n" + "\\n".join(port_labels)

        g.node(
            f"container_{c.container_id}",
            shape="box",
            label=label,
            fillcolor="#ff9999",
            style="filled",
        )

    def draw_link(self, g: Graph, networks: Dict[str, Network], link: Link):
        g.edge(
            f"container_{link.container_id}",
            f"network_{link.network_name}",
            color=networks[link.network_name].color,
        )

    def get_container_stats(self):
        if _rust is not None:
            try:
                return _rust.get_container_stats_parallel()
            except Exception as e:
                print(f"Rust stats failed: {e}, falling back to Python")

        # stats(stream=False) blocks ~1-2s per container while the daemon samples
        # twice, so fetch them concurrently instead of one after another
        max_workers = 32
        client = docker.from_env(timeout=DOCKER_TIMEOUT, max_pool_size=max_workers)
        containers = client.containers.list()
        if not containers:
            return []

        with ThreadPoolExecutor(max_workers=min(max_workers, len(containers))) as pool:
            return list(pool.map(self.get_single_container_stats, containers))

    def get_single_container_stats(self, container):
        try:
            container_stats = container.stats(stream=False)

            # Calculate CPU percentage
            cpu_total = float(container_stats["cpu_stats"]["cpu_usage"]["total_usage"])
            cpu_delta = cpu_total - float(
                container_stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = float(
                container_stats["cpu_stats"]["system_cpu_usage"]
            ) - float(container_stats["precpu_stats"]["system_cpu_usage"])
            online_cpus = container_stats["cpu_stats"].get(
                "online_cpus",
                len(container_stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])),
            )

            cpu_percent = 0.0
            if system_delta > 0.0:
                cpu_percent = (cpu_delta / system_delta) * 100.0 * online_cpus

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

            if request.GET.get("type") == "stats":
                return JsonResponse(
                    {"stats": STATS_RESULT.get(self.get_container_stats)}
                )
            elif request.GET.get("type") == "graph":
                return JsonResponse(
                    {"graph": GRAPH_RESULT.get(self.generate_network_graph)}
                )

        # For normal page loads, render the template
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)


def sse_event(data, event=None):
    lines = [f"event: {event}"] if event else []
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"


_view = DockerStatsView()
BROADCASTERS = {
    "stats": Broadcaster(lambda: {"stats": _view.get_container_stats()}),
    "graph": Broadcaster(lambda: {"graph": _view.generate_network_graph()}),
}


async def stats_stream(request):
    """Server-Sent Events stream of container stats or the network graph, pushed every second."""
    broadcaster = BROADCASTERS.get(request.GET.get("type"))
    if broadcaster is None:
        return JsonResponse({"error": "type must be 'stats' or 'graph'"}, status=400)

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
