"""Adapters against fakes of the real thing: a NapCat-like OneBot server and WeChat's webhook."""

import asyncio
import hashlib
import json

import httpx
import websockets
from fastapi import FastAPI

from anima.adapters.onebot import OneBotAdapter
from anima.adapters.wechat import WeChatMPAdapter
from tests.conftest import wait_idle

SELF_ID = 10001


class FakeNapCat:
    def __init__(self) -> None:
        self.actions: list[tuple[str, dict]] = []
        self.ws = None
        self.connected = asyncio.Event()

    async def handler(self, ws) -> None:
        self.ws = ws
        self.connected.set()
        async for raw in ws:
            msg = json.loads(raw)
            action, params = msg["action"], msg.get("params", {})
            self.actions.append((action, params))
            data = {"user_id": SELF_ID, "nickname": "可乐"} if action == "get_login_info" else {"message_id": len(self.actions)}
            await ws.send(json.dumps({"status": "ok", "retcode": 0, "data": data, "echo": msg["echo"]}))

    async def push(self, event: dict) -> None:
        await self.ws.send(json.dumps({"self_id": SELF_ID, "time": 0, **event}))

    def sent(self, action: str) -> list[dict]:
        return [p for a, p in self.actions if a == action]


async def test_onebot_group_mention_poke_and_whitelist(make_brain):
    napcat = FakeNapCat()
    server = await websockets.serve(napcat.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    adapter = OneBotAdapter({"url": f"ws://127.0.0.1:{port}", "groups": [123], "token_env": "NO_TOKEN"})

    def responder(system, turns, dynamic):
        return "[poke]\n别戳啦" if "戳了戳你" in turns[-1].text else "在！[sticker:laugh]"

    brain, _ = make_brain(responder, adapter=adapter)
    await adapter.start(brain)
    try:
        await asyncio.wait_for(adapter.connected.wait(), 3)
        assert adapter.self_id == str(SELF_ID)

        await napcat.push({
            "post_type": "message", "message_type": "group", "group_id": 123, "user_id": 42, "message_id": 7,
            "sender": {"nickname": "小明", "card": "明明"},
            "message": [{"type": "at", "data": {"qq": str(SELF_ID)}}, {"type": "text", "data": {"text": " 在吗"}}],
        })
        await asyncio.sleep(0.2)
        await wait_idle(brain)
        sent = napcat.sent("send_group_msg")
        assert sent and sent[0]["group_id"] == 123
        assert sent[0]["message"] == [{"type": "text", "data": {"text": "在！"}}, {"type": "face", "data": {"id": "182"}}]
        history = await brain.memory.recent("qq:group:123")
        assert history[0].sender_name == "明明" and history[0].text.startswith("@可乐")

        await napcat.push({  # a group she isn't in: invisible
            "post_type": "message", "message_type": "group", "group_id": 999, "user_id": 42, "message_id": 8,
            "sender": {"nickname": "小明"}, "message": [{"type": "text", "data": {"text": "可乐可乐"}}],
        })
        await napcat.push({"post_type": "notice", "notice_type": "notify", "sub_type": "poke",
                           "group_id": 123, "user_id": 42, "target_id": SELF_ID})
        await asyncio.sleep(0.3)
        await wait_idle(brain)
        assert napcat.sent("group_poke") == [{"group_id": 123, "user_id": 42}]
        assert any(p["message"] == [{"type": "text", "data": {"text": "别戳啦"}}] for p in napcat.sent("send_group_msg"))
        assert await brain.memory.recent("qq:group:999") == []

        mine = [m for m in await brain.memory.recent("qq:group:123") if m.is_self]
        adapter._sent_ids.clear()  # as after a restart: memory still knows which messages were hers
        await napcat.push({
            "post_type": "message", "message_type": "group", "group_id": 123, "user_id": 43, "message_id": 9,
            "sender": {"nickname": "小红"},
            "message": [{"type": "reply", "data": {"id": mine[0].platform_msg_id}}, {"type": "text", "data": {"text": "哈哈真的吗"}}],
        })
        await asyncio.sleep(0.2)
        await wait_idle(brain)
        assert brain.llm.calls[-1]["turns"][-1].text.endswith("哈哈真的吗"), "a reply to her message, even from before a restart"
        await napcat.push({"post_type": "notice", "notice_type": "group_recall", "group_id": 123,
                           "user_id": 43, "operator_id": 43, "message_id": 9})
        await asyncio.sleep(0.2)
        recalled = [m for m in await brain.memory.recent("qq:group:123") if m.platform_msg_id == "9"]
        assert recalled[0].text == "（撤回了一条消息）"
    finally:
        await adapter.stop()
        server.close()


def _sign(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()


async def test_wechat_official_account_verify_and_reply(make_brain, monkeypatch):
    monkeypatch.setenv("WECHAT_MP_TOKEN", "testtoken")
    adapter = WeChatMPAdapter({"enabled": True})
    brain, _ = make_brain(lambda *a: "你好呀\n我是可乐[sticker:doge]", adapter=adapter, hour=3)
    await adapter.start(brain)
    app = FastAPI()
    app.include_router(adapter.router())
    ts, nonce = "1700000000", "abc"
    params = {"signature": _sign("testtoken", ts, nonce), "timestamp": ts, "nonce": nonce}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://wx") as client:
        verify = await client.get("/wechat/mp", params={**params, "echostr": "hello"})
        assert verify.text == "hello"
        bad = await client.get("/wechat/mp", params={**params, "signature": "nope", "echostr": "x"})
        assert bad.status_code == 403
        xml = ("<xml><ToUserName><![CDATA[gh_1]]></ToUserName><FromUserName><![CDATA[openid_1]]></FromUserName>"
               "<CreateTime>1700000000</CreateTime><MsgType><![CDATA[text]]></MsgType>"
               "<Content><![CDATA[你好]]></Content><MsgId>42</MsgId></xml>")
        resp = await client.post("/wechat/mp", params=params, content=xml)
    assert resp.status_code == 200
    assert "你好呀\n我是可乐[旺柴]" in resp.text, "answers even at 3 a.m., with WeChat's own emoji code"
