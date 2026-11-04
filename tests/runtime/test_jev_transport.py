import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('harness.jev.transport'),'System One transport missing')
        from harness.jev.transport import SystemOne
        self.SystemOne=SystemOne
        self.reply={'model':'jev-test','answers':{'review':{'type':'noul','noul':.05},'missing':{'type':'noul','noul':.05}}}
        self.request=None
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                owner.request=(self.path,self.headers.get('Authorization'),json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                body=json.dumps(owner.reply).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.endpoint=f'http://127.0.0.1:{self.server.server_port}/v1/systemone'
        self.request_body={'phase':'PREFLIGHT','summary':{'risk':'LOW','task_class':'BOUNDED','scope_count':1,'acceptance_count':1,'required_check_count':1,'base_checks_passed':False},'evidence_digest':None}

    def client(self):
        return self.SystemOne(provider='typesafe',model='jev-test',api_key='test-only',endpoint=self.endpoint,allow_test_http=True)

    def test_real_systemone_request_and_advisory_mapping(self):
        result=self.client()(self.request_body)
        self.assertEqual(result,{'verdict':'CLEAR','gaps':[]})
        path,auth,body=self.request
        self.assertEqual(path,'/v1/systemone')
        self.assertEqual(auth,'Bearer test-only')
        self.assertEqual(body['model'],'jev-test')
        self.assertEqual(body['questions']['review']['type'],'noul')
        self.assertNotIn('messages',body)
        self.reply['answers']['review']['noul']=.9
        self.assertEqual(self.client()(self.request_body)['verdict'],'REVIEW_RECOMMENDED')

    def test_invalid_probabilities_or_missing_answers_rejected(self):
        for value in [True, -1, 2, float('nan'), '0.1', None]:
            self.reply['answers']['review']['noul']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.client()(self.request_body)
        self.reply['answers']={}
        with self.assertRaises(ValueError):self.client()(self.request_body)

    def test_ambiguous_probability_is_incomplete(self):
        self.reply['answers']['review']['noul']=.3
        self.assertEqual(self.client()(self.request_body)['verdict'],'INCOMPLETE')

    def test_credentials_not_sent_to_unapproved_endpoint(self):
        for endpoint in ['https://evil.example/v1/systemone',self.endpoint,'https://opencode.ai@evil.example/v1/systemone']:
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):
                self.SystemOne(provider='opencode',model='jev',api_key='real-key',endpoint=endpoint)
        with self.assertRaises(ValueError):
            self.SystemOne(provider='typesafe',model='jev',api_key='real-key',endpoint=self.endpoint,allow_test_http=True)
        self.assertIsNone(self.request)

    def test_summary_rejects_arbitrary_data_before_network(self):
        self.request_body['summary']['api_key']='secret'
        with self.assertRaises(ValueError):self.client()(self.request_body)
        self.assertIsNone(self.request)
