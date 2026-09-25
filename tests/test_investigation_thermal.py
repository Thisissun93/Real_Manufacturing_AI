from copy import deepcopy
import pytest
from src.investigation.thermal import high_bake_profile, analyze
from src.investigation.maintenance import status, recommendations


def test_baking_recipe_and_measured_lag():
    p=high_bake_profile(200,True)
    assert len(p['elapsed_s'])==7201
    assert p['zones'][0]['end_s']==5400 and p['zones'][1]['end_s']==7200
    assert p['zones'][0]['setpoint_c']==200 and p['zones'][1]['setpoint_c']==30
    assert p['temperature_c'][0]<200 and p['temperature_c'][5400]>30
    a=analyze(p)
    assert a['zones'][0]['저온 노출(초)']>0 and a['zones'][1]['고온 노출(초)']>0
    assert all(x['end_s']<=7200 for x in a['intervals'])


def test_reference_not_setpoint_and_missing_limits():
    p=high_bake_profile()
    assert not analyze(p)['intervals']
    p.pop('tolerance_c')
    assert analyze(p)['zones']==[] and '보류' in analyze(p)['note']


def test_interval_boundary_counts():
    p={'elapsed_s':[0,1,2,3], 'temperature_c':[94,100,106,110],'reference_c':[100]*4,'tolerance_c':4,
       'zones':[{'zone':1,'start_s':0,'end_s':2,'setpoint_c':100},{'zone':2,'start_s':2,'end_s':3,'setpoint_c':100}]}
    a=analyze(p)
    assert a['zones'][0]['저온 노출(초)']==1
    assert a['zones'][1]['고온 노출(초)']==1
    assert a['intervals']==[{'start_s':0,'end_s':1,'state':'저온','zone':1},{'start_s':2,'end_s':3,'state':'고온','zone':2}]


def test_life_requires_source_and_no_future_records():
    at='2026-01-01T00:00:00+09:00'
    assert status({'limit_hours':100,'used_hours':200},at)=='수명 기준 미등록'
    assert status({'source':'OEM-X','limit_hours':100,'used_hours':101},at)=='사용시간 초과'
    assert status({'source':'OEM-X','limit_hours':100,'used_hours':95,'warning_hours':10},at)=='사용시간 임박'
    assert status({'source':'OEM-X','due_at':at},at)=='기한 도달'
    rows=recommendations({'maintenance':[{'equipment':'CURE-1','component':'히터','available_at':'2026-01-02T00:00:00+09:00','source':'OEM','limit_hours':1,'used_hours':2}]},[{'step':'CURE','equipment':'CURE-1','end':at}])
    assert all(x['판정']=='수명 기준 미등록' for x in rows)
