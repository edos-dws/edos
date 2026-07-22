# EDOS WebSocket — client examples

Base host below is `localhost:8000`; over the tailnet use the Tailscale IP (e.g. `100.100.159.28:8000`).
Postman supports WebSocket via **New → WebSocket Request** (WS requests aren't stored in the shared REST
collection); the snippets below work from a terminal, a browser, or a Node/Python frontend.

## Quick test with `wscat`
```bash
npm i -g wscat

# 1) stream an analysis
wscat -c ws://localhost:8000/v1/ws/analyze
> {"project_id":"p1","question":"pick an MCU","context_items":[{"type":"requirement","ref_id":"R1","content":"LoRaWAN reporting","signals":{"graph":0.9,"semantic":0.9,"recency":0.9,"confidence":0.9,"focus":0.9}}]}
# ← stage / decision / done messages stream back

# 2) subscribe to a project's live event stream
wscat -c ws://localhost:8000/v1/ws/projects/p1/events
# ← {"type":"connected",...} then events as they happen
```
Trigger an event onto the stream from another terminal:
```bash
curl -X POST localhost:8000/v1/projects/p1/events -H "Content-Type: application/json" \
  -d '{"type":"alert","message":"check duty cycle"}'
```

## Browser / frontend (JavaScript)
```js
// stream an analysis
const ws = new WebSocket("ws://localhost:8000/v1/ws/analyze");
ws.onopen = () => ws.send(JSON.stringify({
  project_id: "p1", question: "pick an MCU",
  context_items: [{ type: "requirement", ref_id: "R1", content: "LoRaWAN reporting",
    signals: { graph: .9, semantic: .9, recency: .9, confidence: .9, focus: .9 } }],
}));
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "stage")    showProgress(msg.stage);
  if (msg.type === "decision") renderDecision(msg.decision);
  if (msg.type === "done")     ws.close();
};

// live project event stream (keep open for the session)
const events = new WebSocket("ws://localhost:8000/v1/ws/projects/p1/events");
events.onmessage = (e) => handleProjectEvent(JSON.parse(e.data));
```

## Python client
```python
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://localhost:8000/v1/ws/analyze") as ws:
        await ws.send(json.dumps({"project_id": "p1", "question": "pick an MCU",
            "context_items": [{"type": "requirement", "ref_id": "R1", "content": "LoRaWAN reporting",
                "signals": {"graph": .9, "semantic": .9, "recency": .9, "confidence": .9, "focus": .9}}]}))
        async for raw in ws:
            msg = json.loads(raw)
            print(msg["type"], msg.get("stage") or "")
            if msg["type"] == "done":
                break

asyncio.run(main())
```
