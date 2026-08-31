# skill-doc-audit 技能工程仓库

本仓库是 SkillHub 技能 **skill-doc-audit（技能文档审计）** 的源管理与发布工程仓库，并非技能本身。正式上架版本发布于 SkillHub（slug：`skill-doc-audit`），平台综合评测 **4.7/5（优秀，最新为 v1.19.0 TRACE 评测，2026-08-31 15:36；v1.18.1 曾达 4.8/5）**。

## 仓库布局
- `src/`：技能根目录（即发布包内容）
  - `src/SKILL.md`：技能定义与用法（SkillHub 据此生成技能主页）
  - `src/scripts/audit_docs.py`：核心静态体检脚本
  - `src/references/checkers.md`：检查器明细基准
  - `src/dist/skill-doc-audit.zip`：可发布制品
- `icons/`：已选定技能图标
- `backups/`：本地编辑期快照，不进版本库，仅留本机

## 本地开发 / 自测
```bash
# 对技能源做全检查器自审计（应 0 ERROR，退出码 0）
python src/scripts/audit_docs.py --skill src --all-checks
# 多平台来源自测：克隆 GitHub 仓库并审计（应正常克隆+定位 SKILL.md+审计+清理临时目录）
python src/scripts/audit_docs.py --source github --ref JettLand/skill-doc-audit --check structure
# 多平台来源自测：经 skillhub CLI 拉取集市技能并审计
python src/scripts/audit_docs.py --source skillhub --ref skill-doc-audit --check structure
```

## 打包与发布
1. 修改 `src/` 内源文件，自测通过；
2. 重新打包制品为 `src/dist/skill-doc-audit.zip`（含 SKILL.md / audit_docs.py / checkers.md）；
3. 经 SkillHub CLI 发布：`skillhub publish src/dist/skill-doc-audit.zip --version x.y.z --changelog "..."`；
4. 提交并推送本仓库：`git add ... && git commit && git push origin main`。

