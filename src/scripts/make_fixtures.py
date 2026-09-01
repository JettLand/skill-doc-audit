#!/usr/bin/env python3
# make_fixtures.py —— 声明式 recipe 生成器（self_validate.py 的技术兜底）
#
# 设计：把每个 fixture 的"手工创建过程"编码为 recipe（frontmatter + 文件内容），
# 运行时精确复刻 tests/fixtures/。与"从 golden 反推"的弱方案不同——recipe 复刻的是
# 原始 fixture 本身（无损），golden 快照仍只作断言基准，因此不削弱回归严格性。
#
# 仅 dev 工具：不进 dist / 部署副本；self_validate.py 依赖本工具产出的 fixtures。
# 仓库根经 __file__ 解析，不依赖 CWD（新环境 clone 后任意目录可跑）。
#
# 用法：
#   python src/scripts/make_fixtures.py                # 重建 tests/fixtures/
#   python src/scripts/make_fixtures.py --check        # 校验现有 fixtures 与 recipe 一致（不写盘）
#   python src/scripts/make_fixtures.py --out DIR      # 输出到指定目录
#   python src/scripts/make_fixtures.py --baseline     # 重建 fixtures 后一并重建黄金快照 tests/examples/*.expected.json（人工显式动作）
import os, sys, argparse, json

HERE = os.path.dirname(os.path.abspath(__file__))        # <root>/src/scripts
ROOT = os.path.dirname(os.path.dirname(HERE))            # <root>
DEFAULT_OUT = os.path.join(ROOT, "tests", "fixtures")

# 每个 fixture 的设计意图（仅文档用途，不参与生成）
INTENT = {
  "dirty-skill": "多类违规集中：死路径(引用不存在的 scripts/ghost.py / references/old_notes.md) + 语法错误(broken_syntax.py) + 死代码(unreferenced_module.py / main.py 的 unused_helper) + 硬编码凭据(main.py 的 API_KEY)",
  "multifile": "跨文件引用：scripts/b.py 经 `from a import shared_helper` 依赖 a.py，验证跨文件可达性",
  "tricky-clean": "看似可疑其实合规：含 URL、`@app.route` 代码块、`import os # keep` 等，验证检查器不误报（error=0/warn=0）",
  "ts-skill": "TypeScript 技能：scripts/main.ts 含硬编码凭据，验证 portability/security 对 TS 的处理",
}

# FIXTURES: name -> {"files": {相对路径: 文件内容}}
# 内容为已提交 fixtures 的精确副本（LF/CRLF 与当前工作副本一致），保证重建字节一致。
FIXTURES = {'dirty-skill': {'files': {'SKILL.md': '---\nname: dirty-wrong\ndisplayName: Dirty Test\ndescription: 测试用的脏技能，含多种文档漂移与死代码问题。\nversion: "0.0.1"\nlicense: MIT\nauthor: test\ntags: [test]\n---\n\n# Dirty Test\n\n本技能用于压力测试，故意制造多种文档漂移、安全与死代码问题。\n\n## 用法\n\n```sh\npython scripts/main.py --recalc\n```\n\n参考脚本 `scripts/ghost.py` 与历史说明 `references/old_notes.md`。\n\n## 退出码\n\n| 退出码 | 含义 |\n| --- | --- |\n| `0` | 成功 |\n| `7` | 部分失败（文档声明但代码从不返回） |\n\n## 内部\n\n调用 `tune_model` 完成训练流程。\n\nTODO: fix this section\n', 'scripts/broken_syntax.py': 'def broken(:\n    pass\n', 'scripts/main.py': 'import json\nimport os\nimport subprocess\n\nAPI_KEY = "AKIA1234567890ABCDEFXYZ"\n\ndef run():\n    base = "/data"\n    name = "x"\n    path = base + "/../" + name\n    subprocess.run(["ffmpeg", "-i", "in.mp4", "out.mp4"])\n    return path\n\ndef demo():\n    x = 1\n    return x\n    print("unreachable after return")\n\ndef unused_helper():\n    return 42\n\nresult = run()\nprint(result)\n', 'scripts/unreferenced_module.py': 'def helper_only():\n    return "never imported anywhere"\n\n\nclass OldUtil:\n    pass\n'}}, 'multifile': {'files': {'SKILL.md': '---\nname: multifile\ndisplayName: Multifile\ndescription: 多文件死代码误报验证夹具。\nversion: "0.1.0"\nlicense: MIT\nauthor: test\ntags: [test]\n---\n\n# Multifile\n\nscripts/a.py 定义 shared_helper，scripts/b.py 通过 `from a import shared_helper` 使用它。\n', 'scripts/a.py': 'def shared_helper():\n    return 42\n', 'scripts/b.py': 'from a import shared_helper\nprint(shared_helper())\n'}}, 'tricky-clean': {'files': {'SKILL.md': '---\nname: tricky-clean\ndisplayName: Tricky Clean\ndescription: 用于验证误报抑制的干净技能，含字符串键分发、装饰器注册、# keep 白名单与文档 URL。\nversion: "1.0.0"\nlicense: MIT\nauthor: test\ntags: [test]\n---\n\n# Tricky Clean\n\n调用 `scripts/main.py`，详见 https://example.com/api/v2/guide 。\n\n## 路由\n\n用装饰器注册入口：@app.route。主入口为 main()。\n\n文档 URL 示例 https://docs.example.org/v1/path/../resource （含 ../ 但属文档 URL，非真实穿越）。\n', 'scripts/main.py': 'import os  # keep\nimport json\n\nHANDLERS = {\n    "create": create,\n    "update": update,\n}\n\ndef create(ctx):\n    return do_work(ctx)\n\ndef update(ctx):\n    return do_work(ctx)\n\ndef do_work(ctx):\n    data = json.dumps(ctx)\n    return data\n\n@app.route("/x")\ndef main():\n    return HANDLERS["create"]({})\n\nif __name__ == "__main__":\n    main()\n'}}, 'ts-skill': {'files': {'SKILL.md': '---\nname: ts-skill\ndisplayName: TS Skill\ndescription: TypeScript 技能多语言覆盖验证夹具。\nversion: "0.1.0"\nlicense: MIT\nauthor: test\ntags: [test]\n---\n\n# TS Skill\n\n运行 `scripts/main.ts` 中的 `runGame` 启动游戏。\n', 'scripts/main.ts': 'export function runGame() {\n  const API_KEY = "AKIA1234567890ABCDEFXYZ";\n  return API_KEY.length;\n}\n'}}}

