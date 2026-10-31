#!/usr/bin/env bash
# Start 5 tiny demo containers on Docker and 5 on Podman, each with a published port,
# to try dStats with both engines.
#
# Usage:
#   scripts/demo-containers.sh up     [docker|podman|all]   # default: all
#   scripts/demo-containers.sh down   [docker|podman|all]
#   scripts/demo-containers.sh status [docker|podman|all]
#
# Ports (localhost only): Docker 18081-18085, Podman 18091-18095.
# Change the bases with DOCKER_BASE_PORT / PODMAN_BASE_PORT.

set -euo pipefail

IMAGE="docker.io/library/busybox:1.37"
PREFIX="dstats-demo"
NETWORK="${PREFIX}-net"
LABEL="dstats-demo=1"
DOCKER_BASE_PORT="${DOCKER_BASE_PORT:-18080}"
PODMAN_BASE_PORT="${PODMAN_BASE_PORT:-18090}"

# Serve a one-line page on port 80; $1 is extra shell run alongside the web server
web_server() {
    # ";" (not "&&") before the workload, so its "&" backgrounds only the workload
    printf '%s' "mkdir -p /www && echo \"dStats demo: \$(hostname)\" > /www/index.html; $1 httpd -f -p 80 -h /www"
}

# name | extra docker/podman run flags | background workload
DEMOS=(
    "web||"
    "api||"
    "busy|--cpus 0.25|(while :; do :; done) &"
    "client||(while :; do wget -q -O /dev/null http://${PREFIX}-web; sleep 2; done) &"
    "isolated|--no-demo-network|"
)

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

    "$engine" network inspect "$NETWORK" >/dev/null 2>&1 \
        || "$engine" network create --label "$LABEL" "$NETWORK" >/dev/null

    for demo in "${DEMOS[@]}"; do
        IFS='|' read -r name flags workload <<<"$demo"
        local container="${PREFIX}-${name}" network_args=(--network "$NETWORK")
        if [[ $flags == --no-demo-network ]]; then
            network_args=()
            flags=""
        fi

        if "$engine" container inspect "$container" >/dev/null 2>&1; then
            echo "[$engine] $container already exists"
        else
            # shellcheck disable=SC2086  # $flags is deliberately split into arguments
            "$engine" run -d --name "$container" --label "$LABEL" \
                "${network_args[@]}" --memory 32m $flags \
                -p "127.0.0.1:$((port + i)):80" \
                "$IMAGE" sh -c "$(web_server "$workload")" >/dev/null
            echo "[$engine] $container -> http://127.0.0.1:$((port + i))"
        fi
        i=$((i + 1))
    done
}

down() {
    local engine=$1 ids
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
    if "$engine" network inspect "$NETWORK" >/dev/null 2>&1; then
        "$engine" network rm "$NETWORK" >/dev/null
        echo "[$engine] removed network $NETWORK"
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
        *) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
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
