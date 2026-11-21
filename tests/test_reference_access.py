import csv
import pytest
from src.mch.reference_access import apply_reference_gtfs_access
from src.mch.schema import District,Site,Instance

def instance():
    return Instance([District('D','D',10,0,0,1,0,0)],[Site('S','S','cooling','D',0,0,50,9,17)],
                    {('D','S'):100},{('D',0):10},1,{'calendar_start_date':'2026-07-20','access_mode':'transit_min'})

def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['district_id','site_id','service_date','departure','duration_minutes']);w.writerows(rows)

def test_reference_access_is_explicit_date_matched_and_nonmutating(tmp_path):
    path=tmp_path/'od.csv';write(path,[['D','S','2026-07-20','09:00:00',27]])
    original=instance();revised=apply_reference_gtfs_access(original,path)
    assert original.access['D','S']==100 and revised.access['D','S']==27
    assert revised.meta['access_mode']=='gtfs_reference_one_departure'
    assert 'not a time-dependent' in revised.meta['reference_access']['scope']

@pytest.mark.parametrize('rows',[
    [['D','S','2026-07-21','09:00:00',27]],
    [['D','WRONG','2026-07-20','09:00:00',27]],
    [['D','S','2026-07-20','09:00:00',27],['D','S','2026-07-20','09:00:00',28]]])
def test_bad_reference_table_is_not_silently_accepted(tmp_path,rows):
    path=tmp_path/'od.csv';write(path,rows)
    with pytest.raises(ValueError):apply_reference_gtfs_access(instance(),path)
