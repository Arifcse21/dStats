#!/usr/bin/env bash
# Start 10 tiny demo containers on Docker and 10 on Podman, each with a published port,
# to try the dStats UI with both engines. They are deliberately lightweight: each one
# is a busybox web server capped at 16 MB of memory and 10% of a CPU. Most sit on
# several of 5 networks, so the network graph is busy enough to test with.
#
# Usage:
#   scripts/demo-containers.sh up     [docker|podman|all]   # default: all
#   scripts/demo-containers.sh down   [docker|podman|all]
#   scripts/demo-containers.sh status [docker|podman|all]
#
# Ports (localhost only): Docker 18081-18090, Podman 18101-18110.
# Change the bases with DOCKER_BASE_PORT / PODMAN_BASE_PORT.

set -euo pipefail

IMAGE="docker.io/library/busybox:1.37"
PREFIX="dstats-demo"
LABEL="dstats-demo=1"
DOCKER_BASE_PORT="${DOCKER_BASE_PORT:-18080}"
PODMAN_BASE_PORT="${PODMAN_BASE_PORT:-18100}"

# Overlapping networks make a deliberately messy graph
NETWORKS=(edge frontend backend data monitoring)

# Light, occasional activity so the CPU and network columns aren't all zeros
TINY_CPU_BURST='(while :; do i=0; while [ $i -lt 3000 ]; do i=$((i+1)); done; sleep 5; done) &'
CALL_WEB_EVERY_5S="(while :; do wget -q -O /dev/null http://${PREFIX}-web; sleep 5; done) &"

# name | networks (comma-separated; empty = engine's default network) | background workload
DEMOS=(
    "web|edge,frontend|"
    "api|frontend,backend,monitoring|"
    "auth|backend,data|"
    "cache|backend,data|"
    "db|data|"
    "queue|backend,data,monitoring|"
    "worker|backend,data|$TINY_CPU_BURST"
    "client|edge,frontend|$CALL_WEB_EVERY_5S"
    "metrics|monitoring,frontend,backend,data|"
    "isolated||"
)

# Serve a one-line page on port 80; $1 is extra shell run alongside the web server.
# ";" (not "&&") before it, so the workload's "&" backgrounds only the workload.
web_server() {
    printf '%s' "mkdir -p /www && echo \"dStats demo: \$(hostname)\" > /www/index.html; $1 httpd -f -p 80 -h /www"
}

engine_ready() {
    local engine=$1
    if ! command -v "$engine" >/dev/null 2>&1; then
        echo "[$engine] not installed, skipping"
        return 1
    fi
    if ! "$engine" info >/dev/null 2>&1; then
        if [[ $engine == docker ]]; then
            echo "[docker] can't talk to the daemon: is it running, and is \`id -nG\` showing 'docker'? (try: newgrp docker)"
        else
            echo "[podman] \`podman info\` failed"
        fi
        return 1
    fi
}

base_port() {
    [[ $1 == docker ]] && echo "$DOCKER_BASE_PORT" || echo "$PODMAN_BASE_PORT"
}

up() {
    local engine=$1 port i=1
    engine_ready "$engine" || return 0
    port=$(base_port "$engine")

    echo "[$engine] pulling $IMAGE"
    "$engine" pull -q "$IMAGE" >/dev/null

    for net in "${NETWORKS[@]}"; do
        "$engine" network inspect "${PREFIX}-${net}" >/dev/null 2>&1 \
            || "$engine" network create --label "$LABEL" "${PREFIX}-${net}" >/dev/null
    done

    for demo in "${DEMOS[@]}"; do
        IFS='|' read -r name networks workload <<<"$demo"
        local container="${PREFIX}-${name}" nets=() network_args=()
        [[ -n $networks ]] && IFS=',' read -r -a nets <<<"$networks"
        [[ ${#nets[@]} -gt 0 ]] && network_args=(--network "${PREFIX}-${nets[0]}")

        if "$engine" container inspect "$container" >/dev/null 2>&1; then
            echo "[$engine] $container already exists"
        else
            "$engine" run -d --name "$container" --label "$LABEL" \
                "${network_args[@]}" --memory 16m --cpus 0.1 \
                -p "127.0.0.1:$((port + i)):80" \
                "$IMAGE" sh -c "$(web_server "$workload")" >/dev/null
            # A container can only be created on one network; attach the rest afterwards
            for net in "${nets[@]:1}"; do
                "$engine" network connect "${PREFIX}-${net}" "$container"
            done
            echo "[$engine] $container -> http://127.0.0.1:$((port + i))  [${networks:-default network}]"
        fi
        i=$((i + 1))
    done
}

down() {
    local engine=$1 ids nets
    engine_ready "$engine" || return 0
    ids=$("$engine" ps -aq --filter "label=$LABEL")
    if [[ -n $ids ]]; then
        # Throwaway containers: kill at once (Podman otherwise waits 10s per container)
        local stop_now=()
        [[ $engine == podman ]] && stop_now=(-t 0)
        # shellcheck disable=SC2086  # one ID per word
        "$engine" rm -f "${stop_now[@]}" $ids >/dev/null
        echo "[$engine] removed $(wc -w <<<"$ids") demo container(s)"
    else
        echo "[$engine] no demo containers"
    fi
    nets=$("$engine" network ls -q --filter "label=$LABEL")
    if [[ -n $nets ]]; then
        # shellcheck disable=SC2086  # one ID per word
        "$engine" network rm $nets >/dev/null
        echo "[$engine] removed $(wc -w <<<"$nets") demo network(s)"
    fi
    echo "[$engine] the $IMAGE image is kept; remove it with: $engine rmi $IMAGE"
}

status() {
    local engine=$1
    engine_ready "$engine" || return 0
    echo "[$engine]"
    "$engine" ps --filter "label=$LABEL" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
}

main() {
    local action=${1:-} target=${2:-all} engines
    case $target in
        docker | podman) engines=("$target") ;;
        all) engines=(docker podman) ;;
        *) echo "Unknown engine '$target' (use docker, podman or all)" >&2; exit 2 ;;
    esac
    case $action in
        up | down | status) ;;
        *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
    esac

    for engine in "${engines[@]}"; do
        "$action" "$engine"
    done

    if [[ $action == up ]]; then
        echo
        echo "Now run: dStats.server --engine docker,podman"
        echo "Clean up: $0 down"
    fi
}

main "$@"
