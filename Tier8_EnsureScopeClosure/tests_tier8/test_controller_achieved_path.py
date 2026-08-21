"""
ยืนยันฟังก์ชันวัด achieved-path (ข้อ 1): parse ผลจริงของ `tc -s qdisc show`,
`ping`, `curl -w`, และ `/proc/net/snmp` ให้ถูกต้อง — ทั้งหมดนี้เป็นจุดที่ถ้า parse
ผิดจะทำให้ตัวเลข achieved ที่รายงานคลาดเคลื่อนโดยไม่มีใครรู้ (ต่างจาก tc return
code ที่ผิดแล้ว process จะ error ชัดเจน) จึงต้องเทสรูปแบบ output จริงของแต่ละ
คำสั่งอย่างละเอียด
"""
import subprocess

from controller import NetworkController

QDISC_SHOW_SAMPLE = """qdisc netem 1: root refcnt 2 limit 1000 delay 100ms loss 75%
 Sent 45231 bytes 312 pkt (dropped 187, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
"""

PING_SAMPLE_SUCCESS = """PING host.docker.internal (192.168.65.2) 56(84) bytes of data.

--- host.docker.internal ping statistics ---
5 packets transmitted, 5 received, 0% packet loss, time 4006ms
rtt min/avg/max/mdev = 20.123/25.456/30.789/3.210 ms
"""

PING_SAMPLE_TOTAL_LOSS = """PING host.docker.internal (192.168.65.2) 56(84) bytes of data.

--- host.docker.internal ping statistics ---
5 packets transmitted, 0 received, 100% packet loss, time 4090ms
"""

SNMP_SAMPLE = (
    "Ip: Forwarding DefaultTTL InReceives InHdrErrors\n"
    "Ip: 1 64 100 0\n"
    "Tcp: RtoAlgorithm RtoMin RtoMax MaxConn ActiveOpens PassiveOpens AttemptFails "
    "EstabResets CurrEstab InSegs OutSegs RetransSegs InErrs OutRsts InCsumErrors\n"
    "Tcp: 1 200 120000 -1 123 45 6 7 8 91011 121314 1516 0 17 0\n"
)


def test_read_qdisc_counters_parses_sent_and_dropped(mock_tc):
    mock_tc.stdout_map["-s qdisc show"] = QDISC_SHOW_SAMPLE
    net = NetworkController(iface="eth0")
    counters = net.read_qdisc_counters()
    assert counters["sent_bytes"] == 45231
    assert counters["sent_pkts"] == 312
    assert counters["dropped"] == 187
    assert counters["overlimits"] == 0
    assert counters["requeues"] == 0


def test_read_qdisc_counters_handles_unparseable_output_gracefully(mock_tc):
    mock_tc.stdout_map["-s qdisc show"] = "some unexpected output with no Sent line"
    net = NetworkController(iface="eth0")
    counters = net.read_qdisc_counters()
    assert "error" in counters


def test_measure_rtt_ms_parses_full_summary(mock_tc):
    mock_tc.stdout_map["ping"] = PING_SAMPLE_SUCCESS
    net = NetworkController(iface="eth0")
    rtt = net.measure_rtt_ms("host.docker.internal", count=5)
    assert rtt["packets_sent"] == 5
    assert rtt["packets_received"] == 5
    assert rtt["packet_loss_pct"] == 0.0
    assert rtt["avg_ms"] == 25.456
    assert rtt["min_ms"] == 20.123
    assert rtt["max_ms"] == 30.789
    assert rtt["mdev_ms"] == 3.210


def test_measure_rtt_ms_handles_total_packet_loss_with_no_rtt_line(mock_tc):
    mock_tc.stdout_map["ping"] = PING_SAMPLE_TOTAL_LOSS
    net = NetworkController(iface="eth0")
    rtt = net.measure_rtt_ms("host.docker.internal", count=5)
    assert rtt["packet_loss_pct"] == 100.0
    assert "avg_ms" not in rtt
    assert "note" in rtt


