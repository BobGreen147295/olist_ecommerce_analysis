#!/usr/bin/env python
"""
Agent 运行入口

用法:
    python run_agent.py "圣保罗州最近销量怎么样"
    python run_agent.py "分析最近半年的销售趋势"
    python run_agent.py "客户流失预警，给出挽回建议"
"""

import sys
import os

# Windows GBK 终端兼容: 强制 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    if len(sys.argv) < 2:
        print("用法: python src/agent/run_agent.py \"你的问题\"")
        print("示例: python src/agent/run_agent.py \"圣保罗州最近销量怎么样\"")
        sys.exit(1)

    user_query = sys.argv[1]

    try:
        from src.agent.agent_graph import run

        print(f"\n🤖 AI Agent 启动...")
        print(f"   问题: {user_query}\n")

        result = run(user_query)

        # 输出数据查询
        print("=== 🔍 数据查询 ===\n")
        tool_results = result.get("tool_results", [])
        if tool_results:
            for i, tr in enumerate(tool_results, 1):
                tool_name = tr.get("tool", "?")
                success = tr.get("success", False)
                summary = tr.get("summary", "")
                status = "✅" if success else "❌"
                print(f"  {i}. [{tool_name}] {status}")
                print(f"     {summary}\n")
        else:
            print("  无数据\n")

        # 输出分析
        print("=== 📊 分析 ===\n")
        analysis = result.get("analysis", "")
        if analysis:
            print(f"  {analysis}\n")
        else:
            print("  无分析结果\n")

        # 输出策略建议
        print("=== 💡 策略建议 ===\n")
        recommendation = result.get("recommendation", "")
        if recommendation:
            print(f"  {recommendation}\n")
        else:
            print("  无策略建议\n")

        # 输出错误信息
        if result.get("error"):
            print(f"⚠️  错误: {result['error']}")
            sys.exit(1)

        print("✅ Agent 执行完毕\n")

    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("   请确保已安装依赖: pip install -r requirements.txt")
        print("   并确保已安装 Ollama: https://ollama.com")
        print("   并拉取模型: ollama pull qwen3:8b")
        sys.exit(1)

    except Exception as e:
        print(f"❌ 执行错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
