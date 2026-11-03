# Optional local Ollama proposal

The standard-library adapter sends only a synthetic subtotal problem and an explicit
model name to a local Ollama server. It returns `{"operator":"multiply"}` or
`{"operator":"add"}`; the existing worker validator enforces that exact vocabulary.
The proposal still needs the controller's normal authorization and verification.
Model output cannot supply source code, paths, commands, or a completion decision.

Start Ollama separately and choose an already installed model (`ollama list`). Then,
from the repository root, substitute its exact installed name:

```bash
python -c 'from harness.adapters.ollama import propose; print(propose("YOUR_INSTALLED_MODEL"))'
```

There is no default model, automatic model pull, installation, or server startup.
The default endpoint is `http://127.0.0.1:11434`; `endpoint` may specify only an HTTP
origin with literal `localhost`, `127.0.0.1`, or `[::1]`, and an optional valid port.
Credentials, paths (including a trailing slash), query strings and fragments are
rejected. Environment proxies and HTTP redirects are disabled. One POST is made
without retries, with a 60-second default socket timeout and a 64 KiB response cap.
The socket timeout is not a total wall-clock deadline against a trickling server.
The adapter does not read user files or credentials. Error messages omit model
response bodies. A local server and its selected model must still be trusted;
loopback restrictions are not a container or process isolation boundary.

The request uses `/api/chat`, `stream: false`, and a JSON schema in `format` with
one required `operator` enum and `additionalProperties: false`. A complete reply
must have `done: true`, an assistant message, and valid proposal JSON in
`message.content`. See the [official Ollama chat API](https://docs.ollama.com/api/chat).

Validation in this environment is **protocol-tested only** using a real local HTTP
fixture; no live Ollama model was available or invoked. Run the protocol tests with:

```bash
python -m unittest discover -s tests/runtime -p test_ollama.py
```

Live model compatibility, inference quality and latency remain unverified. A valid
`add` answer is intentionally accepted as a proposal; downstream candidate tests
must reject its incorrect subtotal behavior.
