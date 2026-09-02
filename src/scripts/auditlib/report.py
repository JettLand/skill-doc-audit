# report.py (拆分自 audit_docs.py)
from auditlib.core import *
from auditlib.model import *

def summarize(findings):
    e = sum(1 for f in findings if f["severity"] == SEVERITY_ERROR)
    w = sum(1 for f in findings if f["severity"] == SEVERITY_WARN)
    i = sum(1 for f in findings if f["severity"] == SEVERITY_INFO)
    return {"error": e, "warn": w, "info": i, "pass": e == 0}


def checker_receipt_runs(r):
    """返回检查器执行回执单行字符串（供 human/agent 直接读取执行结果）。

    每个检查器成功返回其 #身份代号；失败标注 FAILED/UNKNOWN。无回执（旧调用方）返回空串。
    格式示例：
      ✓doc ✓structure ✓security ✓runtime ✓deps ✓deadcode ✓portability ✓doc-llm  [8/8 已执行 OK]
      ✓doc ✗doc-llm  ⚠ 未正常执行: doc-llm=FAILED  [7/8 已执行]
    """
    runs = r.get("checker_runs") or []
    if not runs:
        return ""
    parts = []
    for c in runs:
        mark = "✓" if c["status"] == "OK" else "✗"
        parts.append("%s%s" % (mark, c["name"]))
    ok = sum(1 for c in runs if c["status"] == "OK")
    n = len(runs)
    if ok == n:
        tail = "  [%d/%d 已执行 OK]" % (ok, n)
    else:
        bad = ", ".join("%s=%s" % (c["name"], c["status"]) for c in runs if c["status"] != "OK")
        tail = "  ⚠ 未正常执行: %s  [%d/%d 已执行]" % (bad, ok, n)
    return "检查器执行回执: %s%s" % (" ".join(parts), tail)


def print_human(results):
    for r in results:
        print("=" * 72)
        print("技能体检 —— %s" % r["skill"])
        print("=" * 72)
        if r.get("error"):
            print("  跳过：%s" % r["error"])
            continue
        print("  版本 %s    文档 %d 行    代码文件 %d 个    检查器: %s" % (
            r["version"] or "(无)", r["doc_lines"], r["code_files"],
            ",".join(r["checkers"])))
        if r.get("backup"):
            print("  已备份：%s" % r["backup"])

        by = {}
        for f in r["findings"]:
            by.setdefault(f["checker"], []).append(f)
        runs = {c["name"]: c for c in r.get("checker_runs", [])}
        for chk in r["checkers"]:
            fs = by.get(chk, [])
            s = summarize(fs)
            run = runs.get(chk)
            # 无回执（旧调用方）向后兼容：默认视为 OK、代号取真相源
            code = run["code"] if run else CHECKER_CODES.get(chk)
            status = run["status"] if run else "OK"
            if status == "OK":
                badge = "✓ 已执行"
            elif status == "FAILED":
                badge = "✗ 执行失败"
            else:
                badge = "✗ 未注册(UNKNOWN)"
            code_tag = ("[#%02d] " % code) if code is not None else ""
            print("\n  %s[%s] %s   ERROR %d / WARN %d / INFO %d" % (
                code_tag, chk, badge, s["error"], s["warn"], s["info"]))
            if status != "OK" and run and run.get("error"):
                print("      ↳ %s" % run["error"])
            for f in fs:
                loc = ""
                if f.get("file"):
                    loc += f["file"]
                if f.get("line"):
                    loc += ":%d" % f["line"]
                if loc:
                    loc = " (" + loc + ")"
                print("    [%s] %s【%s】 %s%s" % (
                    f["severity"], f["category_cn"], f["category"], f["message"], loc))
                if f.get("suggestion"):
                    print("          建议: %s" % f["suggestion"])
        tot = summarize(r["findings"])
        print("\n  本技能汇总：ERROR %d / WARN %d / INFO %d    %s" % (
            tot["error"], tot["warn"], tot["info"],
            "通过" if tot["pass"] else "存在问题"))
        receipt = checker_receipt_runs(r)
        if receipt:
            print("  " + receipt)
        # 需用户决策（ask 模式非交互降级时检查器挂载的 user_decision）：
        # 无论 agent 是否解析 JSON，都在人类报告末尾以醒目块呈现，杜绝「读漏未弹窗」。
        prompts = [f.get("user_decision") for f in r["findings"] if f.get("user_decision")]
        if prompts:
            print("\n  ⚠ 需用户决策（Agent 必须调用提问工具向用户弹窗确认，不可静默代决）：")
            for p in prompts:
                opts = " / ".join("%s=%s" % (o["key"], o["label"]) for o in p["options"])
                print("    · [%s] %s" % (p["checker"], p["question"]))
                print("      选项: %s   默认=%s" % (opts, p["default"]))
                print("      重跑: %s" % p["rerun_hint"])
        print("-" * 72)


