"""ยืนยันว่า NetworkController.apply() ต้นฉบับรองรับ bandwidth_kbit จริง
(เป็น precondition สำคัญของ Tier2 bandwidth axis — ถ้าอันนี้พังคือ Tier2 ทั้ง
ส่วน bandwidth ใช้งานไม่ได้เลย) ใช้ mock_tc กัน subprocess จริงถูกเรียก"""
from experiment.controller import NetworkController


def test_apply_without_bandwidth_does_not_call_tbf(mock_tc):
    net = NetworkController(iface="eth0")
    net.apply(delay_ms=100, jitter_ms=0, loss_pct=0, bandwidth_kbit=None)
    joined = [" ".join(c) for c in mock_tc]
    assert not any("tbf" in c for c in joined)


def test_apply_with_bandwidth_issues_tbf_command(mock_tc):
    net = NetworkController(iface="eth0")
    net.apply(delay_ms=0, jitter_ms=0, loss_pct=0, bandwidth_kbit=500)
    joined = [" ".join(c) for c in mock_tc]
    tbf_calls = [c for c in joined if "tbf" in c]
    assert len(tbf_calls) == 1
    assert "rate 500kbit" in tbf_calls[0]
    assert "eth0" in tbf_calls[0]


def test_apply_with_bandwidth_and_loss_combines_netem_and_tbf(mock_tc):
    net = NetworkController(iface="eth0")
    net.apply(delay_ms=0, jitter_ms=0, loss_pct=20, bandwidth_kbit=250)
    joined = [" ".join(c) for c in mock_tc]
    netem_calls = [c for c in joined if "netem" in c]
    tbf_calls = [c for c in joined if "tbf" in c]
    assert len(netem_calls) == 1
    assert "loss 20%" in netem_calls[0]
    assert len(tbf_calls) == 1
    assert "rate 250kbit" in tbf_calls[0]


def test_apply_baseline_all_zero_and_no_bandwidth_skips_tc_add_entirely(mock_tc):
    net = NetworkController(iface="eth0")
    result = net.apply(delay_ms=0, jitter_ms=0, loss_pct=0, bandwidth_kbit=None)
    assert result["cmd"] == "baseline"
    add_calls = [c for c in mock_tc if "add" in c]
    assert add_calls == []  # ไม่มี tc qdisc add เลยตอน baseline จริงๆ (มีแค่ clear ตอนต้น)


def test_apply_zero_bandwidth_kbit_is_treated_as_no_bandwidth(mock_tc):
    """bandwidth_kbit=0 ต้องไม่ถูกตีความว่าเป็นการจำกัด bandwidth (has_bandwidth
    เช็คว่า > 0) กันไม่ให้ Tier2 scenario ที่พลาดใส่ 0 ทำให้ apply() ล้มเหลว"""
    net = NetworkController(iface="eth0")
    result = net.apply(delay_ms=0, jitter_ms=0, loss_pct=0, bandwidth_kbit=0)
    assert result["cmd"] == "baseline"
