"""Verified TypeSafe System One API; no Chat Completions emulation."""
import http.client
import json
import math
import re
import urllib.request

ENDPOINTS={'opencode':'https://opencode.ai/inference/systemone/v1/systemone',
           'typesafe':'https://api.typesafe.ai/v1/systemone'}
FIELDS={'risk','task_class','scope_count','acceptance_count','required_check_count','base_checks_passed'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class SystemOne:
    def __init__(self,*,provider,model,api_key,endpoint=None,timeout=30,allow_test_http=False):
        if provider not in ENDPOINTS:
            raise ValueError('Unknown Jev provider')
        endpoint=endpoint or ENDPOINTS[provider]
        if endpoint!=ENDPOINTS[provider]:
            if not (allow_test_http and api_key=='test-only' and re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}/v1/systemone',endpoint)):
                raise ValueError('Unapproved Jev endpoint')
        if not isinstance(model,str) or not model.strip() or len(model)>128:
            raise ValueError('Explicit Jev model required')
        if not isinstance(api_key,str) or not api_key.strip() or any(c in api_key for c in '\r\n'):
            raise ValueError('Jev API key is missing or invalid')
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120:
            raise ValueError('Timeout must be in (0,120]')
        self.endpoint,self.model,self._key,self.timeout=endpoint,model,api_key,timeout
        self.identity={'provider':provider,'model':model,'endpoint':endpoint}

    def __call__(self,request):
        summary=request.get('summary')
        if type(summary) is not dict or set(summary)!=FIELDS:
            raise ValueError('Only structural Jev summaries may leave the host')
        if summary['risk'] not in ('LOW','MEDIUM','HIGH','CRITICAL') or summary['task_class'] not in ('SPIKE','BOUNDED','ARCHITECTURAL'):
            raise ValueError('Invalid summary class/risk')
        if any(type(summary[k]) is not int or not 0<=summary[k]<=10000 for k in ('scope_count','acceptance_count','required_check_count')):
            raise ValueError('Invalid summary counts')
        if type(summary['base_checks_passed']) is not bool or request.get('phase') not in ('PREFLIGHT','COMPLETION'):
            raise ValueError('Invalid summary phase')
        payload={'model':self.model,'state':json.dumps({'phase':request['phase'],**summary}),
                 'questions':{'review':{'type':'noul','instructions':'Given the structural task metadata, is additional independent review advisable? Do not infer facts not present.'},
                              'missing':{'type':'noul','instructions':'Do the scope, acceptance and required check counts show missing requirements? Base checks must have passed for completion.'}}}
        req=urllib.request.Request(self.endpoint,data=json.dumps(payload).encode(),method='POST',
                                   headers={'Authorization':'Bearer '+self._key,'Content-Type':'application/json'})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        try:
            with opener.open(req,timeout=self.timeout) as response:
                if response.status!=200:raise ValueError('Bad response')
                body=response.read(65537)
                if len(body)>65536 or response.length not in (None,0):raise ValueError('Incomplete/oversized response')
            data=json.loads(body)
            if not isinstance(data,dict) or not isinstance(data.get('model'),str) or not data['model']:
                raise ValueError('Missing provider model')
            answers=data['answers']
            probabilities=[]
            for name in ('review','missing'):
                answer=answers[name]
                value=answer['noul']
                if answer['type']!='noul' or type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:
                    raise ValueError('Invalid typed probability')
                probabilities.append(value)
            gaps=[label for label,value in zip(('additional_review','missing_requirements'),probabilities) if value>=.5]
            if gaps:return {'verdict':'REVIEW_RECOMMENDED','gaps':gaps}
            if any(value>.2 for value in probabilities):return {'verdict':'INCOMPLETE','gaps':['uncertain_advice']}
            return {'verdict':'CLEAR','gaps':[]}
        except (OSError,http.client.HTTPException,ValueError,KeyError,TypeError,RecursionError):
            raise ValueError('Jev request/result unavailable or invalid') from None
