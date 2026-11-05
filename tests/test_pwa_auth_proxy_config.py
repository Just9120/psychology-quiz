import hashlib
from pathlib import Path
import subprocess

import pytest

from scripts.pwa_auth_proxy_config import apply, transform


TEMPLATE = (Path(__file__).resolve().parents[1] / "deployment/pwa/nginx.conf.template").read_text(encoding="utf-8")
CONFIG = b'''server {
    server_name unrelated.example;
    location / { return 200; }
}
server {
    server_name psy.example;
    location ^~ /web/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
    }
    location / { try_files $uri /index.html; }
}
'''
ENV = b"BOT_TOKEN=synthetic-secret\nPWA_ENABLED=true\n"


def test_only_pwa_web_location_and_single_peer_setting_change():
    config, env = transform(CONFIG, ENV, TEMPLATE, "::ffff:172.20.0.1")
    assert config.startswith(CONFIG[:CONFIG.index(b"    location ^~ /web/")])
    assert config.endswith(CONFIG[CONFIG.index(b"    location / { try_files"):])
    assert b"X-Psychology-Client-Address $remote_addr;" in config
    assert b"set_real_ip_from 127.0.0.1" not in config
    assert env == ENV + b"PWA_AUTH_PROXY_PEERS=172.20.0.1\n"
    assert transform(config, env, TEMPLATE, "172.20.0.1") == (config, env)


@pytest.mark.parametrize("config,env,peer", [
    (CONFIG.replace(b":8081;", b":9999;"), ENV, "172.20.0.1"),
    (CONFIG + CONFIG, ENV, "172.20.0.1"),
    (CONFIG, ENV + b"PWA_AUTH_PROXY_PEERS=a\nPWA_AUTH_PROXY_PEERS=b\n", "172.20.0.1"),
    (CONFIG, ENV, "172.20.0.0/16"), (CONFIG, ENV, "*")])
def test_unknown_config_is_not_silently_reinterpreted(config, env, peer):
    with pytest.raises(ValueError):
        transform(config, env, TEMPLATE, peer)


@pytest.mark.parametrize("failure", [None, "candidate-test", "reload", "digest"])
def test_cutover_backup_readback_and_failure_restore(tmp_path, failure):
    config, env, backup = [tmp_path / name for name in ("site.conf", "runtime.env", "backup")]
    config.write_bytes(CONFIG)
    env.write_bytes(ENV)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if ((failure == "candidate-test" and len(calls) == 2)
                or (failure == "reload" and len(calls) == 3)):
            raise subprocess.CalledProcessError(1, command)

    config_digest = hashlib.sha256(CONFIG).hexdigest()
    args = (config, env, backup, TEMPLATE, "172.20.0.1",
            "0" * 64 if failure == "digest" else config_digest, hashlib.sha256(ENV).hexdigest())
    if failure:
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            apply(*args, run=run)
        assert (config.read_bytes(), env.read_bytes()) == (CONFIG, ENV)
        assert backup.exists() is (failure != "digest")
    else:
        apply(*args, run=run)
        assert (config.read_bytes(), env.read_bytes()) == transform(CONFIG, ENV, TEMPLATE, "172.20.0.1")
    if backup.exists():
        assert (backup / "nginx.conf").read_bytes() == CONFIG
        assert (backup / "runtime.env").read_bytes() == ENV
        with pytest.raises(FileExistsError):
            # Reuse is rejected even when both expected digests are current.
            apply(config, env, backup, TEMPLATE, "172.20.0.1", hashlib.sha256(config.read_bytes()).hexdigest(),
                  hashlib.sha256(env.read_bytes()).hexdigest(), run=run)
