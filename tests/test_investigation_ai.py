import json
from io import BytesIO
from urllib.error import HTTPError
import pytest
from src.investigation.ai_assistant import payload,parse_response,ask,ENDPOINT

def sources():return [dict(title='온도 시험',source='TEST-001',excerpt='온도 센서를 대조했다.')]

def test_payload_minimizes_and_has_no_persistence():
    p=payload('온도 원인?',sources(),'model-test')
    assert p['store'] is False
    assert 'tools' not in p and 'previous_response_id' not in p
    assert json.loads(p['input'])['evidence'][0]['source']=='TEST-001'
    with pytest.raises(ValueError):payload('질문',[],'model-test')
    with pytest.raises(ValueError):payload('질문',sources(),'invalid model')

def test_output_requires_valid_source_numbers_and_completion():
    r={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'센서 대조를 확인 [1]'}]}]}
    assert '[1]' in parse_response(r,1)
    with pytest.raises(ValueError):parse_response(dict(r,status='incomplete'),1)
    r['output'][0]['content'][0]['text']='근거 [9]'
    with pytest.raises(ValueError):parse_response(r,1)

def test_request_transport_no_real_network():
    def transport(req,timeout):
        assert req.full_url==ENDPOINT and timeout==50
        assert req.get_header('Authorization')=='Bearer synthetic-test-key'
        assert json.loads(req.data)['store'] is False
        return BytesIO(json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'검토 초안 [1]'}]}]}).encode())
    assert ask('synthetic-test-key',payload('질문',sources(),'model-test'),1,transport)=='검토 초안 [1]'

def test_errors_do_not_echo_provider_body_or_key():
    def transport(req,timeout):raise HTTPError(ENDPOINT,401,'private error text',{},BytesIO(b'private content'))
    with pytest.raises(ValueError) as exc:ask('synthetic-test-key',payload('질문',sources(),'model-test'),1,transport)
    assert '401' in str(exc.value) and 'private' not in str(exc.value) and 'synthetic-test-key' not in str(exc.value)
