from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creator_hub.config import DEFAULT_BRANDS, DEFAULT_DB, DEFAULT_SETTINGS
from creator_hub.service import CreatorHub
from creator_hub.ai.provider import PROTOCOLS, GENERIC_KEY_ENV, protocol_default_base_url


def choose(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(prompt + suffix + ": ").strip()
    return value or default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-only", action="store_true")
    args = ap.parse_args()
    hub = CreatorHub(DEFAULT_DB, DEFAULT_SETTINGS, DEFAULT_BRANDS)
    current = hub.ai_status()

    print("YouTube Creator Data Hub - AI 可选配置向导")
    print("AI 不是核心依赖：不配置任何 AI API，现有功能仍可正常使用。")
    print("v3.1 不维护固定模型目录；你可以自行输入 API Base URL、API Key 和模型 ID。\n")

    if args.key_only:
        label = current.get("protocol_label") or current.get("protocol") or "当前 AI 接口"
        key = getpass.getpass(f"请输入 {label} 使用的 API Key: ").strip()
        if not key:
            print("未输入 Key，没有修改。")
            return 1
        hub.configure_ai({}, api_key=key)
        print(f"API Key 已保存到本机供应商中立密钥槽：{GENERIC_KEY_ENV}")
        return 0

    choices = [
        ("1", "openai_responses", "Responses API（OpenAI 等）"),
        ("2", "openai_chat", "OpenAI-compatible Chat Completions（自定义兼容 API / 网关）"),
        ("3", "anthropic_messages", "Anthropic Messages"),
        ("4", "gemini_generate_content", "Gemini generateContent"),
        ("5", "mock", "Mock / 离线测试（不调用真实 AI）"),
    ]
    print("请选择你的 API 使用的接口协议。这里选的是请求格式，不是固定模型供应商：")
    for n, _, label in choices:
        print(f"  {n}. {label}")
    current_protocol = str(current.get("protocol") or "openai_responses")
    default_num = next((n for n, p, _ in choices if p == current_protocol), "1")
    raw = choose("接口协议", default_num)
    protocol = next((p for n, p, _ in choices if n == raw), raw)
    if protocol not in PROTOCOLS or protocol == "disabled":
        print("不支持的接口协议。")
        return 2

    base_url = ""
    key = ""
    model = str(current.get("model") or "") if current_protocol == protocol else ""
    if protocol == "mock":
        model = choose("模型 ID", model or "mock-v1")
    else:
        default_base = str(current.get("base_url") or "") if current_protocol == protocol else protocol_default_base_url(protocol)
        print("\nAPI Base URL 可以使用默认值，也可以填写你自己的兼容 API / 网关地址。")
        base_url = choose("API Base URL", default_base)
        print("请输入 API Key；若本机已经保存了当前 Key，可直接回车保留。输入内容不会回显。")
        key = getpass.getpass("API Key: ").strip()

        # Try model discovery before asking the user to type an ID. A failed /models
        # endpoint is not fatal because some gateways intentionally do not expose it.
        patch = {"protocol": protocol, "base_url": base_url, "model": model or "temporary-model", "enabled": True}
        try:
            listed = hub.ai_models(patch, api_key=(key or None)).get("models") or []
        except Exception as exc:
            listed = []
            print(f"无法自动读取模型列表：{exc}")
            print("这不代表 API 一定不可用；可以继续输入 API 文档给出的模型 ID。")
        if listed:
            print(f"\nAPI 返回 {len(listed)} 个可用模型。以下显示前 30 个：")
            for mid in listed[:30]:
                print("  " + str(mid))
        model = choose("模型 ID（可输入任意由当前 API 支持的 ID）", model)
        if not model:
            print("必须填写模型 ID。")
            return 2

    try:
        limit = int(choose("每日 AI 请求软上限", str(current.get("daily_request_soft_limit") or 100)))
    except ValueError:
        print("请求上限必须是整数。")
        return 2
    status = hub.configure_ai(
        {
            "enabled": True,
            "protocol": protocol,
            "base_url": base_url,
            "model": model,
            "daily_request_soft_limit": limit,
            "api_key_env": GENERIC_KEY_ENV,
        },
        api_key=(key or None),
    )
    print("\n已保存配置：")
    print(json.dumps({k: status.get(k) for k in ["enabled", "available", "protocol", "model", "base_url", "api_key_present", "api_key_source", "daily_request_soft_limit"]}, ensure_ascii=False, indent=2))
    if protocol != "mock":
        ans = choose("现在测试 API 连接？(Y/n)", "Y").lower()
        if ans not in {"n", "no"}:
            try:
                print(json.dumps(hub.ai_test(), ensure_ascii=False, indent=2, default=str))
            except Exception as exc:
                print(f"连接测试失败：{exc}")
                print("配置已经保留；可以在 Dashboard 中修改 Base URL / 模型 ID / API Key 后再次测试。")
                return 3
    print("\nAI 配置完成。如果交互 Dashboard 已经在运行，请重启 start-dashboard.cmd。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
