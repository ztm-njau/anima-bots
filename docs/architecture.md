# How the brain works

```
adapter ──Incoming──▶ Brain.handle
                        │ record message, update person
                        ▼
                 debounce per chat (2.5 s DM / 4 s group, max 12 s)
                        ▼
                 Policy.decide ── ignore (stay quiet, still remembers)
                        │       └ defer  (asleep: answered by wake_up())
                        ▼ reply
                 notice delay (by availability) → mark read → reading delay
                        ▼
                 compose: history + scene → LLM (tool loop) → markup → humanizer → guard
                        ▼
                 deliver: per-bubble typing delay → adapter.send → record her line
                        ▼
                 every ~16 messages: reflection (facts, affinity, nicknames, birthdays, treasures)
```

`Life` runs beside it every 30 s: morning plan, nightly diary, reminders, greetings, birthdays,
breaking long silences, and waking up (which answers what piled up overnight).

## Prompt layout (and why)

| Part | Where | Changes |
| --- | --- | --- |
| Persona, examples, message format, output protocol, tool notes | top-level `system`, cached | never during a run |
| Conversation history (her lines as `assistant`, others as `user`, `名字: …` in groups) | `messages`, cache breakpoint on the last turn | append-only |
| The scene: time, activity, mood, today's plan, the people (facts, closeness), her own past claims, why she's speaking, game state, warnings | trailing mid-conversation `system` message | every turn |

The volatile scene rides after the cached prefix, so it never invalidates it. Claude requests use
`output_config.effort` (no sampling parameters), adaptive thinking (the model default), the
server-side refusal fallback (`fallbacks: "default"`), and the web search server tool.

## Output protocol

One line per chat bubble. Inline tags: `[sticker:key]`, `[poke]`, `[reply]`,
`[voice]…[/voice]`, `[mood:label]` (not sent), `[silent]` (say nothing). `markup.py` parses them,
flattens any markdown, and the humanizer splits run-ons and drops the final full stops people
don't type.

## Memory (`data/<bot>/memory.db`)

`users` (platform:uid, name, nickname, affinity, birthday), `messages`, `facts` (subject is a
user key, `self`, or a chat key), `chats`, `reminders`, `journal` (plan / diary per date),
`treasures`, `state` (mood, game state, per-platform cursors).

## Extending

- **A skill:** a decorated async function, see `src/anima/skills/fun.py`. Drop bot-specific ones
  into `bots/<name>/skills/*.py`.
- **A platform:** subclass `Adapter` (`send` is the only required method), translate events into
  `Incoming`, register it in `Runtime.build_adapters`.
- **A bot:** `uv run anima new <name>`.

Tests use `FakeLLM` and a recorder adapter, with human pacing switched off: `uv run pytest`.
