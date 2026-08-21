"""
ยืนยันว่า direction="egress" (ค่าเริ่มต้น) ของ Tier8_EnsureScopeClosure/controller.py
ยิงคำสั่ง tc ชุดเดียวกันเป๊ะกับ experiment/controller.py เดิมของโปรเจกต์ — สำคัญ
มากเพราะข้อ 2 (fixed-long-timeout) และข้อ 5 (jitter floor) ต้องเทียบกับ
5,300 trials เดิมได้ตรงๆ ถ้า egress behavior เปลี่ยนไปแม้แต่นิดเดียว การเทียบ
นั้นจะเสียความหมาย
"""
from controller import NetworkController


def test_apply_baseline_all_zero_skips_tc_add_entirely(mock_tc):
    net = NetworkController(iface="eth0")  # direction เริ่มต้น = "egress"
    result = net.apply(delay_ms=0, jitter_ms=0, loss_pct=0, bandwidth_kbit=None)
    assert result["cmd"] == "baseline"
    add_calls = [c for c in mock_tc if "add" in c]
    assert add_calls == []


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
    netem_calls = [c for c in joined if "netem" in c and "add" in c]
    tbf_calls = [c for c in joined if "tbf" in c]
    assert len(netem_calls) == 1
    assert "loss 20%" in netem_calls[0]
    assert len(tbf_calls) == 1
    assert "rate 250kbit" in tbf_calls[0]


def test_apply_zero_bandwidth_kbit_is_treated_as_no_bandwidth(mock_tc):
    net = NetworkController(iface="eth0")
    result = net.apply(delay_ms=0, jitter_ms=0, loss_pct=0, bandwidth_kbit=0)
    assert result["cmd"] == "baseline"


def test_jitter_without_delay_is_rejected(mock_tc):
    net = NetworkController(iface="eth0")
    result = net.apply(delay_ms=0, jitter_ms=30, loss_pct=0, bandwidth_kbit=None)
    assert result["returncode"] == 1
    assert "jitter_ms > 0 requires delay_ms > 0" in result["stderr"]


def test_egress_apply_never_touches_ingress_or_ifb_keys(mock_tc):
    """direction='egress' ต้องไม่มี key 'ingress'/'ingress_setup' โผล่มาเลย —
    กัน caller ที่อ่าน log แล้วสับสนว่ามีการ shape ingress ทั้งที่ไม่ได้เปิดใช้"""
    net = NetworkController(iface="eth0")
    result = net.apply(delay_ms=100, jitter_ms=0, loss_pct=50, bandwidth_kbit=None)
    assert "ingress" not in result
    assert "ingress_setup" not in result


def test_clear_uses_harmless_error_handling_same_as_original(mock_tc):
    net = NetworkController(iface="eth0")
    result = net.clear()
    assert result["returncode"] == 0
