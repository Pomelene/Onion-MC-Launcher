# -*- coding: utf-8 -*-
"""崩溃报告解析与定位。"""

import re
from pathlib import Path
from typing import Optional


def parse_crash(path: Path) -> dict:
    """解析崩溃报告，返回 {description, exception, java, time, suspected}。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    def field(name: str) -> str:
        m = re.search(rf"(?m)^{re.escape(name)}:\s*(.*)$", text)
        return m.group(1).strip() if m else ""

    exception = ""
    for line in text.splitlines():
        if re.match(r"\s*([\w.]+\.[A-Za-z]\w*(?:Exception|Error))\b", line):
            exception = line.strip()
            break

    suspected: list[str] = []
    in_mods = False
    for line in text.splitlines():
        if "Suspected Mods" in line:
            in_mods = True
            continue
        if in_mods:
            if line.strip().startswith("--"):
                break
            if line.strip():
                suspected.append(line.strip())

    return {
        "description": field("Description"),
        "exception": exception,
        "java": field("Java Version"),
        "time": field("Time"),
        "suspected": suspected,
    }


def summarize(path: Path) -> str:
    """生成一段适合提示用户的中文摘要。"""
    info = parse_crash(path)
    parts = [
        f"崩溃时间：{info.get('time') or '未知'}",
        f"描述：{info.get('description') or '未知'}",
    ]
    if info.get("exception"):
        parts.append(f"异常：{info['exception']}")
    if info.get("java"):
        parts.append(f"Java：{info['java']}")
    if info.get("suspected"):
        parts.append("疑似相关模组：" + "、".join(info["suspected"][:8]))
    return "\n".join(parts)


def latest_crash_report(run_dir: Path, since_ts: float = 0.0) -> Optional[Path]:
    """返回 run_dir/crash-reports 下 mtime 晚于 since_ts 的最新崩溃报告。"""
    d = run_dir / "crash-reports"
    if not d.is_dir():
        return None
    best: Optional[Path] = None
    best_mtime = since_ts
    for p in d.glob("crash-*.txt"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > best_mtime:
            best, best_mtime = p, m
    return best


# ---------------------------------------------------------------- 崩溃原因规则
#: 按优先级排列：越靠前的规则越具体。每条规则给出面向玩家的中文结论与建议。
RULES = [
    {"id": "out_of_memory", "title": "内存不足",
     "patterns": (r"java\.lang\.OutOfMemoryError", r"Java heap space",
                  r"GC overhead limit exceeded"),
     "advice": "在设置里调大最大内存；若已较大，减少模组或关闭光影。"},
    {"id": "java_too_old", "title": "Java 版本过低",
     "patterns": (r"UnsupportedClassVersionError", r"has been compiled by a more recent version"),
     "advice": "在设置里为该版本选择更高版本的 Java（或让启动器自动下载）。"},
    {"id": "java_missing", "title": "缺少 Java 运行时",
     "patterns": (r"Could not find or load main class", r"Unable to access jarfile",
                  r"JAVA_HOME"),
     "advice": "检查 Java 路径是否有效，或重新下载对应大版本的运行时。"},
    {"id": "missing_dependency", "title": "缺少前置模组",
     "patterns": (r"Missing or unsupported mandatory dependencies",
                  r"requires .* which is missing", r"缺少.*前置"),
     "advice": "按提示安装缺失的前置模组，注意版本要匹配。"},
    {"id": "duplicate_mods", "title": "模组重复",
     "patterns": (r"Duplicate mods found", r"duplicate mod", r"重复的模组"),
     "advice": "删除 mods 目录中重复的同一个模组，只保留一个版本。"},
    {"id": "mod_resolution", "title": "模组依赖冲突",
     "patterns": (r"Mod resolution failed", r"Incompatible mod set",
                  r"incompatible with", r"mod resolution encountered an error"),
     "advice": "按日志指出的模组调整版本，或暂时移除冲突模组。"},
    {"id": "mixin_apply", "title": "Mixin 注入失败",
     "patterns": (r"Mixin apply failed", r"MixinTransformerError",
                  r"Critical injection failure"),
     "advice": "通常是模组与游戏版本不匹配，更新或移除相关模组。"},
    {"id": "no_class_def", "title": "缺少类定义",
     "patterns": (r"NoClassDefFoundError", r"ClassNotFoundException"),
     "advice": "多为前置库缺失或模组损坏，重装对应模组。"},
    {"id": "glfw_error", "title": "窗口创建失败（GLFW）",
     "patterns": (r"GLFW error", r"Failed to create window", r"GLFW.*failed"),
     "advice": "更新显卡驱动；远程桌面/虚拟机环境需要硬件加速。"},
    {"id": "opengl", "title": "OpenGL 不可用",
     "patterns": (r"Pixel format not accelerated", r"does not appear to support OpenGL",
                  r"OpenGL.*not supported", r"GL_INVALID"),
     "advice": "更新显卡驱动，或安装 Mesa 软件渲染作为兜底。"},
    {"id": "native_crash", "title": "虚拟机级崩溃",
     "patterns": (r"A fatal error has been detected by the Java Runtime Environment",
                  r"EXCEPTION_ACCESS_VIOLATION", r"SIGSEGV"),
     "advice": "查看 hs_err_pid 日志；常见于显卡驱动或本地库冲突。"},
    {"id": "access_denied", "title": "文件访问被拒绝",
     "patterns": (r"AccessDeniedException", r"Access is denied", r"拒绝访问"),
     "advice": "把游戏目录移出受保护路径，或以有权限的账户运行。"},
    {"id": "file_in_use", "title": "文件被占用",
     "patterns": (r"being used by another process", r"另一个程序正在使用"),
     "advice": "关闭占用文件的程序（杀毒、同步盘、另一个游戏实例）后重试。"},
    {"id": "corrupt_jar", "title": "模组或游戏文件损坏",
     "patterns": (r"zip END header not found", r"invalid LOC header",
                  r"invalid distance too far back"),
     "advice": "用校验功能修复版本文件，或重新下载损坏的模组。"},
    {"id": "wrong_mc_version", "title": "游戏版本不匹配",
     "patterns": (r"requires minecraft 1\.", r"requires Minecraft version",
                  r"only supports Minecraft"),
     "advice": "安装与当前游戏版本对应的模组版本。"},
    {"id": "fabric_loader_old", "title": "加载器版本过低",
     "patterns": (r"Fabric Loader .* is too old", r"requires Fabric Loader"),
     "advice": "升级 Fabric/Quilt 加载器版本后重试。"},
    {"id": "forge_error", "title": "Forge 启动失败",
     "patterns": (r"forge.*failed", r"Failed to load mods", r"ModLoader"),
     "advice": "检查 Forge 版本与游戏版本是否匹配，必要时重装 Forge。"},
    {"id": "shader_error", "title": "光影或渲染出错",
     "patterns": (r"OptiFine", r"shader", r"Iris.*exception"),
     "advice": "关闭光影或更新 Iris/OptiFine 与显卡驱动。"},
    {"id": "texture_atlas", "title": "纹理图集构建失败",
     "patterns": (r"Stitching texture atlas", r"Atlas.*failed"),
     "advice": "资源包损坏或分辨率过高，移除可疑资源包。"},
    {"id": "bootstrap", "title": "启动引导失败",
     "patterns": (r"Failed to bootstrap", r"Unable to launch"),
     "advice": "重新安装该版本；若仍失败，检查 java 参数是否被额外修改。"},
    {"id": "mod_conflict", "title": "模组之间冲突",
     "patterns": (r"Mod .* requires .* but", r"conflicts with", r"incompatible"),
     "advice": "按日志逐个排除冲突模组，优先保留核心模组。"},
    {"id": "unknown", "title": "未识别的崩溃", "patterns": (),
     "advice": "查看日志尾部的 Caused by 与模组列表，或到社区检索异常关键字。"},
]


def diagnose(text: str) -> dict:
    """根据崩溃文本匹配规则，返回 {id, title, advice, matched, evidence}。"""
    sample = text or ""
    fallback = RULES[-1]
    for rule in RULES:
        for pattern in rule.get("patterns", ()):
            if re.search(pattern, sample, re.IGNORECASE):
                evidence = ""
                for line in sample.splitlines():
                    if re.search(pattern, line, re.IGNORECASE):
                        evidence = line.strip()[:300]
                        break
                return {"id": rule["id"], "title": rule["title"],
                        "advice": rule["advice"], "matched": pattern,
                        "evidence": evidence}
    return {"id": fallback["id"], "title": fallback["title"],
            "advice": fallback["advice"], "matched": "", "evidence": ""}


def diagnose_file(path: Path) -> dict:
    """读取崩溃报告并给出结论。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return diagnose("")
    result = diagnose(text)
    info = parse_crash(Path(path))
    result["description"] = info.get("description", "")
    result["suspected"] = info.get("suspected", [])
    result["exception"] = info.get("exception", "")
    return result


