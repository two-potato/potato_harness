"""Host compiler: role/rules from repository, opaque data from callers."""
import hashlib
import json
import re
from harness.controller import ROOT, ControllerError, _json


def _digest(text):return 'sha256:'+hashlib.sha256(text.encode()).hexdigest()


def _redact(text):
    text=re.sub(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----','[REDACTED PRIVATE KEY]',text,flags=re.S)
    text=re.sub(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b','[REDACTED]',text)
    text=re.sub(r'(?i)\b(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[\"\']?[^\s\"\',;]+',r'\1=[REDACTED]',text)
    text=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9_]{10,})\b','[REDACTED]',text)
    text=re.sub(r'(?i)Bearer\s+[^\s\"\']+','Bearer [REDACTED]',text)
    return text


DOMAIN_PROFILES = {"marketplace": "profiles/marketplace.md"}


def compile_context(task,recipient,segments,limit,token_count,*,domain_profile=None):
    """recipient={role,session_id}; host callable counts the FINAL encoded text.

    Caller segments are always inert JSON data, even if claiming trusted status.
    Only repository role and fixed rules can supply instruction segments.
    """
    if type(limit) is not int or limit<1 or not callable(token_count):raise ControllerError('Token limit and host counter required')
    role=recipient.get('role');session=recipient.get('session_id')
    allowed={'architect','backend','frontend','search','ml-recommendations','qa','devops-sre','security','valera-ceo'}
    if role not in allowed or not isinstance(session,str) or not session:raise ControllerError('Unauthorized recipient role/session')
    owner=task.get('owner')
    if role!=owner and role not in ('qa','security','valera-ceo'):raise ControllerError('Role is not task owner or reviewer')
    role_text=(ROOT/'agents'/f'{role}.md').read_text()
    sources=['AGENTS.md','rules/PRIORITY.md','rules/SECURITY.md','rules/REPORTING.md','docs/harness/v3/CONTROL_FLOW.md']
    skill={'valera-ceo':'harness-delegate','architect':'harness-contract-design','qa':'harness-verify','security':'harness-security-review','devops-sre':'harness-recover'}.get(role,'harness-implement')
    sources.append('skills/'+skill+'/SKILL.md')
    if domain_profile is not None:
        if not isinstance(domain_profile, str) or domain_profile not in DOMAIN_PROFILES:
            raise ControllerError('Unknown domain profile')
        sources.append(DOMAIN_PROFILES[domain_profile])
    rules='\n'.join((ROOT/path).read_text() for path in sources)
    base=[{'name':'role','text':role_text,'trust':'trusted','mandatory':True},{'name':'policy','text':rules,'trust':'trusted','mandatory':True}]
    mandatory=[];optional=[]
    for segment in segments:
        if not isinstance(segment.get('name'),str) or not isinstance(segment.get('text'),str) or type(segment.get('mandatory')) is not bool or segment.get('trust') not in ('trusted','untrusted'):raise ControllerError('Invalid context segment')
        item={'name':segment['name'],'untrusted_data':_redact(segment['text']),'trust':'untrusted','mandatory':segment['mandatory']}
        (mandatory if item['mandatory'] else optional).append(item)
    # JSON encoding prevents caller text from closing any instruction delimiter.
    def render(items):return _json({'instructions':base,'data':items})
    def count(text):
        value=token_count(text)
        if type(value) is not int or value<0:raise ControllerError('Host counter returned invalid count')
        return value
    selected=list(mandatory);mandatory_tokens=count(render(selected))
    if mandatory_tokens>limit:raise ControllerError('Mandatory context exceeds limit')
    for item in optional:
        if count(render(selected+[item]))<=limit:selected.append(item)
    text=render(selected);total=count(text)
    return {'schema_version':'3.0.1','task_id':task['task_id'],'task_revision':task['revision'],'source_commit':task['base_commit'],'recipient_session':session,'compiler_version':'durable-core-1','role_prompt_hash':_digest(role_text),'policy_digest':_digest(rules),'content_hash':_digest(text),'max_tokens':limit,'mandatory_tokens':mandatory_tokens,'optional_tokens':max(0,total-mandatory_tokens),'token_count':total,'text':text,'segments':[{'kind':'role' if item['name']=='role' else 'policy' if item['name']=='policy' else 'diagnostic','source':item['name'],'digest':_digest(item.get('text',item.get('untrusted_data',''))),'trust':item['trust'],'mandatory':item['mandatory']} for item in base+selected]}
