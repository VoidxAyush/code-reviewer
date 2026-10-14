import ast, sys, os, json, urllib.request

# ANSI Colors for instant visual appeal in Terminal!
RED, YEL, CYN, GRN, BOLD, RST = "\033[91m", "\033[93m", "\033[96m", "\033[92m", "\033[1m", "\033[0m"
SEV_COLOR = {"HIGH": RED, "MEDIUM": YEL, "LOW": CYN}

# 1. AST SCANNER: Finds 4 types of issues (Security + Code Quality)

def scan_ast(source):
    tree = ast.parse(source)
    lines = source.splitlines()
    issues = []

    for node in ast.walk(tree):
        # 1. Missing Docstring (LOW)
        if isinstance(node, ast.FunctionDef) and not ast.get_docstring(node):
            issues.append({"line": node.lineno, "sev": "LOW", "type": "missing docstring", "target": f"{node.name}()"})

        # 2. Unused Variables inside Functions (MEDIUM)
        if isinstance(node, ast.FunctionDef):
            stored = {n.id: n.lineno for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id != "_"}
            loaded = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            for var, ln in stored.items():
                if var not in loaded:
                    issues.append({"line": ln, "sev": "MEDIUM", "type": "unused variable", "target": var})

        # 3. CREATIVE RULE: Hardcoded Secret / Password Detection (HIGH)
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and any(k in t.id.lower() for k in ("password", "secret", "api_key", "token")):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        issues.append({"line": node.lineno, "sev": "HIGH", "type": "hardcoded secret", "target": t.id})

    # 4. Deeply Nested Code > 3 levels (HIGH)
    def check_depth(n, depth=0):
        if isinstance(n, (ast.If, ast.For, ast.While, ast.Try)):
            depth += 1
            if depth > 3:
                issues.append({"line": n.lineno, "sev": "HIGH", "type": f"deeply nested code (level {depth})", "target": type(n).__name__})
        for child in ast.iter_child_nodes(n):
            check_depth(child, 0 if isinstance(child, ast.FunctionDef) else depth)

    check_depth(tree)
    for i in issues:
        i["code"] = lines[i["line"] - 1].strip() if 0 < i["line"] <= len(lines) else ""
    return sorted(issues, key=lambda x: x["line"])

# 2. AI EXPLAINER (Groq / Gemini JSON + Instant Offline Backup)

def explain_with_ai(issue):
    prompt = (f"Python bug at line {issue['line']}: {issue['type']} on `{issue['target']}` (Code: `{issue['code']}`). "
              f'Return ONLY JSON: {{"why": "short plain reason", "fix": "short fix", "fixed_code": "1-line corrected python code"}}')
    try:
        if os.getenv("GROQ_API_KEY"):
            req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}", "Content-Type": "application/json"},
                data=json.dumps({"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}],
                                 "response_format": {"type": "json_object"}}).encode())
            return json.loads(json.loads(urllib.request.urlopen(req, timeout=4).read())["choices"][0]["message"]["content"])
        if os.getenv("GEMINI_API_KEY"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={os.getenv('GEMINI_API_KEY')}"
            req = urllib.request.Request(url, headers={"Content-Type": "application/json"},
                data=json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}).encode())
            return json.loads(json.loads(urllib.request.urlopen(req, timeout=4).read())["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        pass
    # Built-in smart backup if Wi-Fi or API key fails!
    backups = {
        "missing docstring": ("Readers cannot tell what this function does.", "Add a one-line docstring.", f"def {issue['target']}:\n    \"\"\"Does X.\"\"\""),
        "unused variable": (f"Variable '{issue['target']}' wastes memory and clutters code.", "Remove the unused variable.", "# Delete unused assignment"),
        "hardcoded secret": ("Exposing passwords/keys in code is a major security risk!", "Load secret from environment variables.", f"{issue['target']} = os.getenv('{issue['target'].upper()}')"),
    }
    w, f, c = backups.get(issue["type"], ("Deep nesting makes logic hard to debug.", "Use early return guard clauses.", "if not condition: return"))
    return {"why": w, "fix": f, "fixed_code": c}

# 3. RUNNER & VISUAL HEALTH BAR REPORT

def review_file(path):
    print(f"\n{BOLD}🔍 Scanning: {path}{RST}")
    try:
        issues = scan_ast(open(path, encoding="utf-8").read())
    except SyntaxError as e:
        print(f"{RED}Line {e.lineno} | [HIGH] Syntax Error: {e.msg}{RST}")
        return []

    score = max(0, 100 - sum({"HIGH": 20, "MEDIUM": 10, "LOW": 5}[i["sev"]] for i in issues))
    bar = "█" * (score // 10) + "░" * (10 - score // 10)
    grade = "A+ (Clean)" if score >= 90 else "B (Good)" if score >= 75 else "C (Needs Work)" if score >= 50 else "F (Critical)"
    print(f"{BOLD}Health: [{GRN if score>=75 else YEL if score>=50 else RED}{bar}{RST}{BOLD}] {score}/100 — Grade: {grade}{RST}\n" + "-"*55)

    report_lines = [f"FILE: {path} | Score: {score}/100 ({grade})"]
    for i in issues:
        ai = explain_with_ai(i)
        col = SEV_COLOR[i["sev"]]
        block = (f"Line {i['line']} | {col}[{i['sev']}]{RST} {BOLD}{i['type']}{RST} | {i['target']}\n"
                 f"  Why : {ai.get('why')}\n  Fix : {ai.get('fix')}\n  Code: {GRN}{ai.get('fixed_code')}{RST}\n")
        print(block, end="")
        report_lines.append(block)
    return report_lines

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    py_files = [os.path.join(r, f) for r, _, fs in os.walk(target) for f in fs if f.endswith(".py") and f != "reviewer.py"] if os.path.isdir(target) else [target]
    full_log = [line for f in py_files for line in review_file(f)]
    open("review_report.txt", "w", encoding="utf-8").write("\n".join(full_log))
    print(f"\n{CYN}✔ Saved report to review_report.txt{RST}")