import glob, os, sys, json, argparse

# ---- 仓库根解析（fresh-clone 安全：完全基于 __file__，不依赖 CWD）----
HERE = os.path.dirname(os.path.abspath(__file__))          # <root>/src/scripts
SCRIPTS = HERE
ROOT = os.path.dirname(os.path.dirname(HERE))             # <root>
TESTS = os.path.join(ROOT, 'tests')
FIX = os.path.join(TESTS, 'fixtures')
EXAMPLES = os.path.join(TESTS, 'examples')
MANIFEST = os.path.join(EXAMPLES, 'manifest.json')

def fail(msg, code=2):
    sys.stderr.write('[self_validate] ERROR: %s\n' % msg)
    sys.exit(code)

# ---- 导入审计器包（触发检查器自注册）----
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
try:
    import auditlib                       # noqa: F401  (导入即触发 checkers 自注册)
    from auditlib.model import analyze_skill
    from auditlib.report import build_json
except Exception as e:
    fail('无法导入 auditlib 包：%s\n（请确认在仓库源码环境运行，且 scripts/auditlib/ 完整）' % e)

# 仅用确定性检查器，避免 vulture 版本 / agent 推理带来的黄金快照漂移
DETERMINISTIC = ["doc", "structure", "security", "runtime", "deps"]


def normalize(results):
    """掩码唯一易变项：顶层 skill 绝对路径 -> <ROOT>。

    build_json 期望结果列表（cli 以 [results] 传入），故此处同样包成单元素列表。
    """
    lst = build_json([results])  # build_json 返回结果列表（cli 再 json.dumps）
    r = lst[0]
    if isinstance(r.get('skill'), str):
        r['skill'] = '<ROOT>'
    # findings 内部 file 已是相对路径；line 稳定；保持原样以便精确比对
    return r


def finding_signature(f):
    # 以 (checker, category, severity, file, message) 做语义化比对，忽略 line 偏移
    return (f.get('checker'), f.get('category'), f.get('severity'),
            f.get('file'), f.get('message'))


def diff_results(got, exp):
    diffs = []
    for k in ('error', 'warn', 'info', 'pass'):
        g = got.get('summary', {}).get(k)
        e = exp.get('summary', {}).get(k)
        if g != e:
            diffs.append('summary.%s: expected=%s got=%s' % (k, e, g))
    gf = sorted(finding_signature(f) for f in got.get('findings', []))
    ef = sorted(finding_signature(f) for f in exp.get('findings', []))
    import collections
    gc = collections.Counter(gf); ec = collections.Counter(ef)
    for sig, n in (gc - ec).items():
        diffs.append('额外发现(+%d): %s' % (n, sig))
    for sig, n in (ec - gc).items():
        diffs.append('缺失发现(-%d): %s' % (n, sig))
    return diffs


def main():
    ap = argparse.ArgumentParser(description='skill-doc-audit 内置自校验工具（Vector 3）')
    ap.add_argument('--baseline', action='store_true',
                    help='重新生成黄金快照 tests/examples/*.expected.json（评审后提交）')
    args = ap.parse_args()

    if not os.path.isdir(FIX):
        fail('未找到 fixtures 目录：%s\n（self_validate 仅能在源码仓库环境运行；若 fixtures 丢失，可运行 `python src/scripts/make_fixtures.py` 重建）' % FIX)
    if not os.path.isfile(MANIFEST):
        fail('未找到 manifest：%s' % MANIFEST)

    manifest = json.load(open(MANIFEST, encoding='utf-8'))
    examples = manifest.get('examples', [])
    if not examples:
        fail('manifest 中无 examples 条目')

    overall = True
    for ex in examples:
        name = ex.get('name', '<unnamed>')
        fx = ex.get('fixture')
        checkers = ex.get('checkers') or DETERMINISTIC
        golden_rel = ex.get('golden')
        if not fx or not golden_rel:
            fail('示例 %s 缺少 fixture / golden 字段' % name)
        fx_path = os.path.join(FIX, fx)
        golden_path = os.path.join(EXAMPLES, golden_rel)
        if not os.path.isdir(fx_path):
            fail('fixture 不存在：%s\n（可运行 `python src/scripts/make_fixtures.py` 重建 tests/fixtures/）' % fx_path)

        results = analyze_skill(fx_path, enabled=list(checkers), args=None)
        got = normalize(results)

        if args.baseline:
            os.makedirs(EXAMPLES, exist_ok=True)
            json.dump(got, open(golden_path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
            print('[BASELINE] %s -> %s' % (name, golden_rel))
            continue

        if not os.path.isfile(golden_path):
            print('[SKIP] %s: 黄金快照缺失（先跑 --baseline）' % name)
            overall = False
            continue

        exp = json.load(open(golden_path, encoding='utf-8'))
        diffs = diff_results(got, exp)
        if diffs:
            overall = False
            print('[FAIL] %s' % name)
            for d in diffs:
                print('       - %s' % d)
        else:
            print('[PASS] %s  (summary: error=%s warn=%s info=%s pass=%s)' % (
                name, got['summary']['error'], got['summary']['warn'],
                got['summary']['info'], got['summary']['pass']))

    if args.baseline:
        print('\n黄金快照已生成。请人工评审后提交 tests/examples/。')
        sys.exit(0)
    sys.exit(0 if overall else 1)


if __name__ == '__main__':
    main()
