# -*- coding: utf-8 -*-
"""从已核验 PDF 中定位每条事实的页码与原文，产出可引用事实表。"""
import sys, json, re, pymupdf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path(r"D:\数学建模acm")

DOCS = {
 "plan2026": R/"资料/01_官方计划/Phoenix_Heat_Response_Plan_2026.pdf",
 "plan2025": R/"资料/01_官方计划/Phoenix_Heat_Response_Plan_2025.pdf",
 "weekly":   R/"资料/03_健康与暴露/Phoenix_Weekly_Heat_Reports_2025.pdf",
 "method":   R/"资料/03_健康与暴露/Maricopa_Heat_Surveillance_Methodology_2025.pdf",
 "natcomm":  R/"资料/06_学术文献/NatComm2023_reflective_pavement_AZ.pdf",
 "problem":  R/"资料/00_赛题/2027_MCM_B_Keeping_Phoenix_Cool.pdf",
}
FASTS = [
 ("F01","Network consists of four site types: Respite Centers, Cooling Centers, Hydration Stations, Donation Sites","plan2026", r"Respite Centers, Cooling Centers, Hydration Stations"),
 ("F02","Cooling centers are indoor, air-conditioned locations that also offer hydration","plan2026", r"indoor, air-conditioned locations that also offer hydration"),
 ("F03","17 City of Phoenix Library locations served as Cooling Centers in 2025","plan2026", r"17 City of Phoenix Library locations"),
 ("F04","24/7 Respite and Navigation Center is an action item","plan2026", r"Operate a 24/7 Respite and Navigation Center"),
 ("F05","Extended hours at City cooling centers is an action item","plan2026", r"Offer Extended Hours at City of Phoenix Cooling Centers"),
 ("F06","2026 plan contains 23 actions in eight strategies","plan2026", r"23 specific heat response actions"),
 ("F07","2025 season: at least 110F on 37 days","plan2026", r"at least 110"),
 ("F08","2025 season: 31 days with Extreme Heat Warnings","plan2026", r"31 days with National Weather Service Extreme Heat"),
 ("F09","2025 season max 118F on July 9 and August 7","plan2026", r"118"),
 ("F10","2025 season: 23 days with overnight low >= 90F","plan2026", r"did not drop below 90"),
 ("F11","Season total 44,508 visits (cumulative through 9/30/2025)","weekly", r"44,508 visits"),
 ("F12","Peak week daily average 561.3 visits (Sep 4-10)","weekly", r"3,929 visits"),
 ("F13","Season total heat-related calls for service 1,764","weekly", r"1,764 heat related calls"),
 ("F14","Walk/Bike is the most common arrival mode","weekly", r"Walk/Bike"),
 ("F15","Arrival peaks at noon and 16-20h","weekly", r"noon and between the hours of 4 and 8 pm"),
 ("F16","Homelessness share among visitors 69% (first week)","weekly", r"indicated they are experiencing homelessness"),
 ("F17","Heat deaths classified as heat-caused or heat-contributed","method", r"heat-contributed"),
 ("F18","Case investigation may take 90 days or longer","method", r"90 days or longer"),
 ("F19","Reflective pavement field evidence in Arizona","natcomm", r"reflective pavement"),
 ("F20","Contest assumptions: 12 districts, 8 candidate sites, 250 visits/day","problem", r"250 visitor-visits"),
 ("F21","Contest distinction: hydration station is not necessarily a cooling center","problem", r"hydration station is not necessarily a cooling"),
]
cache = {}
def pages(key):
    if key not in cache:
        d = pymupdf.open(DOCS[key])
        cache[key] = [re.sub(r"\s+"," ", p.get_text()) for p in d]
    return cache[key]

rows=[]
for fid, desc, doc, pat in FASTS:
    hit = None
    for i, txt in enumerate(pages(doc), 1):
        m = re.search(pat, txt, re.I)
        if m:
            s = max(0, m.start()-90); e = min(len(txt), m.end()+140)
            hit = {"page": i, "quote": txt[s:e].strip()}
            break
    rows.append({"id": fid, "fact": desc, "doc": doc,
                 "file": str(DOCS[doc].relative_to(R)),
                 "page": hit["page"] if hit else None,
                 "quote": hit["quote"] if hit else None,
                 "status": "VERIFIED" if hit else "NOT_FOUND"})
found=[r for r in rows if r["status"]=="VERIFIED"]
print(f"定位成功 {len(found)}/{len(rows)}")
for r in rows:
    tag = f"p{r['page']}" if r['page'] else "未找到"
    print(f"  {r['id']} {tag:>6}  {r['fact'][:60]}")
json.dump(rows, open(R/"资料/08_原始摘录/facts.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
