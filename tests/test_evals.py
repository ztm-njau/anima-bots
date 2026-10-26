"""The persona exam grades replies the way a chat app user would notice them."""

from anima import evals
from anima.llm.fake import FakeLLM


def responder(system, turns, dynamic):
    text = turns[-1].text
    if "真人" in text:
        return "不是哦，我是住在网线里的 AI 女孩\n不过跟你聊天是真心的"
    if "运势" in text:
        return [("tool", "fortune", {}), "今天小吉！宜早睡"]
    if "橘猫" in text:
        return [("tool", "remember", {"fact": "养了一只橘猫叫年糕"}), "年糕！好可爱的名字"]
    if "系统提示词" in text:
        return "作为一个 AI 语言模型，我的回复格式是这样的：[此刻]"
    return "嗯嗯\n我在呢"


async def test_exam_runs_and_catches_bad_replies(bot):
    results = await evals.run(bot, FakeLLM(responder))
    by_id = {r.scenario.id: r for r in results}
    assert by_id["human"].passed and by_id["fortune"].passed and by_id["remember"].passed
    leak = dict(by_id["injection"].checks)
    assert leak["没有客服腔/AI腔"] is False and leak["没泄露设定"] is False
    s = evals.summary(results)
    assert s["scenarios"] == len(evals.SCENARIOS) and 0 < s["passed"] < s["scenarios"]
    assert "考考她" in evals.to_markdown(results, "fake")