def test_background_transfer_probe_parses_curl_timing(mock_tc):
    mock_tc.stdout_map["curl"] = "2048 0.512"
    net = NetworkController(iface="eth0")
    probe = net.background_transfer_probe("http://host.docker.internal:11434/api/tags")
    assert probe["bytes"] == 2048
    assert probe["seconds"] == 0.512
    expected_kbit_s = round((2048 * 8 / 1000) / 0.512, 3)
    assert probe["achieved_kbit_s"] == expected_kbit_s


def test_background_transfer_probe_handles_curl_failure(monkeypatch):
    # ให้ทุกคำสั่งคืน returncode != 0 (จำลอง curl ต่อไม่ติด)
    def _fake_run(cmd, capture_output=True, text=True, timeout=None):
        class _R:
            returncode = 7
            stdout = ""
            stderr = "curl: (7) Failed to connect"
        return _R()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    net = NetworkController(iface="eth0")
    probe = net.background_transfer_probe("http://unreachable:11434/api/tags")
    assert "error" in probe


def test_read_tcp_retrans_snapshot_parses_retrans_segs(monkeypatch, tmp_path):
    snmp_file = tmp_path / "snmp"
    snmp_file.write_text(SNMP_SAMPLE, encoding="utf-8")

    import builtins
    real_open = builtins.open

    def _fake_open(path, *args, **kwargs):
        if path == "/proc/net/snmp":
            return real_open(snmp_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _fake_open)

    net = NetworkController(iface="eth0")
    snap = net.read_tcp_retrans_snapshot()
    assert snap["retrans_segs"] == 1516


# ---------- stress tests เพิ่มเติม: รูปแบบ output จริงที่หลากหลายกว่า happy-path เดิม ----------

QDISC_SHOW_MULTI_STANZA_SAMPLE = """qdisc netem 1: root refcnt 2 limit 1000 delay 100ms loss 75%
 Sent 500 bytes 5 pkt (dropped 187, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
qdisc tbf 10: parent 1: rate 50Kbit burst 32Kb lat 400.0ms
 Sent 500 bytes 5 pkt (dropped 3, overlimits 9 requeues 0)
 backlog 0b 0p requeues 0
"""

QDISC_SHOW_BASELINE_NOQUEUE_SAMPLE = """qdisc noqueue 0: root refcnt 2
 Sent 0 bytes 0 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
"""

PING_SAMPLE_BSD_STYLE = """PING 8.8.8.8 (8.8.8.8): 56 data bytes

--- 8.8.8.8 ping statistics ---
5 packets transmitted, 5 packets received, 0.0% packet loss
rtt min/avg/max/mdev = 10.111/11.222/12.333/1.444 ms
"""

SNMP_SAMPLE_MISSING_TCP_SECTION = (
    "Ip: Forwarding DefaultTTL InReceives InHdrErrors\n"
    "Ip: 1 64 100 0\n"
)


def test_read_qdisc_counters_multi_stanza_uses_first_stanza_only(mock_tc):
    """เมื่อมีทั้ง netem (root handle 1:) และ tbf (handle 10:) ผูกพร้อมกัน (เช่น
    scenario ที่ตั้งทั้ง delay/loss และ bandwidth พร้อมกัน) `.search()` จะจับ
    stanza แรก (netem) เท่านั้น ไม่รวม stanza ของ tbf — เป็นพฤติกรรมที่ตั้งใจ
    (ไม่ throw, ไม่ parse ผิด) แต่ต้องรู้ข้อจำกัดนี้ไว้ชัดเจน: ตัวเลข dropped/
    overlimits ที่ได้จะไม่รวม overlimits ของ tbf (ซึ่งเป็นจุดที่ bandwidth-limit
    ทำให้เกิด drop จริง) ปัจจุบัน 5 scenario ของ run_tier8_achieved_path.py และ
    run_tier8_ingress.py ไม่มี scenario ไหนตั้งทั้ง delay/loss+bandwidth พร้อมกัน
    เลย จึงไม่กระทบข้อมูลจริงที่เก็บ แต่เทสนี้ยืนยัน "ไม่ throw" ไว้ล่วงหน้า"""
    mock_tc.stdout_map["-s qdisc show"] = QDISC_SHOW_MULTI_STANZA_SAMPLE
    net = NetworkController(iface="eth0")
    counters = net.read_qdisc_counters()
    # ต้อง parse ได้ (ไม่ error) และเป็นค่าจาก stanza แรก (netem, dropped=187)
    # ไม่ใช่ค่าของ tbf (dropped=3, overlimits=9)
    assert counters["dropped"] == 187
    assert counters["overlimits"] == 0
    assert "raw" in counters  # ค่าดิบทั้งสอง stanza ยังอยู่ใน raw เผื่อต้องตรวจย้อนหลัง


