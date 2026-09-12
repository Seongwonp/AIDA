"""보고서가 **콘솔 인코딩 때문에 죽지 않는지** 본다.

보고서는 사람이 판정을 막 끝낸 뒤에 돌린다. 그 자리에서 죽으면 방금 잰 기록을
못 읽는다 — 실제로 세 번 죽었고(후보 출처 이름, 빠진 열쇠, 세션 기준 판정),
네 번째가 이것이다.

윈도우 콘솔이 cp949이거나 출력을 파일로 넘기면 `sys.stdout`의 인코딩이 cp949가
된다. 설명문에 섞인 `—`(em dash) 한 글자가 cp949에 없어서
`UnicodeEncodeError`로 죽는다. **보고 내용이 아니라 글자 하나 때문에 죽는다.**

그래서 `timing_report`는 불러들이는 순간 `errors="replace"`로 바꾼다. UTF-8
콘솔에서는 바뀌는 것이 없고(못 쓰는 글자가 없다), cp949에서는 `?`로 나오지만
보고서는 끝까지 나온다. **깨져 보이는 것이 안 나오는 것보다 낫다.**
"""
import os
import subprocess
import sys
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]


def run(code: str, encoding: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": encoding,
           "PYTHONPATH": str(EXPERIMENT)}
    return subprocess.run([sys.executable, "-c", code], cwd=EXPERIMENT,
                          env=env, capture_output=True)


def test_cp949_콘솔에서_em_dash를_찍어도_안_죽는다():
    """이 검사는 고치기 전에 `UnicodeEncodeError`로 떨어진다."""
    got = run("import timing_report, sys; sys.stdout.write('\\u2014\\n')",
              "cp949")
    assert got.returncode == 0, got.stderr.decode("utf-8", "replace")
    assert b"UnicodeEncodeError" not in got.stderr


def test_cp949에서는_바꿀_수_없는_글자만_대체된다():
    """한글은 cp949에 있으므로 그대로 나온다. 깨지는 것은 `—`뿐이다."""
    got = run("import timing_report, sys; "
              "sys.stdout.write('계획값 \\u2014 5.02초\\n')", "cp949")
    assert got.returncode == 0
    assert "계획값".encode("cp949") in got.stdout
    assert "5.02초".encode("cp949") in got.stdout


def test_UTF8_콘솔에서는_그대로_나온다():
    """대체 규칙을 켠 것이 UTF-8 출력을 망가뜨리지 않는지 확인한다."""
    got = run("import timing_report, sys; sys.stdout.write('\\u2014\\n')",
              "utf-8")
    assert got.returncode == 0
    assert "—".encode("utf-8") in got.stdout


def test_보고서_도움말이_cp949에서도_끝까지_나온다():
    """`--help`는 인자 설명을 전부 찍는다 — 설명문에 `—`가 들어 있다."""
    env = {**os.environ, "PYTHONIOENCODING": "cp949",
           "PYTHONPATH": str(EXPERIMENT)}
    got = subprocess.run([sys.executable, "timing_report.py", "--help"],
                         cwd=EXPERIMENT, env=env, capture_output=True)
    assert got.returncode == 0, got.stderr.decode("utf-8", "replace")
    assert b"--reviewed" in got.stdout       # 마지막 근처 인자까지 나왔다
