# -*- coding: utf-8 -*-
"""重建 data/processed 的四张核心 CSV（可复现）。

数据来源与可信层级（每条记录带 source 字段）：
  OBS_2025   2025 年 Phoenix 周报读出的观测量（人次、峰值）
  PLAN       官方计划/网络文本
  ESTIMATE   基于公开地理关系的估算（直线距离、人口量级）
  CONTEST    题面虚构参数（12 区、8 点、250 人次/日）

用法：python tools/build_data.py
"""
import csv, json, math, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"; OUT.mkdir(parents=True, exist_ok=True)

OBS = {"season_mean_visits_per_day": 292.8, "peak_week_visits_per_day": 561.3,
       "season_total_visits": 44508,
       "source": "Phoenix 2025 Weekly Heat Reports (city respite + extended-hour centers, 5/1-9/30/2025)"}

DISTRICTS = [
 ("D01","Central City","Central City",62000,0.11,0.24,48000,0.14,0.82,33.4484,-112.0740),
 ("D02","Encanto","Encanto",78000,0.13,0.17,52000,0.18,0.74,33.4700,-112.1000),
 ("D03","Alhambra-North Mountain","Alhambra; North Mountain",142000,0.15,0.16,47000,0.15,0.78,33.5400,-112.1200),
 ("D04","Camelback East","Camelback East",130000,0.12,0.09,76000,0.21,0.62,33.5000,-111.9900),
 ("D05","Deer Valley","Deer Valley",158000,0.10,0.05,92000,0.17,0.52,33.6900,-112.1200),
 ("D06","Desert View","Desert View",98000,0.09,0.07,78000,0.12,0.61,33.7800,-112.0000),
 ("D07","Estrella","Estrella",86000,0.08,0.05,88000,0.10,0.57,33.4000,-112.3000),
 ("D08","Laveen","Laveen",72000,0.09,0.09,74000,0.09,0.66,33.3500,-112.1700),
 ("D09","Maryvale","Maryvale",165000,0.09,0.21,39000,0.08,0.91,33.4900,-112.1900),
 ("D10","North Gateway-Rio Vista","North Gateway; Rio Vista",94000,0.11,0.04,96000,0.14,0.50,33.8200,-112.1000),
 ("D11","Paradise Valley","Paradise Valley",133000,0.17,0.06,105000,0.24,0.46,33.5900,-111.9500),
 ("D12","South Mountain-Ahwatukee","South Mountain; Ahwatukee Foothills",158000,0.13,0.06,88000,0.13,0.60,33.3400,-112.0500),
]
k_pop = 1_650_000 / sum(d[3] for d in DISTRICTS)
DISTRICTS = [(*d[:3], int(round(d[3]*k_pop)), *d[4:]) for d in DISTRICTS]

EXISTING = [
 ("C01","Central City Cooling Center","cooling","D01",33.4484,-112.0740,50,9,17),
 ("C02","Encanto Cooling Center","cooling","D02",33.4700,-112.1000,50,9,17),
 ("C03","North Mountain Cooling Center","cooling","D03",33.5650,-112.1200,50,9,17),
 ("C04","Camelback East Cooling Center","cooling","D04",33.5000,-111.9900,50,9,17),
 ("C05","Deer Valley Cooling Center","cooling","D05",33.6900,-112.1200,50,9,17),
 ("C06","Desert View Cooling Center","cooling","D06",33.7800,-112.0000,50,9,17),
 ("C07","South Mountain Cooling Center","cooling","D12",33.3400,-112.0500,50,9,17),
 ("C08","Maryvale Cooling Center","cooling","D09",33.4900,-112.1900,50,9,17),
 ("C09","Paradise Valley Cooling Center","cooling","D11",33.5900,-111.9500,50,9,17),
 ("H01","Laveen Hydration Station","hydration","D08",33.3500,-112.1700,0,10,16),
 ("H02","Estrella Hydration Station","hydration","D07",33.4000,-112.3000,0,10,16),
 ("H03","Rio Vista Hydration Station","hydration","D10",33.8200,-112.1000,0,10,16),
 ("H04","Ahwatukee Hydration Station","hydration","D12",33.3300,-112.0200,0,10,16),
 ("R01","24/7 Respite & Navigation Center","respite","D01",33.4490,-112.0700,120,0,24),
]
CANDIDATES = [
 ("MCH-1","Central City MCH","D01",33.4520,-112.0680),
 ("MCH-2","Encanto MCH","D02",33.4740,-112.0940),
 ("MCH-3","Maryvale MCH","D09",33.4940,-112.1860),
 ("MCH-4","South Mountain MCH","D12",33.3450,-112.0560),
 ("MCH-5","Camelback East MCH","D04",33.5050,-111.9950),
 ("MCH-6","Deer Valley MCH","D05",33.6950,-112.1150),
 ("MCH-7","Estrella Gap MCH","D07",33.4010,-112.2960),
 ("MCH-8","North Gateway Gap MCH","D10",33.8180,-112.1020),
]
MCH_CAP = 250

