"""Read-only diagnostics for c506b539fa61. Models are patched in memory only.

python 复现_Q3_Q4_边界检查.py --repo PATH_TO_REPOSITORY --out PATH_TO_EVIDENCE
Requires the repository's ordinary scipy dependencies. No source files are modified.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys
from unittest.mock import patch

ap=argparse.ArgumentParser()
ap.add_argument('--repo',type=Path,default=Path.cwd())
ap.add_argument('--out',type=Path,required=True)
args=ap.parse_args()
repo=args.repo.resolve(); dest=args.out.resolve()
dest.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo))
from src.mch.schema import District,Site,Instance
from src.mch.disruption import plan_response
from src.mch.dynamic import solve_week_dp,plan_moves
from src.mch.loaders import load_instance
from src.mch.static import solve_static,_active_sites,_assign

def district(s,income):return District(s,s,1000,.1,.1,income,.1,.5)
def candidate(s,d,cap=100,op=9,cl=22):return Site(s,s,'candidate_mch',d,0,0,cap,op,cl)
out={'reviewed_revision':'c506b539fa61ac57b04fb822c8557e1cf3b003de'}
ds=[district('D1',100000),district('D2',10000),district('D3',20000)]
ss=[candidate('A','D1'),candidate('B','D2')]
inst=Instance(ds,ss,{('D1','A'):1,('D2','B'):1},{('D1',0):100.,('D2',0):99.,('D3',0):0.},1)
with patch('src.mch.dynamic.move_time_hours',return_value=1.5):
    out['net_response_negative']=plan_response(inst,1,mult=1.1)
    out['undeployed_vehicle_minimal']=plan_response(inst,1,mult=1.,down_vehicle='B')

ds2=[district('D1',100000),district('D2',10000)]
ss2=[candidate('A','D1',1000,0,24),candidate('B','D2',1000,0,24)]
dem={('D1',0):200.,('D2',0):0.,('D1',1):0.,('D2',1):100.,('D1',2):0.,('D2',2):200.}
inst2=Instance(ds2,ss2,{('D1','A'):1,('D2','B'):1},dem,3)
with patch('src.mch.dynamic.move_time_hours',return_value=48.):
    out['multiday_trip']=solve_week_dp(inst2,1,top_k=2)

real=load_instance()
out['undeployed_MCH1']=plan_response(real,3,mult=1.,down_vehicle='MCH-1')
out['deployed_MCH3']=plan_response(real,3,mult=1.,down_vehicle='MCH-3')
base=solve_static(real,3)
healthy=[sid for sid in base.chosen if sid!='MCH-3']
target=solve_static(real,2)
moves=plan_moves(real,healthy,target.chosen)
t=0.; down={}
for m in moves:
    t+=m['hours']; down[m['to']]=max(0.,1.-min(10.,t)/10.)
sol=_assign(real,_active_sites(real,target.chosen),0,30.,250.,downtime=down)
out['healthy_fleet_original_pad_available']={
    'healthy_origins':healthy,'target':target.chosen,'moves':moves,'response_hours':t,
    'no_response_unmet':out['deployed_MCH3']['no_response']['unmet'],
    'with_response_unmet':sol.metrics['unmet_total'],
    'gain':round(out['deployed_MCH3']['no_response']['unmet']-sol.metrics['unmet_total'],3)}

cliout=dest/'q4_budget_01'
cmd=[sys.executable,'-m','src.exp.run_q4_response','--p','3','--mults','1.0',
     '--down-sites','MCH-3','--down-vehicles=','--budget-hours','0.1','--stress-draws','1',
     '--out',str(cliout)]
r=subprocess.run(cmd,cwd=repo,capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
stderr=r.stderr.decode('utf-8',errors='replace').replace(str(repo),'<REPOSITORY>').replace(str(dest),'<EVIDENCE>')
out['infeasible_cli']={'returncode':r.returncode,'stderr':stderr,
    'files_written':sorted(p.name for p in cliout.glob('*') if p.is_file())}
out['observed_issue_checks']={
    'net_response_can_be_negative':out['net_response_negative']['response_gain']<0,
    'undeployed_vehicle_wrongly_reduces_fleet':out['undeployed_MCH1']['fleet_healthy']==2 and len(out['undeployed_MCH1']['no_response']['chosen'])==3,
    'healthy_vehicles_can_regain_service_at_unfailed_original_pad':out['healthy_fleet_original_pad_available']['gain']>0,
    'multiday_trip_serves_before_arrival':out['multiday_trip']['schedule'][2]['unmet']==0,
    'infeasible_cli_fails_formatting_none':r.returncode!=0 and 'NoneType.__format__' in stderr}
out['observed_issue_checks']={k:bool(v) for k,v in out['observed_issue_checks'].items()}
assert all(out['observed_issue_checks'].values()),out['observed_issue_checks']
(dest/'dynamic_reproduction.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out['observed_issue_checks'],ensure_ascii=True,indent=2))