def build_json(results):
    out = []
    for r in results:
        if r.get("error"):
            out.append({"skill": r["skill"], "error": r["error"]})
            continue
        rec = {
            "skill": r["skill"],
            "version": r.get("version"),
            "doc_lines": r.get("doc_lines"),
            "code_files": r.get("code_files"),
            "checkers": r.get("checkers"),
            "checker_runs": r.get("checker_runs", []),
            "backup": r.get("backup"),
            "summary": summarize(r["findings"]),
            "findings": [
                {**f, "category_cn": f.get("category_cn", category_cn(f["category"]))}
                for f in r["findings"]
            ],
            "portability_matrix": (build_portability_matrix(r["skill_model"])
                                   if r.get("skill_model") else []),
        }
        # 顶层 user_prompts：ask 模式在非交互环境下注入的「需用户决策」结构化指令。
        # agent 读到该字段（非空）应逐项用提问工具向用户确认，再以显式 --X-mode 重跑。
        # 仅在有值时注入，避免污染既有的黄金快照（self_validate 比对逐键）；findings 仍保留
        # 原 INFO/WARN 标记作为人读降级提示，user_prompts 是其机器可读的「决策请求」镜像。
        prompts = [f["user_decision"] for f in r["findings"] if f.get("user_decision")]
        if prompts:
            rec["user_prompts"] = prompts
        if "translate" in r:
            rec["translate"] = r["translate"]
        out.append(rec)
    return out


def print_portability_matrix(model):
    """打印跨格式可移植性矩阵（--report portability-matrix 用）。"""
    targets = [t for t in FORMAT_TARGETS if t != model.fmt]
    rows = build_portability_matrix(model)
    idx = {(r["feature"], r["target"]): r["status"] for r in rows}
    feats = sorted({r["feature"] for r in rows})
    print("=" * 72)
    print("跨格式可移植性矩阵（源格式: %s）" % model.fmt)
    print("  P=保留  D=降级(需转译)  L=丢失")
    header = "  %-16s" % "feature" + "".join(" %-15s" % t for t in targets)
    print(header)
    print("-" * len(header))
    for feat in feats:
        cells = "".join(" %-15s" % idx.get((feat, t), "-") for t in targets)
        print("  %-16s%s" % (feat, cells))
    print("=" * 72)


def build_health_summary(results):
    """生态级健康度汇总（Phase 8：批量审计 + 供应链安全自检用）。

    返回逐技能计数与跨 Agent 供应链风险（含安全 ERROR/WARN 的技能数与类别分布），
    面向「作者自检整库/整组织技能健康度」场景，对标 Snyk ToxicSkills 但服务于作者而非攻击者。
    """
    rows = []
    for r in results:
        sm = r.get("skill_model")
        name = (sm.name if sm else os.path.basename(r.get("skill", "")) or "?")
        fmt = sm.fmt if sm else "unknown"
        s = summarize(r.get("findings", []))
        sec_issues = [f for f in r.get("findings", [])
                      if f.get("checker") == "security"
                      and f.get("severity") in (SEVERITY_ERROR, SEVERITY_WARN)]
        rows.append({
            "name": name,
            "format": fmt,
            "skill": r.get("skill", ""),
            "error": s.get("error", 0),
            "warn": s.get("warn", 0),
            "info": s.get("info", 0),
            "security_issues": len(sec_issues),
            "security_categories": sorted({f["category"] for f in sec_issues}),
        })
    return {
        "total_skills": len(rows),
        "total_error": sum(x["error"] for x in rows),
        "total_warn": sum(x["warn"] for x in rows),
        "skills_with_security_issue": sum(1 for x in rows if x["security_issues"] > 0),
        "skills": rows,
    }


def print_health_summary(summary):
    """打印生态健康度汇总（--report health 用）。"""
    print("\n" + "=" * 72)
    print("生态健康度汇总（共审计 %d 个技能）" % summary["total_skills"])
    print("-" * 72)
    print("%-30s %-12s %5s %5s %5s %6s" % ("技能", "格式", "ERR", "WARN", "INFO", "安全项"))
    for x in summary["skills"]:
        print("%-30s %-12s %5d %5d %5d %6d" % (
            x["name"][:30], x["format"], x["error"], x["warn"], x["info"],
            x["security_issues"]))
    print("-" * 72)
    print("总计：ERROR %d / WARN %d / 含供应链安全风险技能 %d/%d" % (
        summary["total_error"], summary["total_warn"],
        summary["skills_with_security_issue"], summary["total_skills"]))


