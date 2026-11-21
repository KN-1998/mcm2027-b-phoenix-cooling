"""Fetch bounded primary cost/context and address geocoding evidence."""
from pathlib import Path
import json,hashlib,datetime
from concurrent.futures import ThreadPoolExecutor
import requests
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'资料'/'12_实证补全_2026-11-21'/'operations_costs'
SOURCES={
 'arizona_2026_wage_release.pdf':'https://www.azica.gov/sites/default/files/2025-10/2026%20Minimum%20Wage.pdf',
 'phoenix_2026_heat_contract_request.html':'https://phoenix.legistar.com/LegislationDetail.aspx?GUID=8DA9469F-1B49-4E07-8CF2-1ED4B4F37AA0&ID=7923913',
 'phoenix_2026_plan_announcement.html':'https://www.phoenix.gov/newsroom/heat-news/city-of-phoenix-unveils-robust-2026-heat-response-plan.html',
 'jackson_census_geocode.json':'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=20%20W%20Jackson%20St%20Phoenix%20AZ&benchmark=Public_AR_Current&format=json',
 'justa_census_geocode.json':'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=1001%20W%20Jefferson%20St%20Phoenix%20AZ&benchmark=Public_AR_Current&format=json',
}
def fetch(item):
    name,url=item
    record={'file':name,'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        response=requests.get(url,timeout=50,headers={'User-Agent':'Phoenix-Cooling-Model-Primary-Source-Research/1.0'})
        record['http_status']=response.status_code
        response.raise_for_status();data=response.content
        if name.endswith('.pdf') and not data.startswith(b'%PDF'):raise ValueError('not a PDF')
        if name.endswith('.json'):response.json()
        (OUT/name).write_bytes(data)
        record.update(saved=True,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),content_type=response.headers.get('Content-Type'))
    except Exception as exc:record.update(saved=False,error=str(exc))
    return record
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(fetch,SOURCES.items()))
    (OUT/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved primary-source records:',len(records))
if __name__=='__main__':main()