def redact(text):
    text=re.sub(r'(?i)(Bearer\s+)\S+',r'\1[已隐藏]',text)
    text=re.sub(r'''(?i)((?:access[_-]?token|refresh[_-]?token|client[_-]?secret|password)["']?\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)''',r'\1[已隐藏]',text)
    text=re.sub(r'(?i)(--(?:accessToken|uuid|username|xuid)\s+)(?:"[^"]*"|\S+)',r'\1[已隐藏]',text)
    return text


def reports(run_dir):
    """Combine bounded tails of game log, latest report and JVM crash log."""
    root=Path(run_dir);paths=[];latest=latest_crash_report(root)
    if latest:paths.append(latest)
    paths.append(root/'logs/latest.log')
    native=[]
    for path in root.glob('hs_err_pid*.log'):
        try:native.append((path.stat().st_mtime,path))
        except OSError:continue
    native=[p for _,p in sorted(native,key=lambda pair:pair[0],reverse=True)]
    if native:paths.append(native[0])
    findings=[]
    for path in paths:
        if not path.is_file() or path.is_symlink():continue
        try:
            from .safety import contained
            contained(path,root)
            with path.open('rb') as source:
                source.seek(max(0,path.stat().st_size-2*1024**2));sample=redact(source.read(2*1024**2).decode('utf-8','replace'))
        except OSError:continue
        # Generic mentions of a renderer or a mod are not evidence of a crash.
        for rule in RULES:
            if rule['id'] in ('unknown','shader_error','java_missing'):continue
            evidence=next((line.strip()[:500] for line in sample.splitlines() if any(re.search(p,line,re.I) for p in rule.get('patterns',()))),'')
            if evidence and not any(item['id']==rule['id'] for item in findings):
                findings.append(dict(id=rule['id'],title=rule['title'],advice=rule['advice'],evidence=evidence,source=path.name))
        for pattern,title,advice in [
            (r'Could not find or load main class|Unable to access jarfile','启动入口或类路径不可用','检查游戏文件、加载器和启动参数；这条错误本身不代表没有安装 Java。'),
            (r'Could not reserve enough space|Invalid maximum heap size','无法分配 JVM 堆内存','降低最大内存，检查是否使用 32 位 Java，并检查额外 -Xmx 参数。'),
            (r'Failed to verify username|Invalid session|Authentication servers are down','会话或认证不可用','重新登录账户并检查网络；服务器白名单或服务端认证策略需由服主管理。')]:
            evidence=next((line.strip()[:500] for line in sample.splitlines() if re.search(pattern,line,re.I)),'')
            if evidence and not any(item['title']==title for item in findings):findings.append(dict(id=title,title=title,advice=advice,evidence=evidence,source=path.name))
    return findings or [dict(id='unknown',title='没有找到可确认的常见原因',advice='诊断为规则匹配，无法证明因果关系。请结合完整日志、最近改动的模组及加载器提示排查。',evidence='',source='')]
