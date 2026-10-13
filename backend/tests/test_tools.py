"""工具层单元测试：不依赖大模型，纯逻辑可复现。

运行（backend 目录下）：
    python -I -m pytest tests/ -v
或无 pytest 时：
    python -I tests/test_tools.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools import ToolContext, calc_gpa, query_scores, gen_document, list_ddls, _score_to_gpa


def test_score_to_gpa_boundaries():
    assert _score_to_gpa(90) == 4.0
    assert _score_to_gpa(89) == 3.7
    assert _score_to_gpa(60) == 1.0
    assert _score_to_gpa(59) == 0.0


def test_calc_gpa_weighted():
    ctx = ToolContext(courses=[
        {"name": "高数", "credit": 4, "score": 90},   # 4.0 * 4
        {"name": "英语", "credit": 2, "score": 75},   # 2.7 * 2
    ])
    r = calc_gpa(ctx)
    assert r["ok"]
    assert r["total_credit"] == 6
    # (4.0*4 + 2.7*2) / 6 = 3.567
    assert abs(r["gpa"] - 3.567) < 0.01
    assert r["failed_courses"] == []


def test_calc_gpa_empty():
    assert calc_gpa(ToolContext(courses=[]))["ok"] is False


def test_calc_gpa_detects_fail():
    ctx = ToolContext(courses=[{"name": "物理", "credit": 3, "score": 55}])
    r = calc_gpa(ctx)
    assert r["failed_courses"] == ["物理"]


def test_query_scores_filter():
    ctx = ToolContext(courses=[
        {"name": "大学物理", "credit": 3, "score": 88},
        {"name": "大学英语", "credit": 2, "score": 70},
    ])
    r = query_scores(ctx, keyword="物理")
    assert r["ok"] and len(r["courses"]) == 1


def test_gen_document_fills_fields():
    r = gen_document(ToolContext(), "请假条", {"姓名": "张三", "请假事由": "感冒发烧", "请假天数": "2"})
    assert r["ok"]
    assert r["title"] == "请假条"
    assert "张三" in r["text"] and "感冒发烧" in r["text"] and "2" in r["text"]
    labels = [f["label"] for f in r["fields"]]
    assert "姓名" in labels and "请假事由" in labels


def test_gen_document_blank_for_missing():
    r = gen_document(ToolContext(), "请假条", {"姓名": "张三"})
    assert r["ok"]
    assert "＿＿" in r["text"]          # 未提供的字段渲染成空白线
    assert "张三" in r["text"]


def test_gen_document_unknown_type():
    r = gen_document(ToolContext(), "不存在的类型", {})
    assert r["ok"] is False
    assert "请假条" in r["types"]


def test_list_ddls_sorted():
    ctx = ToolContext(ddls=[
        {"title": "数据结构大作业", "due": "2026-11-20"},
        {"title": "英语演讲", "due": "2026-11-15"},
    ])
    r = list_ddls(ctx)
    assert r["ok"]
    assert r["ddls"][0]["title"] == "英语演讲"  # 更早的排前面


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} 通过")
