# How the brain works

```
adapter ──Incoming──▶ Brain.handle
                        │ record message, update person   (撤回 → Brain.retract forgets it)
                        ▼
                 debounce per chat (core/debounce.py): 2.5 s DM / 4 s group, longer when a line
                 trails off, shorter after a question, following the sender's rhythm, max 12 s;
                 in groups only people talking to her extend the wait
                        ▼
                 Policy.decide ── ignore (stay quiet, still remembers)
                        │       ├ defer  (asleep: answered by wake_up())
                        │       └ echo   (join a 复读 chain, no model call)
                        ▼ reply, with a target: the message she mainly answers
                 notice delay (by availability) → mark read → reading delay
                        ▼
                 compose: history + scene → LLM (tool loop) → markup → humanizer → guard
                        │  new words from them while she typed → compose again (twice at most)
                        ▼
                 deliver: think, then per-bubble typing (fits reply_budget) → adapter.send
                        │  interrupted mid-reply → stop; the unsent rest becomes a note next turn
                        ▼
                 every ~16 messages: reflection (facts, affinity, nicknames, birthdays, treasures)
```

### Group judgement (core/policy.py)

- Always answers an @, a reply to her, a poke, or her name used as a call ("可乐你…", "问问可乐").
  Words like 喝可乐 or 可乐鸡翅 are `name_false_friends`, not calls; her name mentioned in passing
  only makes her likelier to look.
- Keeps talking with whoever she just answered (`follow_up_seconds`) unless they @ or reply to
  someone else, and answers people who answer her question.
- Otherwise chimes in by chance: interests raise it; cooldown, talking a lot, a fast-moving group,
  people talking to each other and `interjections_per_hour` lower it.
- When the group has moved on she quotes the message she answers (`auto_quote`).
- `[chats."<key>"]` in bot.toml (or the console) tunes one chat: mode quiet / lively, chattiness,
  wait, bubbles, 复读, and a note she reads every turn.

### Bubbles (core/segment.py)

Lines longer than `bubble_split` are cut at sentence ends (a question ends its bubble), very long
sentences at commas; links, numbers, quotes, brackets and kaomoji are never cut, and a run with
nowhere safe to cut stays whole. Groups get at most `group_max_bubbles`.
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
adapter ──Incoming──▶ Brain.handle
                        │ record message, update person   (撤回 → Brain.retract forgets it)
                        ▼
                 debounce per chat (core/debounce.py): 2.5 s DM / 4 s group, longer when a line
                 trails off, shorter after a question, following the sender's rhythm, max 12 s;
                 in groups only people talking to her extend the wait
                        ▼
                 Policy.decide ── ignore (stay quiet, still remembers)
                        │       ├ defer  (asleep: answered by wake_up())
                        │       └ echo   (join a 复读 chain, no model call)
                        ▼ reply, with a target: the message she mainly answers
                 notice delay (by availability) → mark read → reading delay
                        ▼
                 compose: history + scene → LLM (tool loop) → markup → humanizer → guard
                        │  new words from them while she typed → compose again (twice at most)
                        ▼
                 deliver: think, then per-bubble typing (fits reply_budget) → adapter.send
                        │  interrupted mid-reply → stop; the unsent rest becomes a note next turn
                        ▼
                 every ~16 messages: reflection (facts, affinity, nicknames, birthdays, treasures)
```

### Group judgement (core/policy.py)

- Always answers an @, a reply to her, a poke, or her name used as a call ("可乐你…", "问问可乐").
  Words like 喝可乐 or 可乐鸡翅 are `name_false_friends`, not calls; her name mentioned in passing
  only makes her likelier to look.
- Keeps talking with whoever she just answered (`follow_up_seconds`) unless they @ or reply to
  someone else, and answers people who answer her question.
- Otherwise chimes in by chance: interests raise it; cooldown, talking a lot, a fast-moving group,
  people talking to each other and `interjections_per_hour` lower it.
- When the group has moved on she quotes the message she answers (`auto_quote`).
- `[chats."<key>"]` in bot.toml (or the console) tunes one chat: mode quiet / lively, chattiness,
  wait, bubbles, 复读, and a note she reads every turn.

### Bubbles (core/segment.py)

Lines longer than `bubble_split` are cut at sentence ends (a question ends its bubble), very long
sentences at commas; links, numbers, quotes, brackets and kaomoji are never cut, and a run with
nowhere safe to cut stays whole. Groups get at most `group_max_bubbles`.

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