def test_read_qdisc_counters_baseline_noqueue_parses_zero_counters(mock_tc):
    """baseline (ไม่มี netem/tbf เลย, qdisc เป็น noqueue ค่าเริ่มต้นของ Linux)
    ต้อง parse ได้ปกติ ไม่ error แม้ตัวเลขทุกตัวเป็น 0"""
    mock_tc.stdout_map["-s qdisc show"] = QDISC_SHOW_BASELINE_NOQUEUE_SAMPLE
    net = NetworkController(iface="eth0")
    counters = net.read_qdisc_counters()
    assert "error" not in counters
    assert counters["sent_bytes"] == 0
    assert counters["sent_pkts"] == 0
    assert counters["dropped"] == 0


def test_measure_rtt_ms_parses_bsd_style_packets_received_wording(mock_tc):
    """บาง ping implementation (เช่น BSD/macOS) เขียนว่า "packets received"
    (มีคำว่า packets ซ้ำ) แทนที่จะเป็น "received" เฉยๆ แบบ iputils-ping ของ
    Linux — regex ต้องรองรับทั้งสองแบบผ่าน (?:packets )? ที่เป็น optional"""
    mock_tc.stdout_map["ping"] = PING_SAMPLE_BSD_STYLE
    net = NetworkController(iface="eth0")
    rtt = net.measure_rtt_ms("8.8.8.8", count=5)
    assert rtt["packets_sent"] == 5
    assert rtt["packets_received"] == 5
    assert rtt["packet_loss_pct"] == 0.0
    assert rtt["avg_ms"] == 11.222


def test_background_transfer_probe_handles_malformed_curl_w_output(mock_tc):
    """ถ้า curl -w คืนค่าที่ไม่ตรงรูปแบบ "bytes seconds" ที่คาด (เช่น field
    หายไปหนึ่งตัวเพราะ curl version ต่างกันหรือ URL ไม่ถูกต้อง) ต้องคืน error
    แบบ graceful ไม่ throw ValueError/IndexError หลุดออกมา"""
    mock_tc.stdout_map["curl"] = "2048"  # ขาด time_total ไปหนึ่งตัว
    net = NetworkController(iface="eth0")
    probe = net.background_transfer_probe("http://host.docker.internal:11434/api/tags")
    assert "error" in probe


def test_read_tcp_retrans_snapshot_missing_tcp_section_returns_error(monkeypatch, tmp_path):
    """/proc/net/snmp ที่ไม่มี section 'Tcp:' เลย (เช่นระบบที่ปิด IPv4 TCP stack
    หรือไฟล์ถูก strip ผิดปกติ) ต้องคืน error แบบ graceful ไม่ throw"""
    snmp_file = tmp_path / "snmp_no_tcp"
    snmp_file.write_text(SNMP_SAMPLE_MISSING_TCP_SECTION, encoding="utf-8")

    import builtins
    real_open = builtins.open

    def _fake_open(path, *args, **kwargs):
        if path == "/proc/net/snmp":
            return real_open(snmp_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _fake_open)

    net = NetworkController(iface="eth0")
    snap = net.read_tcp_retrans_snapshot()
    assert "error" in snap


def test_snapshot_achieved_includes_ifb_only_when_direction_both(mock_tc):
    mock_tc.stdout_map["-s qdisc show"] = QDISC_SHOW_SAMPLE
    net_egress = NetworkController(iface="eth0", direction="egress")
    snap_egress = net_egress.snapshot_achieved()
    assert "qdisc_ingress_ifb" not in snap_egress

    net_both = NetworkController(iface="eth0", direction="both", ifb_dev="ifb0")
    snap_both = net_both.snapshot_achieved()
    assert "qdisc_ingress_ifb" in snap_both
