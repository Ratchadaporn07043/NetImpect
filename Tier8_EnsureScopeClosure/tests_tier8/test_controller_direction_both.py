"""
ยืนยันพฤติกรรมของ direction="both" (ข้อ 4 — bidirectional/ingress shaping):
  - ต้องเรียก ip link add ifb0 / tc qdisc add ... ingress / tc filter ... mirred
    redirect ทุกครั้งที่ apply() (idempotent setup)
  - ต้อง mirror netem/tbf เดียวกับ egress ไปที่ ifb device
  - direction="egress" (ค่าเริ่มต้น) ต้องไม่ยิงคำสั่งพวกนี้เลยแม้แต่คำสั่งเดียว
    (กันไม่ให้ default behavior ของ 5,300 trials เดิมเปลี่ยนไปโดยไม่ตั้งใจ)
"""
from controller import NetworkController


def test_default_direction_is_egress():
    net = NetworkController(iface="eth0")
    assert net.direction == "egress"


def test_invalid_direction_raises():
    import pytest
    with pytest.raises(ValueError):
        NetworkController(iface="eth0", direction="not_a_real_direction")


def test_both_direction_sets_up_ifb_and_mirred_redirect(mock_tc):
    net = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    net.apply(delay_ms=0, jitter_ms=0, loss_pct=75, bandwidth_kbit=None)
    joined = [" ".join(c) for c in mock_tc]

    assert any("ip link add ifb0 type ifb" in c for c in joined)
    assert any("ip link set dev ifb0 up" in c for c in joined)
    assert any("tc qdisc add dev eth0 ingress" in c for c in joined)
    assert any("mirred egress redirect dev ifb0" in c for c in joined)


def test_both_direction_mirrors_netem_to_ifb_device(mock_tc):
    net = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    net.apply(delay_ms=1000, jitter_ms=0, loss_pct=0, bandwidth_kbit=None)
    joined = [" ".join(c) for c in mock_tc]

    egress_netem = [c for c in joined if "netem" in c and "dev eth0" in c and "add" in c]
    ifb_netem = [c for c in joined if "netem" in c and "dev ifb0" in c and "add" in c]
    assert len(egress_netem) == 1 and "delay 1000ms" in egress_netem[0]
    assert len(ifb_netem) == 1 and "delay 1000ms" in ifb_netem[0]


def test_both_direction_mirrors_tbf_to_ifb_device(mock_tc):
    net = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    net.apply(delay_ms=0, jitter_ms=0, loss_pct=0, bandwidth_kbit=50)
    joined = [" ".join(c) for c in mock_tc]

    egress_tbf = [c for c in joined if "tbf" in c and "dev eth0" in c]
    ifb_tbf = [c for c in joined if "tbf" in c and "dev ifb0" in c]
    assert len(egress_tbf) == 1 and "rate 50kbit" in egress_tbf[0]
    assert len(ifb_tbf) == 1 and "rate 50kbit" in ifb_tbf[0]


def test_both_direction_baseline_still_sets_up_ifb_but_no_netem(mock_tc):
    """falsification-check scenario ของข้อ 4: baseline (ไม่มี impairment) ต้องยัง
    เซ็ต IFB redirect ไว้เหมือนกัน (เพื่อทดสอบว่า IFB path เองไม่ทำให้ completion
    ตก) แต่ต้องไม่มี netem/tbf ใดๆ ถูกใส่ที่ ifb0"""
    net = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    result = net.apply(delay_ms=0, jitter_ms=0, loss_pct=0, bandwidth_kbit=None)
    joined = [" ".join(c) for c in mock_tc]

    assert any("mirred egress redirect dev ifb0" in c for c in joined)
    assert not any("netem" in c and "add" in c for c in joined)
    assert result["ingress"] is None


def test_egress_direction_never_touches_ifb_or_ingress(mock_tc):
    net = NetworkController(iface="eth0", direction="egress")
    net.apply(delay_ms=100, jitter_ms=0, loss_pct=50, bandwidth_kbit=None)
    joined = [" ".join(c) for c in mock_tc]
    assert not any("ifb" in c for c in joined)
    assert not any("ingress" in c for c in joined)
    assert not any("mirred" in c for c in joined)


def test_clear_with_both_direction_clears_ingress_and_ifb_too(mock_tc):
    net = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    net.clear()
    joined = [" ".join(c) for c in mock_tc]
    assert any("qdisc del dev eth0 root" in c for c in joined)
    assert any("qdisc del dev eth0 ingress" in c for c in joined)
    assert any("qdisc del dev ifb0 root" in c for c in joined)


def test_current_status_reports_ifb_and_ingress_when_both(mock_tc):
    net = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    status = net.current_status()
    assert "egress" in status
    assert "ingress" in status
    assert "ifb" in status


def test_current_status_egress_only_returns_plain_string_like_original(mock_tc):
    """direction="egress" ต้องคืนค่าเป็น string เดียว (ไม่ใช่ dict) เหมือน
    experiment/controller.py เดิมทุกประการ — แก้จาก dict-wrapping เดิมที่เป็น
    behavior deviation แม้จะไม่มี run script ไหนเรียกใช้ current_status() จริง"""
    net = NetworkController(iface="eth0", direction="egress")
    status = net.current_status()
    assert isinstance(status, str)
    assert "ingress" not in status
