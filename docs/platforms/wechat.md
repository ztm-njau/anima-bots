# WeChat

Two routes; pick by what you have.

## A. Official account (公众号), the compliant route

1. In the account's admin console (开发 → 基本配置), set a server URL, a Token, and (optionally)
   an EncodingAESKey. Put them in `.env`:
   ```
   WECHAT_MP_TOKEN=...
   WECHAT_MP_APP_ID=...
   WECHAT_MP_AES_KEY=...        # only for 安全模式
   WECHAT_MP_APP_SECRET=...     # optional, verified accounts: enables late replies
   ```
2. WeChat needs a public HTTPS URL. A tunnel is simplest:
   ```bash
   brew install cloudflared
   cloudflared tunnel --url http://127.0.0.1:8765
   ```
   Use `https://<tunnel-host>/wechat/mp` as the server URL.
3. `[platforms.wechat] enabled = true`, then `uv run anima run`.

WeChat wants an answer within 5 s and retries a message up to three times. She uses the retries
as thinking time and answers on a later attempt (about 14 s in total). If that's still too slow
and the account has an AppSecret, the reply goes out through the customer-service message API.
Official accounts answer at any hour; her sleep schedule doesn't apply here.

## B. A personal WeChat account through a OneBot v11 bridge

Any bridge that exposes WeChat as OneBot v11 over a WebSocket plugs into the same adapter as QQ:

```toml
[platforms.wechat]
enabled = true
mode = "onebot_bridge"
url = "ws://127.0.0.1:3002"
token_env = "WECHAT_ONEBOT_TOKEN"
groups = ["xxxx@chatroom"]
```

Automating a personal WeChat account breaks WeChat's terms and risks a ban; use a spare account.
