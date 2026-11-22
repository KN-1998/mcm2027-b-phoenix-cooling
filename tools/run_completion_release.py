"""Freeze-aware full completion run: model outputs and integrity checks."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.mch import runmeta
from tools.build_completion_report import build

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='tmp/reproduce_completion')
    p.add_argument('--pdf-python',default=sys.executable)
    args=p.parse_args();out=ROOT/args.out
    if out.exists() and any(out.iterdir()):
        raise RuntimeError('Refusing to overwrite an existing release. Choose a new empty --out directory.')
    out.mkdir(parents=True,exist_ok=True)
    if runmeta.meta({})['worktree_dirty']:raise RuntimeError('Commit source, tests, tools and inputs before release')
    code_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    jobs=[('base',[sys.executable,'tools/run_takeover_release.py','--out',str(out/'base'),'--pdf-python',args.pdf_python]),
          ('empirical',[sys.executable,'-m','src.exp.run_empirical_validation','--out',str(out/'empirical')]),
          ('gtfs_registered',[sys.executable,'-m','src.exp.run_gtfs_validation','--out',str(out/'gtfs_registered')]),
          ('gtfs_city',[sys.executable,'-m','src.exp.run_gtfs_validation','--city-operations','--out',str(out/'gtfs_city')]),
          ('operations',[sys.executable,'-m','src.exp.run_completion_evidence','--out',str(out/'operations')]),
          ('city_pipeline',[sys.executable,'-m','src.exp.run_pipeline','--p','3','--real-network','--city-operations',
                            '--access-mode','transit_min','--out',str(out/'city_pipeline')]),
          ('reference_gtfs_pipeline',[sys.executable,'-m','src.exp.run_pipeline','--p','3','--real-network','--city-operations',
              '--access-mode','transit_min','--gtfs-reference-od',str(out/'gtfs_city/od_by_departure.csv'),
              '--reference-departure','09:00:00','--out',str(out/'reference_gtfs_pipeline')])]
    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'};records=[]
    for name,command in jobs:
        print('RUN '+name,flush=True);start=datetime.datetime.now(datetime.timezone.utc).isoformat()
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        (out/(name+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8',newline='\n')
        records.append({'name':name,'command':command,'started_utc':start,'exit_code':result.returncode})
        if result.returncode:raise RuntimeError(name+' failed, see log')
        print('PASS '+name,flush=True)
    build(out)
    metas=[]
    for f in out.rglob('run_meta.json'):
        d=json.loads(f.read_text(encoding='utf-8'))
        if d['git_sha']!=code_sha or d['worktree_dirty']:raise RuntimeError('nonfrozen numeric experiment: '+str(f))
        for rel,sha in {**d['source_sha256'],**d['inputs']}.items():
            if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=sha:raise RuntimeError('changed dependency '+rel)
        metas.append(f.relative_to(out).as_posix())
    payload={'source_commit':code_sha,'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'runs':records,'numeric_metadata_files':metas,'runtime_source_and_inputs':runmeta.meta(vars(args)),
        'scope':'Completed reproducible modeling and bounded empirical/schedule checks; not human sign-off or field deployment validation',
        'sha256':{f.relative_to(out).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
                  for f in sorted(out.rglob('*')) if f.is_file() and f.name!='completion_manifest.json'}}
    (out/'completion_manifest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    print('FROZEN_COMPLETION '+code_sha,flush=True)

if __name__=='__main__':main()
