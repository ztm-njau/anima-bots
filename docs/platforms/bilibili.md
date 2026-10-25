# Bilibili

Uses [bilibili-api-python](https://github.com/Nemo2011/bilibili-api) with the cookies of a
logged-in web session.

1. **Log in** with a dedicated account:
   ```bash
   uv run anima login bilibili   # scan the terminal QR code with the Bilibili app
   ```
   Cookies are saved to `data/claudette/secrets/bilibili.json` (gitignored, mode 600) and
   refreshed automatically.
2. **Enable** in `bots/claudette/bot.toml`:
   ```toml
   [platforms.bilibili]
   enabled = true
   private_messages = true       # 私信
   replies_and_mentions = true   # replies to her comments and @-mentions
   live_rooms = [1234567]        # rooms where she hangs out as a viewer
   post_diary = false            # publish her nightly diary as a 动态
   ```
3. `uv run anima run`

Notes: notifications are polled every ~25 s with jitter (Bilibili's web has no push channel).
On first start she skips the backlog of old notifications. Danmaku are cut to 20 characters and
spaced at least 5 s apart. She uses Bilibili emotes like `[doge]` and `[笑哭]`.
