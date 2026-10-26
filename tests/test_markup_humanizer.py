import random

from anima.config import BehaviorConfig
from anima.core.events import Bubble, Segment
from anima.core.humanizer import Humanizer
from anima.core.markup import parse_reply
from anima.core.stickers import StickerBook

BOOK = StickerBook({"laugh": {"desc": "笑哭", "unicode": "😂", "qq": 182, "bilibili": "[笑哭]"},
                    "doge": {"desc": "狗头", "unicode": "🐶", "qq": 179}})


def test_lines_become_bubbles_with_inline_stickers():
    reply = parse_reply("笑死我了[sticker:laugh]\n你这也太离谱了吧\n[sticker:doge]", BOOK)
    assert [b.source for b in reply.bubbles] == ["笑死我了[sticker:laugh]", "你这也太离谱了吧", "[sticker:doge]"]
    assert reply.bubbles[0].segments == [Segment("text", "笑死我了"), Segment("sticker", "laugh")]
    assert reply.bubbles[2].is_sticker_only


def test_markdown_and_speaker_prefix_are_flattened():
    reply = parse_reply("可乐：**好耶**\n- 第一点\n# 标题\n`代码`", BOOK)
    assert [b.text for b in reply.bubbles] == ["好耶", "第一点", "标题", "代码"]


def test_flags_moods_voice_and_silence():
    reply = parse_reply("[poke]\n戳回去！[mood:happy]\n[voice]晚安呀[/voice]\n[reply]", BOOK)
    assert reply.poke == "*" and reply.quote == "*"
    assert reply.moods == ["happy"]
    assert reply.bubbles[-1].voice == "晚安呀"
    assert parse_reply("[silent]", BOOK).silent
    assert parse_reply("[mood:bored][silent]", BOOK).silent


def test_unknown_stickers_and_think_blocks_dropped():
    reply = parse_reply("<think>internal</think>好的[sticker:nonexistent]", BOOK)
    assert [b.text for b in reply.bubbles] == ["好的"]


def test_too_many_lines_merge_into_last_bubble():
    reply = parse_reply("\n".join(str(i) for i in range(8)), BOOK, max_bubbles=3)
    assert len(reply.bubbles) == 3
    assert reply.bubbles[-1].text == "2 3 4 5 6 7"


def test_humanizer_splits_long_bubbles_and_drops_full_stops():
    h = Humanizer(BehaviorConfig(), random.Random(1))
    long = "这是一个特别特别长的句子，用来测试拆分。" * 3 + "最后一句。"
    out = h.shape([Bubble([Segment("text", long)], source=long)])
    assert len(out) >= 2 and all(len(b.text) <= 60 for b in out)
    tidy = h.shape([Bubble([Segment("text", "好的。")], source="好的。")])
    assert tidy[0].text in ("好的", "好的。")


def test_typing_delay_scales_with_length_and_respects_bounds():
    h = Humanizer(BehaviorConfig(typing_cps=6), random.Random(2))
    short = h.typing_delay(Bubble([Segment("text", "嗯")]))
    long = h.typing_delay(Bubble([Segment("text", "这是一句挺长的话" * 4)]))
    assert 0.8 <= short < long <= 9.0
    h.scale = 0
    assert h.typing_delay(Bubble([Segment("text", "x" * 50)])) == 0


def test_sticker_rendering_per_platform():
    assert BOOK.render("laugh", "qq") == ("face", "182")
    assert BOOK.render("laugh", "bilibili") == ("text", "[笑哭]")
    assert BOOK.render("doge", "douyin") == ("text", "🐶")


def test_stage_directions_are_dropped_but_short_emotes_kept():
    reply = parse_reply("嗨~我是可乐\n（突然想到了一部老电影，准备去查查海报）\n（捂脸）\n[voice]晚安呀[voice]", BOOK)
    assert [b.text or b.voice for b in reply.bubbles] == ["嗨~我是可乐", "（捂脸）", "晚安呀"]
