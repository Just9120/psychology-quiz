"""CD must reject public bindings and unrelated network/container targets."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from scripts import runtime_exposure as check

SHA = "a" * 40
CONTAINER = "b" * 64


def owned(service):
    port = check.PORTS[service]
    binding = {port + '/tcp': [{'HostIp': '127.0.0.1', 'HostPort': port}]}
    container = {'State': {'Running': True}, 'Config': {'Labels': {
        'com.docker.compose.project': 'psychology-quiz', 'com.docker.compose.service': service,
        'org.opencontainers.image.revision': SHA}, 'Env': ['TOKEN=private-secret']},
        'HostConfig': {'NetworkMode': 'psychology-quiz_default', 'PortBindings': binding},
        'NetworkSettings': {'Networks': {'psychology-quiz_default': {'NetworkID': 'owned-network'}},
                            'Ports': {**deepcopy(binding), '443/tcp': None}}}
    network = {'Name': 'psychology-quiz_default', 'Id': 'owned-network', 'Driver': 'bridge',
               'Labels': {'com.docker.compose.project': 'psychology-quiz', 'com.docker.compose.network': 'default'}}
    return container, network


@pytest.mark.parametrize('service', list(check.PORTS))
def test_owned_loopback_bindings_pass_without_treating_unpublished_expose_as_public(service):
    container, network = owned(service)
    before = deepcopy((container, network))
    check.verify_exposure(container, network, service, SHA)
    assert (container, network) == before


@pytest.mark.parametrize('host_ip', ['0.0.0.0', '', '::'])
def test_wildcard_bindings_are_rejected_in_requested_and_effective_ports(host_ip):
    for field in ('HostConfig', 'NetworkSettings'):
        container, network = owned('psych_quiz_miniapp_api')
        key = 'PortBindings' if field == 'HostConfig' else 'Ports'
        container[field][key]['8081/tcp'][0]['HostIp'] = host_ip
        with pytest.raises(check.ExposureError):
            check.verify_exposure(container, network, 'psych_quiz_miniapp_api', SHA)


@pytest.mark.parametrize('attack', ['host_network', 'unrelated_network', 'unidentified_network', 'macvlan', 'other_project', 'old_revision', 'extra_port'])
def test_same_service_name_cannot_hide_an_unrelated_or_exposed_runtime(attack):
    container, network = owned('psych_quiz_miniapp_api')
    if attack == 'host_network':
        container['HostConfig']['NetworkMode'] = 'host'
    elif attack == 'unrelated_network':
        container['NetworkSettings']['Networks']['other-network'] = {'NetworkID': 'other'}
    elif attack == 'unidentified_network':
        network.pop('Id')
        container['NetworkSettings']['Networks']['psychology-quiz_default']['NetworkID'] = None
    elif attack == 'macvlan':
        network['Driver'] = 'macvlan'
    elif attack == 'other_project':
        container['Config']['Labels']['com.docker.compose.project'] = 'another-project'
    elif attack == 'old_revision':
        container['Config']['Labels']['org.opencontainers.image.revision'] = 'c' * 40
    else:
        container['NetworkSettings']['Ports']['5432/tcp'] = [{'HostIp': '0.0.0.0', 'HostPort': '5432'}]
    with pytest.raises(check.ExposureError):
        check.verify_exposure(container, network, 'psych_quiz_miniapp_api', SHA)


def test_cli_is_read_only_and_does_not_print_inspected_environment(monkeypatch, capsys):
    container, network = owned('psych_quiz_miniapp_api')
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        value = network if argv[1] == 'network' else container
        return SimpleNamespace(stdout=json.dumps([value]).encode())

    monkeypatch.setattr(check.subprocess, 'run', run)
    args = ['--service', 'psych_quiz_miniapp_api', '--container-id', CONTAINER, '--expected-sha', SHA]
    assert check.main(args) == 0
    assert calls == [['docker', 'inspect', CONTAINER], ['docker', 'network', 'inspect', 'psychology-quiz_default']]
    assert 'private-secret' not in capsys.readouterr().out
    container['NetworkSettings']['Ports']['8081/tcp'][0]['HostIp'] = '0.0.0.0'
    assert check.main(args) == 1
    captured = capsys.readouterr()
    assert 'RUNTIME_EXPOSURE_STOP' in captured.err and 'private-secret' not in captured.err
