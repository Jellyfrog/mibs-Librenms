import io

from mibsite.progress import Progress, phase


def test_non_tty_prints_a_line_per_ten_percent():
    out = io.StringIO()
    p = Progress("pages", 200, stream=out)
    for _ in range(200):
        p.step()
    p.close()
    lines = out.getvalue().splitlines()
    assert len(lines) == 10 and lines[-1].startswith("  pages: 200/200 (100%)")


def test_phase_reports_duration():
    out = io.StringIO()
    with phase("Parsing MIBs", stream=out):
        pass
    assert out.getvalue().splitlines() == ["Parsing MIBs...", "  done in 0s"]
