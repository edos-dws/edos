"""EventHub pub/sub (async, no pytest-asyncio needed — driven with asyncio.run)."""
import asyncio

from edos.pipeline.hub import EventHub


def test_subscribe_publish_receive_unsubscribe():
    async def go():
        h = EventHub()
        q = h.subscribe("p1")
        assert h.subscriber_count("p1") == 1

        delivered = await h.publish("p1", {"type": "decision.ready"})
        assert delivered == 1
        event = await asyncio.wait_for(q.get(), timeout=1.0)
        assert event == {"type": "decision.ready"}

        h.unsubscribe("p1", q)
        assert h.subscriber_count("p1") == 0
        assert await h.publish("p1", {"type": "x"}) == 0  # nobody listening

    asyncio.run(go())


def test_fan_out_to_multiple_subscribers():
    async def go():
        h = EventHub()
        a, b = h.subscribe("p2"), h.subscribe("p2")
        assert await h.publish("p2", {"n": 1}) == 2
        assert (await a.get())["n"] == 1
        assert (await b.get())["n"] == 1

    asyncio.run(go())
