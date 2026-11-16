# -*- coding: utf-8 -*-
"""常驻重试：直连 -> 代理 -> Wayback -> jina 读取器；断点续传；成功即记录。"""
import subprocess, sys, json, hashlib, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"D:\数学建模acm")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
PROXY = "http://127.0.0.1:7897"
LOG = ROOT/"_fetch_retry.log"
def log(m):
    with LOG.open("a", encoding="utf-8") as f: f.write(time.strftime("%H:%M:%S ") + m + "\n")

TARGETS = [
 ("https://mtfchallenge.org/wp-content/uploads/2025/08/CRA-Action-Plan-2025.pdf",
  "资料/06_学术文献/CRA_Cooling_Center_Costs_2025.pdf", "pdf", 5_000_000),
 ("https://azmag.gov/Programs/Community-Initiatives/Heat-Relief-Network",
  "资料/02_降温网络/MAG_Heat_Relief_Network.md", "text", 2_000),
 ("https://www.maricopa.gov/1858/Heat-Surveillance",
  "资料/03_健康与暴露/Maricopa_Heat_Surveillance_Page.md", "text", 2_000),
 ("https://globalfutures.asu.edu/caplter/wp-content/uploads/sites/33/2024/06/Elser-etal.pdf",
  "资料/06_学术文献/Elser_GrowingShade_Phoenix.pdf", "pdf", 200_000),
 ("https://pmc.ncbi.nlm.nih.gov/articles/PMC12087966/",
  "资料/06_学术文献/PNAS2025_heat_adaptation.md", "text", 2_000),
]

def run(cmd, timeout=200):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return f"ERR {e}"

def proxy_ok():
    out = run(["curl","-s","-o","NUL","-w","%{http_code}","--max-time","5","--proxy",PROXY,"https://github.com"], 20)
    return "200" in out

def valid(p: Path, kind: str) -> bool:
    if not p.exists(): return False
    head = p.open("rb").read(5)
    if kind == "pdf": return head.startswith(b"%PDF") and p.stat().st_size > 50_000
    return b"<" in head or p.stat().st_size > 2_000

deadline = time.time() + 25*60
pending = list(TARGETS)
rounds = 0
while pending and time.time() < deadline:
    rounds += 1
    px = proxy_ok()
    log(f"--- 第 {rounds} 轮, 代理={'up' if px else 'down'}, 待抓 {len(pending)}")
    for url, out, kind, minb in list(pending):
        p = ROOT/out; p.parent.mkdir(parents=True, exist_ok=True)
        variants = [("direct", [])]
        if px: variants.append(("proxy", ["--proxy", PROXY]))
        variants.append(("wayback", None))
        ok = False
        for name, extra in variants:
            if kind == "text" and name != "wayback":
                target = f"https://r.jina.ai/{url}"
            elif name == "wayback":
                target = f"https://web.archive.org/web/2026id_/{url}"
            else:
                target = url
            cmd = ["curl","-sSL","--ssl-no-revoke","--max-time","150","-A",UA]
            if kind == "pdf": cmd += ["-C","-"]
            cmd += (extra or []) + ["-o", str(p), "-w", "%{http_code}"]
            out_s = run(cmd)
            size = p.stat().st_size if p.exists() else 0
            log(f"  {out.split('/')[-1]} via {name}: code={out_s.strip()[-3:]} size={size}")
            if valid(p, kind) and size >= minb:
                ok = True; log(f"  OK {out} via {name}"); break
        if ok: pending.remove((url, out, kind, minb))
    if pending: time.sleep(40)
log(f"结束: 剩余 {len(pending)}")
print("done", len(pending))
