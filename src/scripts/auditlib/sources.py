# sources.py (拆分自 audit_docs.py)
from auditlib.core import *

def find_skill_dirs(root):
    """遍历 root，返回所有含 SKILL.md 的目录（绝对路径）。

    支持仓库内含嵌套技能（如 src/SKILL.md）或一仓库多技能。忽略目录与
    collect_code 一致（SKIP_DIRS + 点目录），避免扫入 .git / node_modules。
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if "SKILL.md" in filenames:
            out.append(os.path.abspath(dirpath))
    return out


class SkillSource:
    """将一种「来源」解析为若干本地技能目录。

    analyze_skill 只消费本地目录，故来源层只负责把远程/集市技能落到临时目录，
    再交还本地路径——核心审计逻辑零改动。

    resolve(ref, args) -> (dirs, cleanup)：
      dirs     待审计的本地技能目录列表
      cleanup  使用完毕需清理的临时目录（--keep-temp 时保留供排查）
    """

    name = "local"

    def resolve(self, ref, args):
        raise NotImplementedError


class LocalSource(SkillSource):
    name = "local"

    def resolve(self, ref, args):
        if args.all:
            if not os.path.isdir(SKILLS_ROOT):
                print("技能根目录不存在: %s" % SKILLS_ROOT, file=sys.stderr)
                sys.exit(2)
            dirs = [os.path.join(SKILLS_ROOT, d) for d in sorted(os.listdir(SKILLS_ROOT))
                    if os.path.isfile(os.path.join(SKILLS_ROOT, d, "SKILL.md"))]
            return dirs, []
        if args.skill:
            return [args.skill], []
        print("本地来源需指定 --skill <目录> 或 --all", file=sys.stderr)
        sys.exit(2)


class GithubSource(SkillSource):
    name = "github"

    def resolve(self, ref, args):
        if not ref:
            print("github 来源需通过 --ref 指定仓库（owner/repo 或 https 地址，可加 @分支）", file=sys.stderr)
            sys.exit(2)
        branch = None
        # 仅对 owner/repo 简写做 @分支 切分；完整 URL 整体作为地址
        if not ref.startswith(("http://", "https://", "git@")) and "@" in ref:
            ref, branch = ref.split("@", 1)
        if ref.startswith(("http://", "https://", "git@")):
            url = ref
        else:
            url = "https://github.com/%s.git" % ref
        tmp = tempfile.mkdtemp(prefix="skill-doc-audit-gh-")
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [url, tmp]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.CalledProcessError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            _out = (e.stderr or e.stdout or str(e)).strip().splitlines()
            msg = _out[-1] if _out else str(e)
            print("git clone 失败：%s" % msg, file=sys.stderr)
            sys.exit(2)
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            print("git clone 超时（>120s）", file=sys.stderr)
            sys.exit(2)
        dirs = find_skill_dirs(tmp)
        if not dirs:
            shutil.rmtree(tmp, ignore_errors=True)
            print("克隆仓库中未发现 SKILL.md：%s" % ref, file=sys.stderr)
            sys.exit(2)
        return dirs, [tmp]


class SkillhubSource(SkillSource):
    name = "skillhub"

    def resolve(self, ref, args):
        if not ref:
            print("skillhub 来源需通过 --ref 指定技能 slug", file=sys.stderr)
            sys.exit(2)
        # 显式解析 skillhub 可执行文件全路径：Windows 上常为 skillhub.CMD，
        # 直接传裸名时 subprocess 不会自动补扩展名，故取 which 结果（含扩展名）直传。
        bin_path = shutil.which("skillhub") or os.path.expanduser(
            os.path.join("~", ".local", "bin", "skillhub"))
        if not bin_path or not os.path.isfile(bin_path):
            print("未找到 skillhub CLI，请确认已安装并在 PATH 中", file=sys.stderr)
            sys.exit(2)
        tmp = tempfile.mkdtemp(prefix="skill-doc-audit-sh-")
        cmd = [bin_path, "install", ref, "--dir", tmp]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            shutil.rmtree(tmp, ignore_errors=True)
            print("未找到 skillhub CLI，请确认已安装并在 PATH 中", file=sys.stderr)
            sys.exit(2)
        except subprocess.CalledProcessError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            _out = (e.stderr or e.stdout or str(e)).strip().splitlines()
            msg = _out[-1] if _out else str(e)
            print("skillhub install 失败：%s" % msg, file=sys.stderr)
            sys.exit(2)
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            print("skillhub install 超时（>120s）", file=sys.stderr)
            sys.exit(2)
        dirs = find_skill_dirs(tmp)
        if not dirs:
            shutil.rmtree(tmp, ignore_errors=True)
            print("skillhub 安装后未发现 SKILL.md：%s" % ref, file=sys.stderr)
            sys.exit(2)
        return dirs, [tmp]


class UrlSource(SkillSource):
    name = "url"

    def _normalize(self, ref):
        # GitHub 网页 blob 链接 → raw 直链，便于直接抓取 SKILL.md 文本
        m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)", ref)
        if m:
            return "https://raw.githubusercontent.com/%s/%s/%s" % (m.group(1), m.group(2), m.group(3))
        return ref

    def _fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "skill-doc-audit/1.31.0"})
        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            raise ValueError("网络请求失败：%s" % e)
        if resp.status != 200:
            raise ValueError("HTTP %s" % resp.status)
        data = resp.read()
        if len(data) > MAX_FILE_SIZE:
            raise ValueError("文件过大（>%d 字节），已跳过" % MAX_FILE_SIZE)
        return data.decode("utf-8", errors="replace")

    def resolve(self, ref, args):
        if not ref:
            print("url 来源需通过 --ref 指定 SKILL.md 的 https 地址（可指向文件或所在目录）", file=sys.stderr)
            sys.exit(2)
        ref = self._normalize(ref)
        tmp = tempfile.mkdtemp(prefix="skill-doc-audit-url-")
        skill_dir = os.path.join(tmp, "skill")
        os.makedirs(skill_dir, exist_ok=True)
        # 推导 SKILL.md 文件 URL 与所在目录 base：
        #   - 直接指向 .md 文件 → base 为其父目录
        #   - 指向目录 → 尝试 <dir>/SKILL.md，base=<dir>
        if ref.rstrip("/").endswith(".md"):
            skill_url = ref
            base = ref.rstrip("/")[:ref.rstrip("/").rfind("/")]
        else:
            skill_url = ref.rstrip("/") + "/SKILL.md"
            base = ref.rstrip("/")
        try:
            content = self._fetch(skill_url)
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True)
            print("URL 抓取失败：%s" % e, file=sys.stderr)
            sys.exit(2)
        low = content.lstrip().lower()
        if low.startswith(("<!doctype", "<html")):
            shutil.rmtree(tmp, ignore_errors=True)
            print("URL 返回内容疑似 HTML 页面，非 SKILL.md 文本：%s" % skill_url, file=sys.stderr)
            sys.exit(2)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(content)
        # 相对引用补全：抓取 SKILL.md 中显式引用的 scripts/ 与 references/ 下文件，
        # 使其与本地克隆等价，避免「引用文件缺失」刷屏；单文件抓取失败则静默跳过（保留原缺失提示）。
        self._fetch_refs(content, base, skill_dir)
        return [skill_dir], [tmp]

    def _fetch_refs(self, skill_md, base, skill_dir):
        # 仅补全 scripts/ 与 references/ 下的相对引用（非 http(s)），控制规模防失控
        pat = re.compile(r'(?:scripts|references)[\\/][\w./-]+\.\w+')
        seen = set()
        for m in pat.finditer(skill_md):
            rel = m.group(0).replace("\\", "/")
            if rel in seen or len(seen) >= 50:
                continue
            seen.add(rel)
            dest = os.path.join(skill_dir, rel)
            try:
                data = self._fetch(base.rstrip("/") + "/" + rel)
            except Exception:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(data)


SOURCES = {"local": LocalSource, "github": GithubSource, "skillhub": SkillhubSource, "url": UrlSource}


def get_source(name):
    cls = SOURCES.get(name)
    if cls is None:
        print("未知来源: %s（可选: %s）" % (name, ", ".join(SOURCES)), file=sys.stderr)
        sys.exit(2)
    return cls()