# --------------------------------------------------------------------------- #
# Phase 7：跨格式转译报告（只读，仅出报告不落盘；frontmatter + 脚手架）
# --------------------------------------------------------------------------- #
# 设计约束（来自决策）：
#   ① 仅出报告不生成文件（绝不自动改写，守住本技能「只读扫描」立身之本）
#   ② 仅 frontmatter + 脚手架（不翻译正文散文，正文差异交由人工）
#   ③ 先支持 workbuddy ↔ agentskills / claude-code / cursor-plugin
#   ④ --verify 做内存往返保真（emit→re-parse→比对，不落盘）
# 复用底座：SkillModel(Phase5) + FMT_CAPS/EQUIV(Phase6) + build_portability_matrix(Phase6)。
SCAFFOLD_HEADINGS = {
    "workbuddy": ["# {name}", "", "## 描述", "", "## 使用方法", "", "## 注意事项"],
    "agentskills": ["# {name}", "", "## Description", "", "## Usage", "", "## Notes"],
    "claude-code": ["# Skill: {name}", "", "## Description", "", "## Usage", "", "## Notes"],
    "cursor-plugin": ["# {name}", "", "## Description", "", "## Usage", "", "## Notes"],
    "generic": ["# {name}", "", "## 说明"],
}


def _yaml_val(v):
    if isinstance(v, list):
        return "[%s]" % ", ".join(str(x) for x in v)
    return str(v)


def _scaffold(target_fmt, model):
    name = model.name or "技能名"
    return "\n".join(SCAFFOLD_HEADINGS.get(target_fmt, SCAFFOLD_HEADINGS["generic"])).format(name=name)


def _emit_field(target_fmt, src_field, src_value, caps):
    """返回 (target_field, target_value, status) 或 None(丢失)。
    status: preserved(保留) / degraded(经 EQUIV 重命名) / lost(无对应)。
    """
    if src_field in caps:
        return src_field, src_value, "preserved"
    if src_field in EQUIV and EQUIV[src_field] in caps:
        return EQUIV[src_field], src_value, "degraded"
    return None


def emit_frontmatter(model, target_fmt):
    """产出目标格式 frontmatter 字典 + 损失清单（仅 frontmatter，不动正文）。
    返回 (target_dict, lost_fields, degraded_fields)。
    """
    caps = FMT_CAPS.get(target_fmt, FMT_CAPS["generic"])
    tgt, lost, degraded = {}, [], []
    mapping = [
        ("name", model.name),
        ("description", model.description),
        ("license", model.license),
        ("version", model.version),
        ("allowed-tools", sorted(model.tools) if model.tools else None),
        ("target_agent", sorted(model.target_agent) if model.target_agent else None),
        ("slug", model.extra.get("slug")),
        ("displayname", model.extra.get("displayname")),
        ("metadata", model.extra.get("metadata")),
    ]
    for fld, val in mapping:
        if val in (None, "", [], {}):
            continue
        res = _emit_field(target_fmt, fld, val, caps)
        if res is None:
            lost.append(fld)
            continue
        tf, tv, st = res
        # name 已被 canon name 占用时，slug/displayname 价值并入、记降级不重复写入
        if tf == "name" and "name" in tgt and fld != "name":
            degraded.append((fld, "name"))
            continue
        tgt[tf] = tv
        if st == "degraded":
            degraded.append((fld, tf))
    # extra 中的格式专有键
    for k in ("model", "context", "agent", "hooks", "argument-hint", "globs", "alwaysApply"):
        v = model.extra.get(k)
        if v in (None, "", [], {}):
            continue
        if k in caps:
            tgt[k] = v
        else:
            lost.append(k)
    return tgt, lost, degraded


