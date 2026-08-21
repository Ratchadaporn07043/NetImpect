"""
Network Controller — Tier 9 (standalone copy)
========================================================================
สำเนา byte-identical จาก Tier 8's `controller.py` เปลี่ยนแค่ชื่อไฟล์เป็น
`tier9_controller.py` เพื่อให้ Tier 9 เป็น standalone เต็มรูปแบบ (ไม่ import
ข้าม tier) — เนื้อหาและประวัติที่มาด้านล่างคงไว้ตามเดิมจาก Tier 8 ทั้งหมด:

สร้างใหม่ทั้งไฟล์ (ไม่ใช่แก้ของเดิม) เพราะ `experiment/controller.py` ที่ root
โปรเจกต์ตรวจยืนยันแล้วว่า **ไม่มี** parameter `direction`/`ifb_dev` และไม่มี
`probe_ingress_support()` เลย ทั้งที่เอกสารเก่าเคยเขียนว่าเพิ่มไปแล้ว — เพื่อไม่ให้
เกิดปัญหาแบบเดียวกับ 7A/7B อีก (โค้ดที่ "บันทึกว่าเพิ่มแล้ว" ไม่ตรงกับไฟล์ที่ import
จริงตอนรัน) ไฟล์นี้จึงเป็นของใหม่ทั้งหมด แยกโฟลเดอร์ ตรวจสอบได้ในตัวเอง

ความสามารถ 3 กลุ่ม (ตรงกับข้อ 1 และ 4 ใน 5 ข้อที่ต้องรัน):

1. Egress shaping (ของเดิม, พฤติกรรมต้องเหมือนเดิมทุกประการ เมื่อ direction="egress")
   — ใช้ arm นี้กับข้อ 2 (fixed-long-timeout) และข้อ 5 (jitter floor control)
   เพื่อให้เทียบกับ 5,300 trials เดิมได้ตรงๆ โดยไม่มีตัวแปรที่สองเปลี่ยนไปด้วย

2. Bidirectional shaping (direction="both") — ข้อ 4: redirect ingress ไป IFB
   device แล้ว mirror netem/tbf เดียวกับ egress ไปที่นั่น ค่าเริ่มต้นของ
   `direction` ยังเป็น "egress" เสมอ (ต้องเปิดเองอย่างชัดเจน) กันไม่ให้สคริปต์ไหน
   ที่ลืมส่ง direction เผลอไปเปลี่ยนพฤติกรรม egress-only เดิม

3. Achieved-path measurement — ข้อ 1: อ่าน `tc -s qdisc` counters, วัด RTT จริง
   ด้วย ping, อ่าน TCP retransmission counter จาก `/proc/net/snmp`, และวัด
   throughput จริงด้วย background transfer probe (curl) — ทั้งหมดนี้ใช้เครื่องมือ
   ที่ Dockerfile ของโปรเจกต์ติดตั้งไว้แล้ว (iproute2, iputils-ping, curl) ไม่ต้อง
   ติดตั้งอะไรเพิ่ม

หมายเหตุสำคัญที่สืบทอดจาก `experiment/controller.py` เดิม (ยังจริงเสมอเมื่อ
direction="egress" ค่าเริ่มต้น): qdisc ที่ผูกไว้ที่ `root` ของ interface ควบคุม
egress (ขาออก) เท่านั้น การเพิ่ม direction="both" ในไฟล์นี้ไม่ได้เปลี่ยนพฤติกรรม
เริ่มต้นของ 5,300 trials เดิมแต่อย่างใด — ต้องเปิดใช้อย่างชัดเจนเท่านั้น
"""

import re
import subprocess
import time

DIRECTIONS = ("egress", "both")

# เหมือน experiment/controller.py เดิม "เป๊ะ" (4 รายการนี้เท่านั้น) — ใช้กับ
# egress clear เท่านั้น เพื่อการันตีว่า direction="egress" มีพฤติกรรมเหมือนเดิม
# ทุกประการ ไม่เพิ่ม/ลดเงื่อนไขใดๆ จากของเดิมแม้แต่นิดเดียว
_HARMLESS_TC_ERRORS_EGRESS_ORIGINAL = (
    "Cannot delete qdisc with handle of zero",
    "No such file or directory",
    "Invalid argument",
    "Cannot find device",
)