## 版本摘要
<style>
.ver-table{table-layout:fixed;width:100%;border-collapse:collapse;}
.ver-table th,.ver-table td{border:1px solid #d0d0d0;padding:4px 10px;vertical-align:top;word-break:break-word;text-align:left;}
</style>
<table class="ver-table">
<colgroup><col style="width:12%"><col style="width:88%"></colgroup>
<thead>
<tr><th>版本</th><th>说明</th></tr>
</thead>
<tbody>
<tr><td>1.19.0</td><td><strong>deadcode 非 TTY 精度降级可见化 + 显式 vulture 自动安装（代码层修复 R 可靠性退步）</strong>：根因——v1.18.1 的 SKILL.md 约定修复对评测器自动化调用「不可见」，评测仍点名「deadcode 自动化精度下降无提示」。本版在代码层修复：<code>_resolve_deadcode_mode</code> 返回 <code>(mode, degraded)</code> 元组，非 TTY 且未装 vulture、或显式 vulture 但缺失、或交互超时无输入时均标记 <code>degraded=True</code>，并在报告中发出 <code>precision_degraded</code> WARN（明确标注精度降级与解决建议），使降级对自动化评测/调用方可见、不再无提示蒙混；<strong>新增 <code>_try_install_vulture()</code>：当用户显式 <code>--deadcode-mode vulture</code> 或交互选了 vulture 但环境缺库时，先尝试 <code>pip install vulture</code>，装好即用高精度、装不上才降级告警，尊重用户显式意图；<code>ast</code>/<code>skip</code> 与 ask 非 TTY 自动回退不触发安装</strong>，避免自动化场景发起意外网络请求。vulture 已装仍静默走高精度（不提示）。自身 <code>--all-checks</code> 自审 ERROR 0 / WARN 0，降级路径经模拟样本验证确实产出 <code>precision_degraded</code> 警告</td></tr>
<tr><td>1.18.1</td><td><strong>Agent 执行 deadcode 精度模式修复（非能力变更，补丁级）</strong>：根因——<code>deadcode</code> 默认 <code>ask</code> 的「询问」依赖人类 TTY 的 <code>input()</code>，Agent 经管道调用（stdin 非 TTY）时脚本静默降级为 <code>ast</code>，用户精度选择权被吞掉，与设计初衷相悖。新增「Agent 执行约定（deadcode 精度模式必须显式决策）」专节：Agent 跑 <code>--all-checks</code> 前须先探测 vulture，未装则主动用 AskUserQuestion 询问用户三选一（装 vulture/直接 ast/跳过），并以 <code>--deadcode-mode</code> 显式传入，绝不依赖 <code>ask</code> 默认；同步在「能力边界」deadcode 项与「5 分钟上手」补充 Agent 上下文提示。仅改文档与一处版本常量，无审计口径变化；自身 <code>--check doc</code> 自审 ERROR 0 / WARN 0</td></tr>
<tr><td>1.18.0</td><td><strong>回应评测误报与文档短板</strong>：①检查器误报修复——<code>hardcoded_path</code> 上下文感知（跳过表格/引用块/示例性描述行）、<code>encoding_sep</code> 排除 <code>urlopen</code>/<code>io.open</code>/<code>os.open</code> 等非文件 <code>open</code>（如 <code>--source url</code> 的 <code>urllib.request.urlopen</code> 不再误报）、<code>hardcoded_endpoint</code> 对 <code>raw.githubusercontent.com</code> 等 url 源规范主机白名单放行；自审 WARN 由 4 降至 1（仅剩审计 <code>src/</code> 目录名≠技能名的 harness 假象，部署副本不触发）；②文档增强——新增「5 分钟上手（极简路径）」「能力边界速查」「完整运行示例（真实输出+解读）」「新手常见误区 FAQ（Q6–Q8）」，并引导远端审计优先用 <code>--source url</code>（零外部 CLI、绕开 git clone 网络限制，回应国内适配性扣分）与明确 vulture 可选自动降级 ast。回归自审 ERROR 0 / WARN 1 / EXIT 0</td></tr>
<tr><td>1.17.0</td><td><strong>泛化来源 <code>--source url</code>（零依赖直抓任意 SKILL.md）</strong>：新增 <code>url</code> 来源，用标准库 <code>urllib</code> 直接抓取 SKILL.md 文本到临时目录后照常审计，无需 <code>git</code>/<code>skillhub</code> 等外部 CLI、对 OS 透明；<code>github.com</code> blob 链接自动转 <code>raw.githubusercontent.com</code>；抓取 SKILL.md 后自动补全其显式引用的 <code>scripts/</code> 与 <code>references/</code> 文件，使远程单文件技能与本地克隆等价，避免「引用缺失」刷屏（单次补全长上限 50）。审计能力格式无关，故加来源只加「抓取适配器」、不增加审计口径。<code>SOURCES</code> 注册 <code>url</code>，<code>--source</code>/<code>--ref</code> 帮助文本同步。自审 0 ERROR、WARN 维持 4 无回归；url 源实测（抓取本仓库已发布 SKILL.md + 引用补全）ERROR 0 / WARN 2 / EXIT 0</td></tr>
<tr><td>1.16.0</td><td><strong>Phase 7 ⑤落地·agentskills 全生态枢纽标注 + generic 兜底目标 + 跨平台证明</strong>：①文档标注 <code>--target agentskills</code>/<code>cursor-plugin</code> 即 Agent Skills 开放标准（agentskills.io），一次转译可被 40+ 工具（Claude Code、Cursor、Gemini CLI、Codex、Copilot、Windsurf、Kiro、OpenCode、Cline、Roo Code 等）直接消费；③新增 <code>generic</code> 降级兜底目标（<code>--target</code> 枚举扩展），仅保留 name/description，报告前置「⚠ 高损失」警告并提示优先用 agentskills/cursor-plugin；补全「跨平台可移植性证明」专节（纯标准库/零第三方依赖、无平台专属 API 实际调用、portability 自检 0 OS 级发现）。自审 0 ERROR、WARN 维持基线 2 无回归</td></tr>
<tr><td>1.15.0</td><td><strong>Phase 7 跨格式转译报告（只读预览·不落盘）</strong>：在 Phase 5/6 底座（<code>SkillModel</code>+<code>FMT_CAPS</code>/<code>EQUIV</code>+<code>build_portability_matrix</code>）之上新增 <code>--report translate --target &lt;fmt&gt;</code>，把「检测/矩阵」升级为「可预览转译方案」——但<strong>仅出报告、不落盘</strong>，守住本技能「只读扫描」立身之本。输出 frontmatter 字段映射表（保留/降级/丢失逐项标注）+ 目标 SKILL.md 脚手架预览（仅 frontmatter+标题骨架，正文散文不翻译留人工）；<code>--target</code> 支持 <code>workbuddy</code>↔<code>agentskills</code>/<code>claude-code</code>/<code>cursor-plugin</code> 双向；<code>--verify</code> 做内存往返保真（emit→re-parse→比对），依矩阵给出 <code>RECOVERABLE</code>/<code>LOSSY</code>/<code>IRREVERSIBLE</code> 结论；<code>--json</code> 附 <code>translate</code> 字段。决策：①仅报告不生成文件 ②仅 frontmatter+脚手架 ③先支持 workbuddy↔agentskills/claude-code/cursor-plugin ④<code>--verify</code> 一并纳入。自审 0 ERROR、WARN 维持基线 2 无回归</td></tr>
<tr><td>1.14.0</td><td><strong>Phase 8 生态级批量审计 + 供应链安全</strong>：<code>--ref</code> 支持逗号分隔多仓库批量审计（<code>--source github --ref a/b,c/d</code>）；<code>security</code> 新增 <code>hardcoded_endpoint</code>（硬编码远端地址，仅代码上下文才报，排除文档/注释示例 URL 与检查器自身源码误报）与 <code>dynamic_import</code>（反射式模块加载）两项供应链启发式；新增 <code>--report health</code> 生态健康度汇总（<code>--json</code> 多技能时自动附带 <code>health_summary</code>）。契合 13.4% 技能严重安全问题的行业痛点。自审 0 ERROR、WARN 维持基线 2 无回归</td></tr>
<tr><td>1.13.0</td><td><strong>Phase 6 跨格式可移植性矩阵（核心价值）</strong>：在 Phase 5 <code>SkillModel</code> 之上以开放标准 <code>agentskills</code> 为枢纽构建字段级能力映射（<code>FMT_CAPS</code>/<code>EQUIV</code>），对任意技能生成「源格式 → 各目标格式」P/D/L 损失矩阵；新增 <code>lossy_port</code> 发现（仅当技能显式声明跨 Agent 目标时触发，<code>lost</code>→WARN、<code>degraded</code>→INFO）；新增 <code>--report portability-matrix</code> 专项报告；并修复 <code>_parse_frontmatter_list</code> 内联列表 <code>[a, b]</code> 括号未剥离导致 <code>target_agent</code> 归一化失效的缺陷。自审 0 ERROR、WARN 维持基线 2 无回归</td></tr>
<tr><td>1.12.0</td><td><strong>Phase 5 跨 Agent 格式归一化内核</strong>：新增 <code>detect_format()</code> 按 frontmatter 特征推断技能格式（workbuddy/agentskills/claude-code/cursor-mdc/generic），并构建统一 <code>SkillModel</code>（name/description/fmt/platform/target_platform/target_agent/tools/license/version/extra）；<code>analyze_skill</code> 返回结果新增 <code>format</code> 与 <code>skill_model</code> 字段，供各检查器与后续 Phase 6 矩阵 / Phase 7 转译消费。格式判定「按特征推断」而非硬锁枚举，延续 v1.11.0 自由列表原则以防生态演进漏判。自审 0 ERROR、WARN 无回归</td></tr>
<tr><td>1.11.1</td><td><strong>portability #6 行为修正</strong>：移除 <code>agent_coupling</code> 对 <code>workbuddy</code> 的抑制——本 skill 自身亦开发跨平台/跨 Agent 能力，故 WorkBuddy 目标的耦合提示同样有价值，不再免报。新口径：声明跨 Agent 目标（不含 <code>workbuddy</code>，如 <code>claude-code</code>/<code>cross-agent</code>）但仍含 WorkBuddy 耦合→WARN；其余（未声明/声明含 <code>workbuddy</code>/推断 <code>workbuddy</code>）→均 INFO 提示。文档同步（SKILL.md/checkers.md/README）</td></tr>
<tr><td>1.11.0</td><td><strong>Phase 4 跨 Agent 分发 + Schema Normalizer</strong>：新增 <code>target_agent</code> 字段轴（自由列表，<code>compatibility</code> 映射，按 mcp__/<code>.workbuddy</code> 信号推断 workbuddy），#6 <code>agent_coupling</code> 可按字段抑制（声明 workbuddy）/升级（声明跨 Agent 目标仍含 WorkBuddy 耦合→WARN）；<code>deps.platform_undeclared</code> 由散文扫描升级为读取结构化 <code>target_platform</code>；Schema Normalizer 支持 Claude Code/Cursor 等开放标准技能——YAML 列表式 <code>allowed-tools</code> 解析、<code>version</code>/<code>license</code> 检查平台感知（外部平台不强制 version）。经 <code>--source github --ref anthropics/skills</code> 真实外部仓库验证无 version/license 误报洪泛</td></tr>
<tr><td>1.10.0</td><td><strong>portability 检查器组（跨平台可移植性）</strong>：新增第 7 个检查器 <code>portability</code>，已纳入 <code>--all-checks</code> 默认集；6 类全做（硬编码绝对路径 / 启动目录依赖 / 平台专属 shell / 解释器锁 / 编码分隔符假设 / Agent 平台耦合）；按 SKILL.md 的 <code>target_platform</code> 字段豁免对应平台项（fire iff 声明平台∩breaks_on 非空），全 WARN/INFO 不报 ERROR；#6 Agent 耦合为 INFO 咨询（暂不加 <code>target_agent</code> 字段，列入 Phase 4 跨 Agent 分发待办）</td></tr>
<tr><td>1.9.0</td><td><strong>多平台来源抽象（--source）</strong>：新增 <code>github</code> / <code>skillhub</code> 来源，经 <code>git clone --depth 1</code> / <code>skillhub install</code> 把远程/集市技能落到临时目录后照常审计；<code>analyze_skill</code> 核心逻辑零改动；新增 <code>--ref</code> / <code>--keep-temp</code> 参数；支持仓库内嵌套/多技能自动定位 SKILL.md</td></tr>
<tr><td>1.8.2</td><td>文档补全：SKILL.md 错误码对照表补全额 deadcode 检查器 5 个 category（<code>unused_def</code>/<code>unused_import</code>/<code>unreachable</code>/<code>orphan_asset</code>/<code>vulture</code>），与 <code>references/checkers.md</code> 权威表对齐（原速查表漏列 deadcode）；dist 同步重打包</td></tr>
<tr><td>1.8.1</td><td>交互体验改进：deadcode 询问超时 10s→30s（给用户更充裕思考时间）；<code>ask</code> 模式检测到 vulture 已安装时直接采用高精度模式、不再交互询问；修复 vulture API 调用；vulture 模式去重（不重复报 AST 项）；<code># keep</code> 白名单统一作用于 vulture 分支；vulture 异常改 stderr 告警不静默；ast/vulture 分工明确。<code>doc</code> 检查器 <code>UNKNOWN_IDENT</code> 误报修复：自动识别 frontmatter <code>allowed-tools</code>/<code>tools</code> 与文档中的 <code>mcp__*__&lt;name&gt;</code> 外部工具名并跳过，不再对 MCP/Agent 类技能刷海量误报；该检查由 ERROR 降级为 WARN（本就是「可能拼写有误」的猜测），并按标识符去重。<strong>同窗口内追加三项打磨</strong>：① 死代码 <code>unused_def</code> 增加跨文件引用感知（多文件技能「本文件定义、他文件调用」不再误报），<code>orphan_asset</code> 增加 import 模块名豁免；② 代码/配置文件扫描扩展至多语言（.ts/.tsx/.vue/.go/.rs/.java/.c/.cpp/.h/.rb/.php/.swift/.kt/.lua 等），含多语言硬编码密钥检测；③ 新增 <code>--preview</code> 检查预览（只列出将运行的检查器与将扫描的文件，不产出发现，退出码 0），缓解「参数偏多/文档偏长」的首次使用门槛</td></tr>
<tr><td>1.8.0</td><td><strong>deadcode 投产打磨</strong>：跨文件引用感知 + 多语言扫描覆盖（.ts/.go/.rs 等）；新增 <code>--preview</code> 检查预览；<code>UNKNOWN_IDENT</code> 误报修复（ERROR→WARN，按标识符去重）；文档渐进式披露（快速开始/速查表）</td></tr>
<tr><td>1.7.0</td><td>deadcode 并入 --all-checks 默认集；运行前按 --deadcode-mode 询问精度（vulture/ast/skip），超时回退 ast</td></tr>
<tr><td>1.6.0</td><td>新增 deadcode 死代码检查器（--check deadcode 启用，默认不随 --all-checks）</td></tr>
<tr><td>1.5.3</td><td>检查项中文标签（category_cn）+ 错误码对照表，报告自解释；异常处理 4.3→4.8</td></tr>
<tr><td>1.5.2</td><td>进阶用法示例 + 报错提示通俗化</td></tr>
</tbody>
</table>

> 各版本的「改动 + 验证」明细见 [CHANGELOG.md](./CHANGELOG.md)。