def hav(a,b,c,d):
    R=6371.0; p1,p2=math.radians(a),math.radians(c)
    dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

DETOUR=1.35; SPEED={"walk":4.8,"transit":15.0,"drive":30.0}; TRANSIT_WAIT=10.0
def vuln(p65,pnv,inc):
    return round((min(p65/0.30,1)+min(pnv/0.35,1)+min(max((110000-inc)/72000,0),1))/3,4)
DAY_FACTOR=[1.00,1.05,1.18,1.30,1.22,1.08,0.95]
def raw_demand(d, day):
    return d[3]*(0.4+0.6*d[8])*(0.6+0.8*vuln(d[4],d[5],d[6]))*DAY_FACTOR[day%7]

def main():
    with (OUT/"districts.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["district_id","district_name","villages_mapped","population",
            "pct_65plus","pct_no_vehicle","median_income_usd","canopy_pct","heat_exposure_index",
            "vulnerability","lat","lon","source","note"])
        for d in DISTRICTS:
            w.writerow([d[0],d[1],d[2],d[3],d[4],d[5],d[6],d[7],d[8],vuln(d[4],d[5],d[6]),d[9],d[10],
                "SYNTHETIC_ESTIMATE","12 districts are CONTEST fictions aggregated from Phoenix's 15 urban villages"])
    # 既有网络站点坐标 = 所在区质心（建模假设：设施位于其服务区内部）
    centroid = {d[0]: (d[9], d[10]) for d in DISTRICTS}
    EXISTING_FIXED = [(s[0], s[1], s[2], s[3], centroid[s[3]][0], centroid[s[3]][1], s[6], s[7], s[8])
                      for s in EXISTING]
    with (OUT/"sites.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["site_id","site_name","kind","district_id","lat","lon",
            "capacity_visits_per_day","open_hour","close_hour","source","note"])
        for s in EXISTING_FIXED:
            w.writerow([s[0],s[1],s[2],s[3],s[4],s[5],s[6],s[7],s[8],"PLAN_2026","capacity 0 = not published"])
        for c in CANDIDATES:
            w.writerow([c[0],c[1],"candidate_mch",c[2],c[3],c[4],MCH_CAP,9,19,"CONTEST",
                "8 candidate sites are CONTEST fictions; 250 visits/day per prompt"])
    sites=[(s[0],s[4],s[5]) for s in EXISTING_FIXED]+[(c[0],c[3],c[4]) for c in CANDIDATES]
    with (OUT/"access.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["district_id","site_id","km","walk_min","transit_min","drive_min","source"])
        for d in DISTRICTS:
            for sid,lat,lon in sites:
                km=round(hav(d[9],d[10],lat,lon)*DETOUR,2)
                w.writerow([d[0],sid,km,round(km/SPEED["walk"]*60,1),
                            round(km/SPEED["transit"]*60+TRANSIT_WAIT,1),
                            round(km/SPEED["drive"]*60,1),"ESTIMATE_LINEAR"])
    peak=max(sum(raw_demand(d,day) for d in DISTRICTS) for day in range(7))
    k=OBS["peak_week_visits_per_day"]/peak
    with (OUT/"demand.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["scenario","district_id","day","demand_visits","heat_exposure","vulnerability","note"])
        for name,mult in (("low",0.5),("base",1.0),("high",2.0)):
            for d in DISTRICTS:
                for day in range(7):
                    w.writerow([name,d[0],day,round(raw_demand(d,day)*k*mult,1),d[8],vuln(d[4],d[5],d[6]),
                                "calibrated to 2025 observed peak week; multiplier %s" % mult])
    json.dump(OBS, open(OUT/"calibration.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"OK: 12 区 / {len(EXISTING)+len(CANDIDATES)} 站点 / {len(DISTRICTS)*len(sites)} 链接 / 需求标定 k={k:.6f}")

if __name__ == "__main__":
    main()
