"""热点雷达：B站综合热门（OneAPI）解析。"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import app as web  # noqa: E402


def test_parse_oneapi_bili_hot_maps_title_view_and_link():
    obj = {
        "code": 200,
        "message": "success",
        "data": {
            "code": 0,
            "message": "OK",
            "data": {
                "list": [
                    {
                        "title": "好久不见啊，佐助",
                        "stat": {"view": 997506, "vv": 997506},
                        "short_link_v2": "https://b23.tv/BV1B1hJ6wEwe",
                        "bvid": "BV1B1hJ6wEwe",
                    },
                    {"title": "无短链", "stat": {"vv": 12}, "bvid": "BV1xxxx"},
                    {"title": "  ", "stat": {"view": 1}},
                    "不是对象",
                ],
                "no_more": False,
            },
        },
    }
    assert web._parse_oneapi_bili_hot(obj) == [
        {"title": "好久不见啊，佐助", "hot": "997506", "url": "https://b23.tv/BV1B1hJ6wEwe"},
        {"title": "无短链", "hot": "12", "url": "https://www.bilibili.com/video/BV1xxxx"},
    ]


def test_parse_oneapi_bili_hot_rejects_non_success():
    assert web._parse_oneapi_bili_hot({"code": 301, "message": "余额不足", "data": {}}) == []
    assert web._parse_oneapi_bili_hot({"code": 200, "data": {"code": 0, "data": {}}}) == []


def test_bilibili_trends_prefer_oneapi(monkeypatch):
    monkeypatch.setattr(
        web, "_fetch_bilibili_oneapi",
        lambda: [{"title": "综合热门", "hot": "1", "url": "https://b23.tv/x"}],
    )

    def _boom(url):
        raise AssertionError(url)

    monkeypatch.setattr(web, "_http_get_json", _boom)
    assert web._fetch_platform("bilibili")[0]["title"] == "综合热门"


def test_bilibili_falls_back_when_oneapi_empty(monkeypatch):
    monkeypatch.setattr(web, "_fetch_bilibili_oneapi", lambda: [])
    monkeypatch.setattr(
        web, "_http_get_json",
        lambda url: {"data": [{"title": "备用热榜", "hot": "9", "url": "https://example.com"}]},
    )
    assert web._fetch_platform("bilibili")[0]["title"] == "备用热榜"
