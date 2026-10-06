"""Read-only post-deploy check of owned runtime container/network exposure.

Inspection results contain environment values: never print raw Docker output.
This check makes no changes to containers, networks, ports or firewall rules.
"""
import argparse
import json
import re
import subprocess
import sys

PROJECT = "psychology-quiz"
NETWORK = PROJECT + "_default"
PORTS = {"psych_quiz_bot": "8090", "psych_quiz_miniapp_api": "8081"}


class ExposureError(ValueError):
    pass


def verify_exposure(container, network, service, revision):
    if service not in PORTS or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ExposureError("invalid_runtime_target")
    labels = container.get("Config", {}).get("Labels") or {}
    if (labels.get("com.docker.compose.project") != PROJECT
            or labels.get("com.docker.compose.service") != service
            or labels.get("org.opencontainers.image.revision") != revision
            or container.get("State", {}).get("Running") is not True):
        raise ExposureError("unexpected_runtime_identity")
    host = container.get("HostConfig") or {}
    networks = container.get("NetworkSettings", {}).get("Networks") or {}
    if host.get("NetworkMode") != NETWORK or set(networks) != {NETWORK}:
        raise ExposureError("unexpected_runtime_network")
    network_labels = network.get("Labels") or {}
    network_id = network.get("Id")
    if (network.get("Name") != NETWORK or network.get("Driver") != "bridge"
            or network_labels.get("com.docker.compose.project") != PROJECT
            or network_labels.get("com.docker.compose.network") != "default"
            or not isinstance(network_id, str) or not network_id
            or networks[NETWORK].get("NetworkID") != network_id):
        raise ExposureError("unexpected_runtime_network_identity")
    port = PORTS[service]
    expected = {port + "/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]}
    if host.get("PortBindings") != expected:
        raise ExposureError("runtime_port_must_be_loopback_only")
    # Confirm effective bindings, rather than only the requested HostConfig.
    effective = container.get("NetworkSettings", {}).get("Ports") or {}
    if not isinstance(effective, dict) or {port: bindings for port, bindings in effective.items()
                                         if bindings} != expected:
        raise ExposureError("unexpected_effective_runtime_ports")


def inspect(kind, target):
    result = subprocess.run(["docker", kind, "inspect", target] if kind == "network"
                            else ["docker", "inspect", target],
                            check=True, capture_output=True, timeout=15)
    values = json.loads(result.stdout)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise ExposureError("invalid_runtime_inspection")
    return values[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=PORTS, required=True)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9a-f]{12,64}", args.container_id):
            raise ExposureError("invalid_runtime_container_id")
        verify_exposure(inspect("container", args.container_id), inspect("network", NETWORK),
                        args.service, args.expected_sha)
    except Exception as error:
        print("RUNTIME_EXPOSURE_STOP: " + (str(error) if isinstance(error, ExposureError)
                                          else type(error).__name__), file=sys.stderr)
        return 1
    print("RUNTIME_EXPOSURE_OK service=" + args.service + " revision=" + args.expected_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