# เพิ่ม "Invalid handle" เฉพาะสำหรับเส้นทางใหม่ (ingress/IFB) ที่ไม่มีในไฟล์เดิม —
# พบจริงจาก `tc qdisc del dev eth0 ingress` เมื่อไม่มี qdisc ผูกอยู่ก่อน (handle
# ffff: ต่างจาก root ที่ handle 0 จึงได้ error message คนละแบบ) ต้องแยกออกจาก
# _HARMLESS_TC_ERRORS_EGRESS_ORIGINAL อย่างเคร่งครัด ไม่ให้ปนกับเส้นทาง egress เดิม
_HARMLESS_TC_ERRORS_INGRESS_IFB = _HARMLESS_TC_ERRORS_EGRESS_ORIGINAL + ("Invalid handle",)

_HARMLESS_SETUP_NOTES = (
    "File exists",
    "RTNETLINK answers: File exists",
)


class NetworkController:
    def __init__(self, iface: str = "eth0", direction: str = "egress", ifb_dev: str = "ifb0"):
        if direction not in DIRECTIONS:
            raise ValueError(f"direction ต้องเป็นหนึ่งใน {DIRECTIONS} แต่ได้ {direction!r}")
        self.iface = iface
        self.direction = direction
        self.ifb_dev = ifb_dev

    # ------------------------------------------------------------------
    # low-level helpers
    # ------------------------------------------------------------------
    def _run(self, cmd: list, timeout: float = 15.0):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "cmd": " ".join(cmd),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"timed out after {timeout}s: {exc}",
                "cmd": " ".join(cmd),
            }
        except FileNotFoundError as exc:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"command not found: {exc}",
                "cmd": " ".join(cmd),
            }

    @staticmethod
    def _is_harmless(result: dict, harmless_substrings) -> bool:
        stderr = result.get("stderr", "") or ""
        return any(msg in stderr for msg in harmless_substrings)

    # ------------------------------------------------------------------
    # egress clear / apply — เหมือน experiment/controller.py เดิมทุกประการ
    # เมื่อ direction="egress" (ค่าเริ่มต้น)
    # ------------------------------------------------------------------
    def _clear_egress(self):
        result = self._run(["tc", "qdisc", "del", "dev", self.iface, "root"])
        if result["returncode"] != 0 and self._is_harmless(result, _HARMLESS_TC_ERRORS_EGRESS_ORIGINAL):
            result["returncode"] = 0
            result["note"] = "clear skipped: no existing qdisc"
        return result

    def _clear_ingress(self):
        """ล้าง ingress qdisc (ที่ผูก mirred redirect ไว้) บน self.iface"""
        result = self._run(["tc", "qdisc", "del", "dev", self.iface, "ingress"])
        if result["returncode"] != 0 and self._is_harmless(result, _HARMLESS_TC_ERRORS_INGRESS_IFB):
            result["returncode"] = 0
            result["note"] = "clear skipped: no existing ingress qdisc"
        return result

    def _clear_ifb(self):
        """ล้าง root qdisc บน IFB device (ที่ mirror netem/tbf ของฝั่ง ingress ไว้)"""
        result = self._run(["tc", "qdisc", "del", "dev", self.ifb_dev, "root"])
        if result["returncode"] != 0 and self._is_harmless(result, _HARMLESS_TC_ERRORS_INGRESS_IFB):
            result["returncode"] = 0
            result["note"] = "clear skipped: no existing qdisc"
        return result

    def clear(self):
        """ล้าง netem/tbf rule ทั้งหมด กลับสู่ baseline
        direction="egress": พฤติกรรมเดิมเป๊ะ (แค่ egress root qdisc)
        direction="both": ล้าง ingress redirect + IFB root qdisc เพิ่มด้วย"""
        result = self._clear_egress()
        if self.direction == "both":
            result["ingress"] = self._clear_ingress()
            result["ifb"] = self._clear_ifb()
        return result

    def _setup_ingress_redirect(self):
        """ตั้ง IFB device + ingress redirect (idempotent — เรียกซ้ำได้ปลอดภัย
        เพราะเช็ค stderr ว่า 'device/qdisc มีอยู่แล้ว' แล้วไม่ถือเป็น error)"""
        steps = []

        r_link_add = self._run(["ip", "link", "add", self.ifb_dev, "type", "ifb"])
        if r_link_add["returncode"] != 0 and self._is_harmless(r_link_add, _HARMLESS_SETUP_NOTES):
            r_link_add["returncode"] = 0
            r_link_add["note"] = "ifb device already exists"
        steps.append({"step": "ip_link_add_ifb", "result": r_link_add})

        r_link_up = self._run(["ip", "link", "set", "dev", self.ifb_dev, "up"])
        steps.append({"step": "ip_link_set_ifb_up", "result": r_link_up})

        r_ingress_qdisc = self._run(["tc", "qdisc", "add", "dev", self.iface, "ingress"])
        if r_ingress_qdisc["returncode"] != 0 and self._is_harmless(r_ingress_qdisc, _HARMLESS_SETUP_NOTES):
            r_ingress_qdisc["returncode"] = 0
            r_ingress_qdisc["note"] = "ingress qdisc already exists"
        steps.append({"step": "tc_ingress_qdisc", "result": r_ingress_qdisc})

        r_redirect = self._run([
            "tc", "filter", "add", "dev", self.iface, "parent", "ffff:",
            "protocol", "all", "u32", "match", "u32", "0", "0",
            "action", "mirred", "egress", "redirect", "dev", self.ifb_dev,
        ])
        if r_redirect["returncode"] != 0 and self._is_harmless(r_redirect, _HARMLESS_SETUP_NOTES):
            r_redirect["returncode"] = 0
            r_redirect["note"] = "redirect filter already exists"
        steps.append({"step": "tc_ingress_redirect", "result": r_redirect})

        overall_rc = max(s["result"]["returncode"] for s in steps)
        return {
            "returncode": overall_rc,
            "stdout": "",
            "stderr": "" if overall_rc == 0 else "one or more ingress_setup steps failed, see steps[]",
            "cmd": "setup ingress redirect",
            "steps": steps,
        }

    def apply(
        self,
        delay_ms: int = 0,
        jitter_ms: int = 0,
        loss_pct: float = 0,
        bandwidth_kbit: int = None,
    ):
        """ใส่ network impairment ตาม scenario
        direction="egress": เหมือน experiment/controller.py เดิมทุกประการ
        direction="both": ใส่กฎเดียวกันที่ IFB (ingress) เพิ่มด้วย"""

        clear_result = self.clear()

        has_bandwidth = bandwidth_kbit is not None and bandwidth_kbit > 0

        if delay_ms == 0 and jitter_ms == 0 and loss_pct == 0 and not has_bandwidth:
            result = {
                "returncode": 0,
                "stdout": "baseline (no impairment)",
                "stderr": "",
                "cmd": "baseline",
                "clear_before_apply": clear_result,
            }
            if self.direction == "both":
                result["ingress_setup"] = self._setup_ingress_redirect()
                result["ingress"] = None  # baseline: ไม่มี netem/tbf ให้ mirror ที่ ifb
            return result

        def _build_netem_cmd(dev):
            cmd = ["tc", "qdisc", "add", "dev", dev, "root", "handle", "1:", "netem"]
            if delay_ms > 0:
                cmd += ["delay", f"{delay_ms}ms"]
                if jitter_ms > 0:
                    cmd += [f"{jitter_ms}ms"]
            elif jitter_ms > 0:
                return None
            if loss_pct > 0:
                cmd += ["loss", f"{loss_pct}%"]
            return cmd

        egress_cmd = _build_netem_cmd(self.iface)
        if egress_cmd is None:
            # เหมือน experiment/controller.py เดิมเป๊ะ: "cmd" ในผลลัพธ์ error คือ
            # netem_cmd ฐาน (ก่อนใส่ delay/loss) join กันไว้ ไม่ใช่ค่าว่าง —
            # ต้องสร้างคำสั่งฐานซ้ำที่นี่เพราะ _build_netem_cmd คืน None ไปแล้ว
            base_cmd = ["tc", "qdisc", "add", "dev", self.iface, "root", "handle", "1:", "netem"]
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": "jitter_ms > 0 requires delay_ms > 0",
                "cmd": " ".join(base_cmd),
                "clear_before_apply": clear_result,
            }

        netem_result = self._run(egress_cmd)
        netem_result["clear_before_apply"] = clear_result

        tbf_result = None
        if has_bandwidth:
            tbf_cmd = [
                "tc", "qdisc", "add", "dev", self.iface, "parent", "1:", "handle", "10:",
                "tbf", "rate", f"{bandwidth_kbit}kbit", "burst", "32kbit", "latency", "400ms",
            ]
            tbf_result = self._run(tbf_cmd)
        netem_result["tbf"] = tbf_result

        if self.direction == "both":
            netem_result["ingress_setup"] = self._setup_ingress_redirect()

            ifb_cmd = _build_netem_cmd(self.ifb_dev)
            ifb_netem_result = self._run(ifb_cmd)
            ifb_tbf_result = None
            if has_bandwidth:
                ifb_tbf_cmd = [
                    "tc", "qdisc", "add", "dev", self.ifb_dev, "parent", "1:", "handle", "10:",
                    "tbf", "rate", f"{bandwidth_kbit}kbit", "burst", "32kbit", "latency", "400ms",
                ]
                ifb_tbf_result = self._run(ifb_tbf_cmd)
            ifb_netem_result["tbf"] = ifb_tbf_result
            netem_result["ingress"] = ifb_netem_result

        return netem_result

    def current_status(self):
        """direction="egress": คืนค่าเป็น string เดียว เหมือน experiment/controller.py
        เดิมทุกประการ (ไม่ใช่ dict) เพื่อการันตี byte-identical กับของเดิมจริงๆ —
        ผู้เรียกโค้ดเดิมที่คาดหวัง string จะไม่พังถ้าสลับมาใช้ direction="egress"
        direction="both": คืนค่าเป็น dict {"egress","ingress","ifb"} เพราะต้องรายงาน
        สามจุดพร้อมกัน ซึ่งเป็นรูปแบบใหม่ที่ไม่มีในของเดิม (ของเดิมไม่มี ingress/ifb)"""
        egress_status = self._run(["tc", "qdisc", "show", "dev", self.iface])["stdout"].strip()
        if self.direction != "both":
            return egress_status
        return {
            "egress": egress_status,
            "ingress": self._run(["tc", "qdisc", "show", "dev", self.iface, "ingress"])["stdout"].strip(),
            "ifb": self._run(["tc", "qdisc", "show", "dev", self.ifb_dev])["stdout"].strip(),
        }

    # ------------------------------------------------------------------
    # ข้อ 4: preflight probe ก่อนใช้ direction="both" จริง
    # ------------------------------------------------------------------
    def probe_ingress_support(self):
        """ตรวจว่าสภาพแวดล้อมรองรับ ingress+IFB จริงก่อนรันอะไรทั้งคืน
        คืนค่า {"supported": bool, "reason": str, "checks": [...]}
        ทำงานแบบ idempotent/non-destructive: ถ้า ifb0 ไม่เคยมีมาก่อน จะสร้างแล้ว
        เก็บไว้ (ใช้ต่อได้ใน apply() ครั้งถัดไป) ไม่ลบทิ้งหลังตรวจ เพราะการสร้าง
        ซ้ำไม่มีผลเสีย (idempotent) และการลบ-สร้างสลับกันมีความเสี่ยงมากกว่า"""
        checks = []

        r_ip = self._run(["ip", "-V"])
        checks.append({"check": "ip_command_available", "result": r_ip})
        if r_ip["returncode"] != 0:
            return {"supported": False, "reason": "คำสั่ง `ip` ใช้ไม่ได้ในสภาพแวดล้อมนี้", "checks": checks}

        r_link_add = self._run(["ip", "link", "add", self.ifb_dev, "type", "ifb"])
        ifb_ok = r_link_add["returncode"] == 0 or self._is_harmless(r_link_add, _HARMLESS_SETUP_NOTES)
        checks.append({"check": "ifb_kernel_module_or_device", "result": r_link_add})
        if not ifb_ok:
            return {
                "supported": False,
                "reason": (
                    "สร้าง ifb device ไม่ได้ — kernel module `ifb` ยังไม่ถูกโหลดบน host "
                    f"stderr: {r_link_add.get('stderr', '')[:200]!r} "
                    "แก้ด้วย: sudo modprobe ifb numifbs=0 (รันบน HOST ไม่ใช่ใน container)"
                ),
                "checks": checks,
            }

        r_link_up = self._run(["ip", "link", "set", "dev", self.ifb_dev, "up"])
        checks.append({"check": "ifb_link_up", "result": r_link_up})
        if r_link_up["returncode"] != 0:
            return {
                "supported": False,
                "reason": f"เปิด ifb device ไม่ได้: {r_link_up.get('stderr', '')[:200]!r}",
                "checks": checks,
            }

        r_ingress = self._run(["tc", "qdisc", "add", "dev", self.iface, "ingress"])
        ingress_ok = r_ingress["returncode"] == 0 or self._is_harmless(r_ingress, _HARMLESS_SETUP_NOTES)
        checks.append({"check": "tc_ingress_qdisc", "result": r_ingress})
        if not ingress_ok:
            return {
                "supported": False,
                "reason": (
                    f"สร้าง ingress qdisc บน {self.iface} ไม่ได้: "
                    f"{r_ingress.get('stderr', '')[:200]!r} — ตรวจว่า container มี NET_ADMIN capability"
                ),
                "checks": checks,
            }

        r_filter = self._run([
            "tc", "filter", "add", "dev", self.iface, "parent", "ffff:",
            "protocol", "all", "u32", "match", "u32", "0", "0",
            "action", "mirred", "egress", "redirect", "dev", self.ifb_dev,
        ])
        filter_ok = r_filter["returncode"] == 0 or self._is_harmless(r_filter, _HARMLESS_SETUP_NOTES)
        checks.append({"check": "tc_mirred_redirect_filter", "result": r_filter})
        if not filter_ok:
            return {
                "supported": False,
                "reason": (
                    f"เพิ่ม mirred redirect filter ไม่ได้: {r_filter.get('stderr', '')[:200]!r} — "
                    "kernel อาจไม่มี act_mirred module (`modprobe act_mirred` บน host)"
                ),
                "checks": checks,
            }

        return {"supported": True, "reason": "ทุกจุดตรวจผ่าน", "checks": checks}

    # ------------------------------------------------------------------
    # ข้อ 4 (เสริม): ปิด checksum offload — สาเหตุที่พบบ่อยที่สุดของ packet drop
    # แปลกๆ เมื่อ redirect ผ่าน mirred/ifb ในสภาพแวดล้อม container/VM
    # (ผลข้างเคียงที่รู้จักกันดีของ tc mirred + ifb เมื่อ NIC ยังเปิด rx/tx
    # checksum offload อยู่ — ทำให้ checksum ที่คำนวณจริงกับที่ kernel คาดหวัง
    # ไม่ตรงกันหลัง redirect แล้วแพ็กเก็ตถูกดรอปแม้ไม่ได้ตั้ง loss ไว้เลย)
    # best-effort เท่านั้น: ถ้า ethtool ใช้ไม่ได้/สิทธิ์ไม่พอ จะไม่ throw แค่รายงาน
    # ------------------------------------------------------------------
    def disable_checksum_offload(self):
        result = self._run(["ethtool", "-K", self.iface, "rx", "off", "tx", "off"])
        return result

    # ------------------------------------------------------------------
    # ข้อ 1: achieved-path measurement
    # ------------------------------------------------------------------
    _QDISC_COUNTER_RE = re.compile(
        r"Sent (?P<bytes>\d+) bytes (?P<pkts>\d+) pkt \(dropped (?P<dropped>\d+), "
        r"overlimits (?P<overlimits>\d+) requeues (?P<requeues>\d+)\)"
    )

    def read_qdisc_counters(self, dev: str = None):
        """parse `tc -s qdisc show dev {dev}` -> sent bytes/pkts/dropped/overlimits/requeues
        คืน None ถ้า parse ไม่ได้ (เช่น ไม่มี qdisc ผูกอยู่เลย) แทนที่จะ throw"""
        dev = dev or self.iface
        result = self._run(["tc", "-s", "qdisc", "show", "dev", dev])
        if result["returncode"] != 0:
            return {"error": result.get("stderr", ""), "raw": result.get("stdout", "")}

        match = self._QDISC_COUNTER_RE.search(result["stdout"])
        if not match:
            return {"error": "ไม่พบ 'Sent ... bytes ... pkt (...)' ใน output", "raw": result["stdout"]}

        return {
            "dev": dev,
            "sent_bytes": int(match.group("bytes")),
            "sent_pkts": int(match.group("pkts")),
            "dropped": int(match.group("dropped")),
            "overlimits": int(match.group("overlimits")),
            "requeues": int(match.group("requeues")),
            "raw": result["stdout"],
        }

    def read_tcp_retrans_snapshot(self):
        """อ่าน system-wide TCP RetransSegs counter จาก /proc/net/snmp (ไฟล์
        มาตรฐานของ Linux, ไม่ต้องพึ่ง `ss`/`nstat` ซึ่งมีรูปแบบ output ต่างกันไป
        ตาม version) คืน None ถ้าอ่านไม่ได้ (เช่น รันนอก Linux หรือไม่มีสิทธิ์)"""
        try:
            with open("/proc/net/snmp", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            return {"error": f"อ่าน /proc/net/snmp ไม่ได้: {exc}"}

        header, values = None, None
        for i, line in enumerate(lines):
            if line.startswith("Tcp:") and header is None:
                header = line.split()
                # บรรทัดถัดไปที่ขึ้นต้นด้วย Tcp: คือค่าตัวเลข
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("Tcp:"):
                        values = lines[j].split()
                        break
                break

        if header is None or values is None:
            return {"error": "ไม่พบ section 'Tcp:' ใน /proc/net/snmp"}
        if "RetransSegs" not in header:
            return {"error": "ไม่พบคอลัมน์ RetransSegs ใน /proc/net/snmp"}

        idx = header.index("RetransSegs")
        try:
            retrans_segs = int(values[idx])
        except (IndexError, ValueError) as exc:
            return {"error": f"parse RetransSegs ไม่ได้: {exc}"}

        return {"retrans_segs": retrans_segs}

    _PING_SUMMARY_RE = re.compile(
        r"(?P<sent>\d+) packets transmitted, (?P<recv>\d+) (?:packets )?received,"
        r".*?(?P<loss>[\d.]+)% packet loss"
    )
    _PING_RTT_RE = re.compile(
        r"rtt min/avg/max/mdev = (?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)/(?P<mdev>[\d.]+) ms"
    )

    def measure_rtt_ms(self, target: str, count: int = 5, timeout: float = 15.0):
        """วัด RTT จริงด้วย ICMP ping ไปยัง target (เช่น Ollama host) — เป็นค่า
        achieved โดยตรง ไม่ขึ้นกับ configured delay/loss เลย ใช้ `ping` ที่ image
        ของโปรเจกต์ติดตั้งไว้แล้ว (iputils-ping ใน Dockerfile)"""
        result = self._run(["ping", "-c", str(count), "-q", target], timeout=timeout)
        parsed = {"target": target, "returncode": result["returncode"], "raw": result["stdout"]}

        loss_match = self._PING_SUMMARY_RE.search(result["stdout"])
        if loss_match:
            parsed["packets_sent"] = int(loss_match.group("sent"))
            parsed["packets_received"] = int(loss_match.group("recv"))
            parsed["packet_loss_pct"] = float(loss_match.group("loss"))

        rtt_match = self._PING_RTT_RE.search(result["stdout"])
        if rtt_match:
            parsed["min_ms"] = float(rtt_match.group("min"))
            parsed["avg_ms"] = float(rtt_match.group("avg"))
            parsed["max_ms"] = float(rtt_match.group("max"))
            parsed["mdev_ms"] = float(rtt_match.group("mdev"))
        else:
            parsed["note"] = "ทุก ping อาจสูญหายหมด (100% loss) จึงไม่มีบรรทัด rtt สรุป"

        return parsed

    def background_transfer_probe(self, url: str, timeout: float = 30.0):
        """วัด achieved throughput จริงด้วยการดาวน์โหลดจริงหนึ่งครั้งผ่าน curl
        (ติดตั้งไว้แล้วใน Dockerfile) — อิสระจาก LLM call เอง ใช้เป็น background
        throughput control ตามที่ Discussion §6.3 ของเปเปอร์ระบุไว้ว่าเป็นสิ่งที่
        ควรเพิ่ม"""
        result = self._run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{size_download} %{time_total}", url],
            timeout=timeout,
        )
        parsed = {"target": url, "returncode": result["returncode"]}
        if result["returncode"] != 0:
            parsed["error"] = result.get("stderr", "")
            return parsed

        parts = (result["stdout"] or "").split()
        if len(parts) != 2:
            parsed["error"] = f"curl -w output ไม่ตรงรูปแบบที่คาด: {result['stdout']!r}"
            return parsed

        size_bytes, seconds = int(parts[0]), float(parts[1])
        parsed["bytes"] = size_bytes
        parsed["seconds"] = seconds
        parsed["achieved_kbit_s"] = round((size_bytes * 8 / 1000) / seconds, 3) if seconds > 0 else None
        return parsed

    def snapshot_achieved(self, include_ingress: bool = None):
        """รวม qdisc counters (+ ifb ถ้า direction='both') กับ TCP retrans
        counter ไว้ในก้อนเดียว มี timestamp ของตัวเอง — เรียกก่อน/หลัง trial
        แล้วเอาผลต่าง (after - before) ไปตีความเป็น "achieved" ของ trial นั้น"""
        include_ingress = self.direction == "both" if include_ingress is None else include_ingress
        snap = {
            "timestamp": time.time(),
            "qdisc_egress": self.read_qdisc_counters(self.iface),
            "tcp_retrans": self.read_tcp_retrans_snapshot(),
        }
        if include_ingress:
            snap["qdisc_ingress_ifb"] = self.read_qdisc_counters(self.ifb_dev)
        return snap
