"""Markdown for studies. The pre-registration is scaffolded once from the study's
Hypothesis; the results block between the generated markers is rewritten on every run,
so a study document's numbers are never typed by hand."""

from pathlib import Path

from tennisdb.research.protocol import FindingTable, Study, StudyResult

RESULTS_START = "<!-- generated:results -->"
RESULTS_END = "<!-- /generated -->"


def render_results_block(result: StudyResult, charts_directory: str | None) -> str:
    lines = [RESULTS_START, "", f"**Verdict: {result.verdict.value.replace('_', ' ')}** — "
             f"{result.conclusion}", ""]  # fmt: skip
    for table in result.tables:
        lines += [f"#### {table.title}", "", *_render_table(table), ""]
    if charts_directory:
        lines += [
            f"![{chart.title}]({charts_directory}/{chart.key}.png)" for chart in result.charts
        ]
        lines.append("")
    return "\n".join([*lines, RESULTS_END])


def scaffold_document(study: Study) -> str:
    hypothesis = study.hypothesis
    return "\n".join([
        f"# {study.title}", "",
        "## Hypothesis", "", hypothesis.statement, "",
        "## Economic rationale", "", hypothesis.rationale, "",
        "## Pre-registered metric and threshold", "",
        f"- **Metric:** {hypothesis.metric}",
        f"- **Decision rule:** {hypothesis.threshold}", "",
        "## Sample discipline", "",
        f"- **In-sample (tuning allowed):** {hypothesis.in_sample}",
        f"- **Out-of-sample (touched once):** {hypothesis.out_of_sample}", "",
        "## Results", "", f"{RESULTS_START}\n{RESULTS_END}", "",
    ])  # fmt: skip


def write_study_document(
    study: Study, result: StudyResult, path: Path, charts_directory: str | None
) -> None:
    document = path.read_text(encoding="utf-8") if path.exists() else scaffold_document(study)
    block = render_results_block(result, charts_directory)
    start, end = document.index(RESULTS_START), document.index(RESULTS_END) + len(RESULTS_END)
    path.write_text(document[:start] + block + document[end:], encoding="utf-8")


def _render_table(table: FindingTable) -> list[str]:
    header = "| " + " | ".join(table.columns) + " |"
    divider = "|" + "|".join("---" for _ in table.columns) + "|"
    rows = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in table.rows]
    return [header, divider, *rows]
