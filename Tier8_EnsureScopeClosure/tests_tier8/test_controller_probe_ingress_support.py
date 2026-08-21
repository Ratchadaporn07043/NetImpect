"""
ยืนยัน probe_ingress_support() (ข้อ 4 — preflight check ก่อนรัน ingress shaping
จริง) ทั้งเส้นทาง "ผ่าน" และ "ไม่ผ่าน" แต่ละจุดที่อาจล้มเหลว — สำคัญเพราะ
run_tier8_ingress.py พึ่งฟังก์ชันนี้เป็นประตูด่านแรกก่อนรันอะไรทั้งคืน ถ้าฟังก์ชัน
นี้รายงานผิดพลาด (บอกว่า supported=True ทั้งที่จริงไม่รองรับ) จะเจอปัญหาแบบ
เดียวกับความพยายามก่อนหน้าที่ falsification check ไม่ผ่าน
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
    """rules: list ของ (substring, returncode, stderr) ตามลำดับที่ควรถูกเช็ค
    คำสั่งไหนไม่ match rule ไหนเลย -> returncode=0 ว่าง (ผ่านเป็นค่าเริ่มต้น)"""
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
    _patch_subprocess(monkeypatch, [])  # ทุกคำสั่งสำเร็จ (returncode=0)
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
    """ifb0 มีอยู่แล้วจากการรันครั้งก่อน (RTNETLINK answers: File exists) ต้องไม่
    ถือเป็นความล้มเหลว (idempotent)"""
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
    """probe ต้องไม่ยิง netem/tbf จริง (ไม่ใช่การ apply impairment) — แค่ตรวจว่า
    โครงสร้างพื้นฐานพร้อมไหม"""
    calls = _patch_subprocess(monkeypatch, [])
    net = NetworkController(iface="eth0", direction="both")
    net.probe_ingress_support()
    joined = [" ".join(c) for c in calls]
    assert not any("netem" in c for c in joined)
    assert not any("tbf" in c for c in joined)