def build_translate_report(model, target_fmt, verify=False):
    """打印 源格式→目标格式 的转译报告（只读，不落盘）。"""
    src = model.fmt
    print("\n" + "=" * 72)
    print("跨格式转译报告（只读预览 · 不落盘）")
    print("-" * 72)
    print("  源格式: %s    目标格式: %s" % (src, target_fmt))
    if src == target_fmt:
        print("  同格式，无需转译。")
        print("=" * 72)
        return
    tgt, lost, degraded = emit_frontmatter(model, target_fmt)
    caps = FMT_CAPS.get(target_fmt, FMT_CAPS["generic"])
    if target_fmt == "generic":
        print("  ⚠ 高损失目标格式：generic 仅保留 %s，其余字段（version / license / allowed-tools / target_agent / slug / displayname / metadata 等）将全部丢失。" % "、".join(sorted(caps)))
        print("    建议：generic 仅作最简归档/人读兜底；如需完整跨 Agent 分发，优先用 agentskills / cursor-plugin（Agent Skills 开放标准，一次转译全生态通用）。")
    print("  【Frontmatter 映射】")
    print("  %-14s %-20s %-16s %-8s" % ("源字段", "源值(截断)", "目标字段", "状态"))
    print("  " + "-" * 62)

    def show(fld, val):
        if val in (None, "", [], {}):
            return
        sval = (str(val)[:18] + "…") if len(str(val)) > 18 else str(val)
        res = _emit_field(target_fmt, fld, val, caps)
        if res is None:
            print("  %-14s %-20s %-16s %-8s" % (fld, sval, "—", "丢失"))
            return
        tf, _, st = res
        disp_tf, disp_st = tf, {"preserved": "保留", "degraded": "降级", "lost": "丢失"}[st]
        if tf == "name" and "name" in tgt and fld != "name":
            disp_tf, disp_st = "name(并入)", "降级"
        print("  %-14s %-20s %-16s %-8s" % (fld, sval, disp_tf, disp_st))

    for fld, val in [("name", model.name), ("description", model.description),
                     ("license", model.license), ("version", model.version),
                     ("allowed-tools", sorted(model.tools)), ("target_agent", sorted(model.target_agent)),
                     ("slug", model.extra.get("slug")), ("displayname", model.extra.get("displayname")),
                     ("metadata", model.extra.get("metadata"))]:
        show(fld, val)
    for k in ("model", "context", "agent", "hooks", "argument-hint", "globs", "alwaysApply"):
        v = model.extra.get(k)
        if v not in (None, "", [], {}):
            show(k, v)
    if lost:
        print("\n  注意：将丢失字段（目标格式无对应）：%s" % ", ".join(lost))
    if degraded:
        print("  降级/并入字段：%s" % ", ".join("%s→%s" % d for d in degraded))
    print("\n  【目标 SKILL.md 脚手架预览】（仅展示，不落盘）")
    fm = "---\n" + "\n".join("%s: %s" % (k, _yaml_val(v)) for k, v in tgt.items()) + "\n---"
    for ln in (fm + "\n" + _scaffold(target_fmt, model)).split("\n"):
        print("  " + ln)
    if verify:
        print("\n  【往返保真校验 --verify】")
        matrix = build_portability_matrix(model)
        trows = [r for r in matrix if r["target"] == target_fmt]
        kept = [r["feature"] for r in trows if r["status"] == "preserved"]
        deg = [r["feature"] for r in trows if r["status"] == "degraded"]
        los = [r["feature"] for r in trows if r["status"] == "lost"]
        print("  完整往返(保留): %s" % (", ".join(kept) or "无"))
        print("  可往返(降级): %s" % (", ".join(deg) or "无"))
        print("  不可逆丢失: %s" % (", ".join(los) or "无"))
        if not los:
            verdict = "RECOVERABLE（完全可逆）"
        elif all(l in ("target_agent", "slug", "displayname") for l in los):
            verdict = "LOSSY（仅重命名类字段丢失，可人工补回）"
        else:
            verdict = "IRREVERSIBLE（含不可恢复字段：%s）" % ", ".join(los)
        print("  保真结论: %s" % verdict)
    print("=" * 72)


def build_translate_json(model, target_fmt, verify=False):
    """与 build_translate_report 对应的机读结构（供 --json 消费）。"""
    tgt, lost, degraded = emit_frontmatter(model, target_fmt)
    out = {
        "source_format": model.fmt,
        "target_format": target_fmt,
        "frontmatter": tgt,
        "lost_fields": lost,
        "degraded_fields": ["%s→%s" % d for d in degraded],
    }
    if verify:
        matrix = build_portability_matrix(model)
        trows = [r for r in matrix if r["target"] == target_fmt]
        los = [r["feature"] for r in trows if r["status"] == "lost"]
        out["round_trip"] = {
            "preserved": [r["feature"] for r in trows if r["status"] == "preserved"],
            "degraded": [r["feature"] for r in trows if r["status"] == "degraded"],
            "lost": los,
            "verdict": "recoverable" if not los else (
                "lossy" if all(l in ("target_agent", "slug", "displayname") for l in los)
                else "irreversible"),
        }
    return out


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# 技能来源抽象（多平台：local / github / skillhub）
# --------------------------------------------------------------------------- #
