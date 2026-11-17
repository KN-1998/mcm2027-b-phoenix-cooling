# data/incoming/ —— 真实资料放这里（留空待填）

把队友找到的文件按**固定文件名**放进本目录，程序会自动覆盖对应的合成值；
没有文件时一切照旧。每次运行会在 `run_meta.json` 或 `inst.meta["incoming"]` 里记录改了哪些字段。

| 文件名 | 覆盖什么 | 必需列 | 状态 |
|---|---|---|---|
| `sites_mag.csv` | 站点坐标/类型/开放时间/容量 | `site_id, lat, lon, kind, open_hour, close_hour, capacity` | ⬜ 待填（M1） |
| `acs_districts.csv` | 12 区人口学属性 | `district_id, population, pct_65plus, pct_no_vehicle, median_income_usd, canopy_pct, heat_exposure_index` | ⬜ 待填（M7） |
| `access_gtfs.csv` | 行程时间矩阵 | `district_id, site_id, walk_min, transit_min, drive_min` | ⬜ 待填（M8） |
| `demand_observed.csv` | 观测到的分区分日到访 | `district_id, day, demand_visits` | ⬜ 选填 |

## 注意

1. 列名**必须**与上表一致（大小写敏感）；多余的列会被忽略；
2. 站点用 `site_id` 匹配（如 `C01` / `MCH-3`）；新增站点请在 `sites_mag.csv` 里给新 id；
3. 填完后重跑：
   ```powershell
   python tools/build_data.py
   python -m pytest tests -q
   python -m src.exp.run_levers --p 3 --out results/levers
   ```
4. 填之前先看 `data/DATA_DICTIONARY.md` 的"预留字段"一节。
