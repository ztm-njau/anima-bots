# Douyin (experimental)

Douyin has no public API for personal accounts, so she joins live rooms the way a viewer does:
through a real Chrome window with its own profile, reading new chat lines as they appear and
typing into the room's input box.

1. **Log in once:**
   ```bash
   uv run anima login douyin     # scan the QR code in the Chrome window that opens
   ```
   The session lives in `data/claudette/browser/douyin`.
2. **Enable:**
   ```toml
   [platforms.douyin]
   enabled = true
   live_rooms = ["123456789"]    # the number in live.douyin.com/<id>
   nickname = "可乐"              # her Douyin nickname, so she ignores her own lines
   ```
3. `uv run anima run`

Douyin's page markup changes often. If she stops seeing messages, open the room in Chrome,
inspect a chat line, and override the selectors:

```toml
[platforms.douyin.selectors]
item = "[class*='webcast-chatroom___item']"
name = "[class*='nickname']"
content = "[class*='content-with-emoji-text']"
input = "textarea"
```
