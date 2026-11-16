# -*- coding: utf-8 -*-
"""带断点续传 + 三级回退（直连 -> 代理 -> Wayback）的资料抓取。"""
import subprocess, sys, os, json, hashlib, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"D:\数学建模acm")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PROXY = "http://127.0.0.1:7897"

def probe_proxy():
    r = subprocess.run(["curl","-s","-o","NUL","-w","%{http_code}","--max-time","6","--proxy",PROXY,"https://github.com"],
                       capture_output=True, text=True, shell=False)
    return r.stdout.strip() == "200"

def fetch(url, out, tries=3, resume=True, min_bytes=20000):
    out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    variants = [("direct", [])]
    if PROBE:
        variants.append(("proxy", ["--proxy", PROXY]))
    variants.append(("wayback", None))   # 特殊处理
    log = []
    for name, extra in variants:
        for attempt in range(tries):
            if name == "wayback":
                target = f"https://web.archive.org/web/2026id_/{url}"
                extra = []
            else:
                target = url
            cmd = ["curl","-sSL","--ssl-no-revoke","--max-time","180","-A",UA]
            if resume: cmd += ["-C","-"]
            cmd += extra + ["-o", str(out), "-w", "%{http_code} %{size_download}", target]
            r = subprocess.run(cmd, capture_output=True, text=True)
            code = (r.stdout or "").split()[:2]
            size = out.stat().st_size if out.exists() else 0
            log.append(f"{name}#{attempt+1} {code} size={size}")
            if size >= min_bytes and is_valid(out):
                return {"ok": True, "via": name, "bytes": size, "log": log}
            if name == "wayback":
                break
            time.sleep(3)
    return {"ok": False, "via": None, "bytes": out.stat().st_size if out.exists() else 0, "log": log}

def is_valid(p: Path) -> bool:
    try:
        head = p.open("rb").read(5)
    except Exception:
        return False
    if p.suffix.lower() == ".pdf":
        return head.startswith(b"%PDF")
    if p.suffix.lower() in (".html",".htm"):
        return b"<" in head
    return True

PROBE = probe_proxy()
print("代理可用:", PROBE, flush=True)

TARGETS = [
 ("https://mtfchallenge.org/wp-content/uploads/2025/08/CRA-Action-Plan-2025.pdf",
  "资料/06_学术文献/CRA_Cooling_Center_Costs_2025.pdf", 5_000_000),
 ("https://azmag.gov/Programs/Community-Initiatives/Heat-Relief-Network",
  "资料/02_降温网络/MAG_Heat_Relief_Network.html", 20_000),
 ("https://www.maricopa.gov/1858/Heat-Surveillance",
  "资料/03_健康与暴露/Maricopa_Heat_Surveillance_Page.html", 20_000),
 ("https://www.phoenix.gov/administration/departments/heat/heat-response-programs/heat-response-plan.html",
  "资料/01_官方计划/Phoenix_Heat_Response_Plan_Page.html", 20_000),
 ("https://globalfutures.asu.edu/caplter/wp-content/uploads/sites/33/2024/06/Elser-etal.pdf",
  "资料/06_学术文献/Elser_GrowingShade_Phoenix.pdf", 200_000),
 ("https://pmc.ncbi.nlm.nih.gov/articles/PMC12087966/pdf/",
  "资料/06_学术文献/PNAS2025_heat_adaptation_prioritization.pdf", 200_000),
 ("https://www.nature.com/articles/s41467-023-36972-5.pdf",
  "资料/06_学术文献/NatComm2023_reflective_pavement_AZ.pdf", 200_000),
]
manifest = []
for url, out, minb in TARGETS:
    print(f"\n>>> {out}", flush=True)
    res = fetch(url, out, min_bytes=minb)
    print("   " + ("OK via " + res["via"] if res["ok"] else "FAIL") + f"  {res['bytes']} B", flush=True)
    for l in res["log"][-3:]:
        print("     " + l, flush=True)
    p = ROOT / out
    manifest.append({"url": url, "path": out, "ok": res["ok"], "via": res["via"],
                     "bytes": res["bytes"],
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None})
(ROOT/"资料/08_原始摘录/fetch_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
print("\n清单已写 资料/08_原始摘录/fetch_manifest.json")
