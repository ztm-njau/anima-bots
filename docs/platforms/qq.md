# QQ (via NapCat)

NapCat runs Linux QQ inside Docker (Docker Desktop or OrbStack) and exposes it as a
OneBot v11 WebSocket on `127.0.0.1:3001`. Anima connects to it as a client. To run NoneBot, Koishi or
AstrBot on the same account, see the OneBot bridge in [plugins.md](../plugins.md).

1. **Prepare a QQ account for her.** A secondary account, not your main one: automated accounts
   can be restricted. Give it a nickname and avatar that say she's a virtual character.
2. **Start NapCat**
   ```bash
   uv run anima napcat init      # data folders, tokens in .env, OneBot config
   uv run anima napcat up        # prints the WebUI link
   ```
3. **Log in:** open the WebUI link and scan the QR code with her account in the QQ app
   (`uv run anima napcat qr` opens the code directly). The login survives restarts.
4. **Choose where she may talk** in `bots/claudette/bot.toml`:
   ```toml
   [platforms.qq]
   enabled = true
   groups = [123456789]          # she speaks only in these groups
   listen_groups = []            # she reads and remembers, never speaks
   ```
   Private chats always work. Friend requests are ignored unless `accept_friend_requests = true`.
5. **Tune each group** (optional) in the console, 设置 → 每个群单独调, or in bot.toml:
   ```toml
   [chats."qq:group:123456789"]
   mode = "quiet"                # only when spoken to; "lively" chimes in twice as often
   note = "天文社的群，大家都叫她乐乐"
   ```
6. **Run:** `uv run anima run` (or `uv run anima doctor` first).

What she does on QQ: answers @-mentions, replies, her name and pokes; keeps talking with whoever
she just answered; chimes in occasionally (at most a few times an hour per group) and sometimes
joins a 复读 chain; quotes the message she answers once the group has moved on; ignores recalled
messages; waits for you to finish typing and changes her mind if you add something;
pokes back; sends native QQ faces, quote replies and short voice notes; shows "对方正在输入…" in
private chats; reads Bilibili mini-program cards people share and can look the video up.

Maintenance: `uv run anima napcat logs`, `uv run anima napcat down`, and
`docker compose -f infra/napcat/compose.yaml pull` to update NapCat.
