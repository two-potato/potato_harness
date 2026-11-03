"""Bounded, loopback-only Ollama proposal transport."""
import http.client
import json
import math
import re
import urllib.error
import urllib.request

from harness.demo.worker import validate_proposal

_MAX_RESPONSE = 65536
_ENDPOINT = re.compile(r'http://(?:localhost|127\.0\.0\.1|\[::1\])(?::([0-9]{1,5}))?\Z')
_SCHEMA = {'type': 'object', 'properties': {'operator': {'type': 'string',
           'enum': ['multiply', 'add']}}, 'required': ['operator'],
           'additionalProperties': False}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def propose(model: str, *, endpoint='http://127.0.0.1:11434', timeout=60) -> dict:
    """Ask an explicitly configured local model for one constrained operator."""
    match = _ENDPOINT.fullmatch(endpoint) if isinstance(endpoint, str) else None
    if not match or (match.group(1) and not 1 <= int(match.group(1)) <= 65535):
        raise ValueError('Endpoint must be an HTTP loopback origin')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('An installed model name is required')
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError('Timeout must be a positive finite number')
    payload = {'model': model, 'stream': False, 'format': _SCHEMA,
               'messages': [{'role': 'user', 'content':
                   'Choose the operator for subtotal(unit_cents, quantity). '
                   'Expected: subtotal(1250, 3)=3750; subtotal(1250, 0)=0; '
                   'subtotal(1250, 1)=1250. Return only JSON with exactly '
                   'one key operator, whose value is multiply or add.'}]}
    request = urllib.request.Request(endpoint + '/api/chat',
                                     data=json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'},
                                     method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError('Ollama request failed')
            body = response.read(_MAX_RESPONSE + 1)
            if response.length not in (None, 0):
                raise ValueError('Ollama response is incomplete')
        if len(body) > _MAX_RESPONSE:
            raise ValueError('Ollama response exceeds size limit')
        result = json.loads(body)
        if not isinstance(result, dict) or result.get('done') is not True:
            raise ValueError('Ollama response is incomplete')
        message = result.get('message')
        if (not isinstance(message, dict) or message.get('role') != 'assistant'
                or not isinstance(message.get('content'), str)):
            raise ValueError('Ollama assistant message is invalid')
        proposal = json.loads(message['content'])
        validate_proposal(proposal)
        return proposal
    except (OSError, http.client.HTTPException, urllib.error.URLError,
            ValueError, TypeError, RecursionError):
        raise ValueError('Ollama request or response is invalid') from None
