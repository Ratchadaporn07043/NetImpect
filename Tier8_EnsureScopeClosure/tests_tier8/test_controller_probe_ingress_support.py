"""
Verify probe_ingress_support() for Tier8 item 4, including every supported and
unsupported preflight path. This is important because run_tier8_ingress.py relies
on it before an overnight run; a false supported=True result would repeat the
earlier failed falsification check.
"""
import subprocess

import pytest

from controller import NetworkController


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_subprocess(monkeypatch, rules):
    """Rules are (substring, returncode, stderr) tuples checked in order.
    Unmatched commands return an empty successful result by default."""
    calls = []

    def _fake_run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(list(cmd))
        joined = " ".join(cmd)
        for substr, rc, stderr in rules:
            if substr in joined:
                return _FakeResult(returncode=rc, stdout="", stderr=stderr)
        return _FakeResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return calls


def test_probe_supported_when_every_step_succeeds(monkeypatch):
    _patch_subprocess(monkeypatch, [])  # Every command succeeds (returncode=0).
    net = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    probe = net.probe_ingress_support()
    assert probe["supported"] is True
    assert len(probe["checks"]) == 5  # ip -V, ifb add, ifb up, ingress qdisc, mirred filter


def test_probe_fails_when_ip_command_missing(monkeypatch):
    _patch_subprocess(monkeypatch, [("ip -V", 127, "ip: command not found")])
    net = NetworkController(iface="eth0", direction="both")
    probe = net.probe_ingress_support()
    assert probe["supported"] is False
    assert "ip" in probe["reason"]


def test_probe_fails_when_ifb_module_not_loaded(monkeypatch):
    _patch_subprocess(monkeypatch, [
        ("ip link add ifb0 type ifb", 2, "RTNETLINK answers: Operation not supported"),
    ])
    net = NetworkController(iface="eth0", direction="both")
    probe = net.probe_ingress_support()
    assert probe["supported"] is False
    assert "modprobe ifb" in probe["reason"]


def test_probe_treats_existing_ifb_device_as_success_not_failure(monkeypatch):
    """An existing ifb0 from an earlier run must not be treated as failure (idempotent)."""
    _patch_subprocess(monkeypatch, [
        ("ip link add ifb0 type ifb", 2, "RTNETLINK answers: File exists"),
    ])
    net = NetworkController(iface="eth0", direction="both")
    probe = net.probe_ingress_support()
    assert probe["supported"] is True


def test_probe_fails_when_ingress_qdisc_rejected(monkeypatch):
    _patch_subprocess(monkeypatch, [
        ("tc qdisc add dev eth0 ingress", 2, "RTNETLINK answers: Operation not permitted"),
    ])
    net = NetworkController(iface="eth0", direction="both")
    probe = net.probe_ingress_support()
    assert probe["supported"] is False
    assert "NET_ADMIN" in probe["reason"]


def test_probe_fails_when_mirred_filter_rejected(monkeypatch):
    _patch_subprocess(monkeypatch, [
        ("action mirred egress redirect", 2, "Error: Specified qdisc kind is unknown."),
    ])
    net = NetworkController(iface="eth0", direction="both")
    probe = net.probe_ingress_support()
    assert probe["supported"] is False
    assert "act_mirred" in probe["reason"]


def test_probe_only_runs_read_or_idempotent_commands(monkeypatch):
    """The probe must not apply real netem/tbf impairment; it only checks readiness."""
    calls = _patch_subprocess(monkeypatch, [])
    net = NetworkController(iface="eth0", direction="both")
    net.probe_ingress_support()
    joined = [" ".join(c) for c in calls]
    assert not any("netem" in c for c in joined)
    assert not any("tbf" in c for c in joined)