def build(out_dir, write=True, quiet=False):
    for name, spec in FIXTURES.items():
        d = os.path.join(out_dir, name)
        for rel, content in spec["files"].items():
            p = os.path.join(d, rel)
            if write:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
        if not quiet:
            print("fixture: %s (%d files)" % (name, len(spec["files"])))

def check(out_dir):
    ok = True
    for name, spec in FIXTURES.items():
        d = os.path.join(out_dir, name)
        for rel, content in spec["files"].items():
            p = os.path.join(d, rel)
            if not os.path.isfile(p):
                print("MISSING: %s" % p); ok = False; continue
            cur = open(p, encoding="utf-8", newline="").read()
            if cur != content:
                print("MISMATCH: %s" % p); ok = False
    print("check: %s" % ("OK" if ok else "MISMATCH"))
    return ok

def rebuild_baseline():
    """重建黄金快照 tests/examples/*.expected.json（复用 self_validate 的掩码逻辑）。

    复用 self_validate.normalize（顶层 skill 路径 -> <ROOT>），保证与
    `self_validate.py --baseline` 产出一致。

    注意：这是人工显式动作，不是 self_validate 正常校验流程的一部分——
    若在正常流程自动重建黄金快照，会拿「当前逻辑输出」比「当前逻辑输出」，
    永远 PASS，从而削弱回归护栏。黄金快照必须保持入库（断言基线）。
    """
    sys.path.insert(0, HERE)
    import self_validate as sv
    from auditlib.model import analyze_skill
    manifest = json.load(open(sv.MANIFEST, encoding="utf-8"))
    for ex in manifest.get("examples", []):
        fx = ex.get("fixture"); golden = ex.get("golden")
        if not fx or not golden:
            continue
        fx_path = os.path.join(sv.FIX, fx)
        checkers = ex.get("checkers") or sv.DETERMINISTIC
        results = analyze_skill(fx_path, enabled=list(checkers), args=None)
        got = sv.normalize(results)
        golden_path = os.path.join(sv.EXAMPLES, golden)
        json.dump(got, open(golden_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("baseline: %s -> %s" % (fx, golden))
    print("黄金快照已重建。请人工评审 diff 后提交 tests/examples/。")


def main():
    ap = argparse.ArgumentParser(description="fixtures 声明式生成器（self_validate 辅助套件）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出目录（默认 tests/fixtures）")
    ap.add_argument("--check", action="store_true", help="校验现有 fixtures 与 recipe 一致，不写盘")
    ap.add_argument("--baseline", action="store_true",
                    help="重建 fixtures 后一并重建黄金快照 tests/examples/*.expected.json（人工显式动作，非自校验自动调用）")
    args = ap.parse_args()
    if args.baseline:
        build(args.out)
        rebuild_baseline()
        sys.exit(0)
    if args.check:
        sys.exit(0 if check(args.out) else 1)
    build(args.out)
    print("fixtures 已重建于: %s" % args.out)

if __name__ == "__main__":
    main()
