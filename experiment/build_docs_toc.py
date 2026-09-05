"""docs/21-next-plan.md에 목차를 만든다.

3454줄에 절 35개인데 목차가 없다. 그것만으로도 불편하지만, 더 위험한 건
**나중에 뒤집힌 결론을 모르고 읽는 것**이다. 이 문서는 결론이 바뀌면 원문을
지우지 않고 정정 주석을 다는 방식이라, 절 하나만 떼어 읽으면 틀린 값을
그대로 가져가게 된다.

그래서 목차에 정정 여부를 같이 적는다 — 절 본문 첫머리의 인용문("> **XX에서
정정**")을 찾아서 표시한다.
"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

p = pathlib.Path(r"C:\Users\USER\Desktop\AIDA\docs\21-next-plan.md")
s = p.read_text(encoding="utf-8")

# 이미 목차가 있으면 지우고 다시 만든다 (다시 돌려도 안전하게)
marker = "<!-- 목차 시작 -->"
end = "<!-- 목차 끝 -->"
if marker in s:
    s = s[: s.index(marker)] + s[s.index(end) + len(end):]
    s = s.lstrip("\n")

lines = s.splitlines()
entries = []
for i, line in enumerate(lines):
    if not line.startswith("# ") or line.startswith("# 21."):
        continue
    title = line[2:].strip()
    # 뒤따르는 인용문에서 정정 표시를 찾는다
    note = ""
    for j in range(i + 1, min(i + 8, len(lines))):
        m = re.match(r">\s*\*\*([A-Z]{1,2})에서 (정정|한정|부분 정정)", lines[j].strip())
        if m:
            note = f" — **{m.group(1)}에서 {m.group(2)}됨**"
            break
        if lines[j].startswith("# "):
            break
    # GitHub 앵커 규칙: 소문자, 공백은 -, 일부 기호 제거
    anchor = title.lower()
    anchor = re.sub(r"[^\w\s가-힣-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor.strip())
    entries.append(f"- [{title}](#{anchor}){note}")

toc = "\n".join([
    marker,
    "## 목차",
    "",
    "절이 35개다. **결론이 바뀐 절은 원문을 지우지 않고 정정 주석을 달았으므로,",
    "아래 표시를 보고 최신 값이 어디 있는지 먼저 확인할 것.**",
    "",
    *entries,
    "",
    end,
    "",
])

# 제목 바로 뒤에 넣는다
first = s.index("\n", s.index("# 21.")) + 1
p.write_text(s[:first] + "\n" + toc + s[first:], encoding="utf-8")
print(f"목차 {len(entries)}개 항목")
for e in entries:
    if "정정" in e or "한정" in e:
        print("  " + e.split("](")[0][3:] + e.split(")")[-1])
