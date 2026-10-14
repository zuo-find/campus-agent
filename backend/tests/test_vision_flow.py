"""拍照识别链路测试。

不真的调用多模态模型（不需要 vision key）：把 vision._ask_image 换成假实现，
验证「识别文本 → 交给对应 Agent → 产出待办/成绩」这条链是通的。

运行（backend 目录下）：
    python -I tests/test_vision_flow.py
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app import vision                                    # noqa: E402
from app.tools import ToolContext                         # noqa: E402

NOTICE = """关于举办第二届计算机综合实践挑战赛的通知
各班级：
  一、报名时间：2026年10月20日至10月31日
  二、作品提交截止：2026年11月30日
  三、答辩时间：2026年12月5日
电子信息工程学院
2026年10月10日"""

SCORES_JSON = ('```json\n{"courses":[{"name":"高等数学","credit":4,"score":88},'
               '{"name":"大学英语","credit":3,"score":"良好"},'
               '{"name":"体育","credit":1,"score":"合格"},'
               '{"name":"合计","credit":0,"score":-1}]}\n```')


def fake_ask(image, prompt, vision_llm, system=vision.VISION_SYSTEM, max_tokens=1200):
    """假装多模态模型：按提示词判断这次要做什么。"""
    if "JSON" in prompt:
        return SCORES_JSON
    if "题目" in prompt:
        return "1. 给定整数数组，求和最大的连续子数组。"
    return NOTICE


vision._ask_image = fake_ask


def main() -> int:
    ctx = ToolContext(courses=[], ddls=[], user_name="同学")
    fails = []

    # ---- 1. 拍成绩单：结构化抽取 ----
    r = vision.handle("data:image/jpeg;base64,x", "scores", "", [], ctx)
    names = [c["name"] for c in r["courses"]]
    print("[scores] 抽出课程:", names)
    if names != ["高等数学", "大学英语", "体育"]:
        fails.append("成绩单抽取结果不对（合计行应被丢掉）")
    if r["courses"][1]["score"] != 82.0:      # 「良好」→ 82
        fails.append("等级换算失败")
    if r["courses"][2]["score"] != 60.0:      # 「合格」→ 60
        fails.append("合格换算失败")

    # ---- 2. 拍通知：转写 → 日程 Agent → 待办 ----
    r = vision.handle("data:image/jpeg;base64,x", "notice", "", [], ctx)
    print("[notice] agent:", r["agent"], "工具:", [t["name"] for t in r["tool_calls"]])
    todos = []
    for t in r["tool_calls"]:
        if t["name"] == "gen_todos" and t["result"].get("ok"):
            todos = t["result"]["todos"]
    print("[notice] 待办:", json.dumps(
        [(t["title"], t["due_text"], t["days_text"]) for t in todos], ensure_ascii=False))
    if len(todos) < 3:
        fails.append("通知里的时间点没被整理成待办（少于 3 条）")
    if not r["ocr"]:
        fails.append("没有回传识别出的原文")

    # ---- 3. 拍题：转写 → 刷题 Agent ----
    r = vision.handle("data:image/jpeg;base64,x", "solve", "", [], ctx)
    print("[solve] agent:", r["agent"], "| 题干长度:", len(r["ocr"]), "| 回答长度:", len(r["reply"]))
    if r["agent"] != "study" or not r["reply"]:
        fails.append("拍题没有走刷题 Agent")

    print()
    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
