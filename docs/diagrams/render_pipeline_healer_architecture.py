import shutil
import subprocess
from pathlib import Path


def build_pipeline_healer_architecture_dot() -> str:
    nodes = {
        "GH": "GitHub Actions\\nworkflow_run.completed",
        "JN": "Jenkins Bridge\\nsigned POST /webhook/jenkins",
        "WH": "Webhook Ingress\\n/github + /jenkins",
        "WF": "PipelineHealerWorkflow",
        "OR": "Orchestrator Agent",
        "LA": "Log Analyzer Agent",
        "DG": "Diagnosis Agent",
        "RM": "Remediation Agent",
        "GT": "Provider Tools / Adapters",
        "PR": "Create PR",
        "IS": "Create Issue",
        "RR": "Re-run Failed Jobs",
        "HO": "Assign-to-Agent\\nHandoff",
        "GW": "Outbound Integration\\nGateway / Receiver",
        "NT": "Notification Sinks\\nwebhook / Slack / Teams / Rocket.Chat",
        "ADP": "GHAW Adapter\\npassive mode",
        "CD": "ci-doctor\\nissue/comment findings",
        "EXT": "External diagnostics\\ncontext",
        "BF": "Backfill Sweep\\nevery 10 min",
        "ST": "Cosmos DB / PostgreSQL /\\nIn-Memory Storage",
        "EX": "Explainability Trace /\\nActivity Metadata",
        "LRN": "Learning Queue / Retrieval\\nVerification Feedback / Trust Ops",
        "UI": "Dashboard / Activities /\\nActivity Detail / Control Center / Settings",
        "API": "/api/settings* +\\n/api/settings/learning/*",
    }

    edges = [
        ("GH", "WH"),
        ("JN", "WH"),
        ("WH", "WF"),
        ("WF", "OR"),
        ("OR", "LA"),
        ("LA", "DG"),
        ("OR", "ADP"),
        ("ADP", "CD"),
        ("CD", "EXT"),
        ("EXT", "DG"),
        ("DG", "RM"),
        ("RM", "GT"),
        ("GT", "PR"),
        ("GT", "IS"),
        ("GT", "RR"),
        ("GT", "HO"),
        ("HO", "GW"),
        ("GW", "NT"),
        ("OR", "ST"),
        ("OR", "EX"),
        ("OR", "LRN"),
        ("LRN", "DG"),
        ("LRN", "RM"),
        ("BF", "ADP"),
        ("BF", "ST"),
        ("UI", "API"),
        ("API", "OR"),
        ("API", "LRN"),
        ("API", "ST"),
    ]

    lines = [
        "digraph PipelineHealerWorkflow {",
        '  rankdir="LR";',
        '  bgcolor="#1e1e1e";',
        (
            '  node [shape="box" style="filled" fillcolor="#2d2d2d" '
            'fontcolor="white" color="#4a4a4a" fontname="Helvetica"];'
        ),
        '  edge [color="#888888" fontname="Helvetica"];',
    ]

    for key, label in nodes.items():
        shape = "cylinder" if key == "ST" else "box"
        lines.append(f'  {key} [label="{label}" shape="{shape}"];')

    for start, end in edges:
        lines.append(f"  {start} -> {end};")

    lines.append("}")
    return "\n".join(lines) + "\n"


def render_with_dot(dot_file: Path, output_file: Path, fmt: str) -> None:
    subprocess.run(
        ["dot", f"-T{fmt}", str(dot_file), "-o", str(output_file)],
        check=True,
    )


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "docs" / "screens"
    output_base = output_dir / "pipeline-healer-architecture"
    dot_file = output_dir / "pipeline-healer-architecture.dot"

    output_dir.mkdir(parents=True, exist_ok=True)
    dot_contents = build_pipeline_healer_architecture_dot()
    dot_file.write_text(dot_contents, encoding="utf-8")
    print(f"Wrote source: {dot_file}")

    if shutil.which("dot") is None:
        print("Graphviz 'dot' CLI not found; skipped SVG/PNG rendering.")
        print("Install Graphviz and rerun this script.")
        print(
            "Ubuntu/WSL: sudo apt-get update && sudo apt-get install -y "
            "graphviz"
        )
        return

    render_with_dot(dot_file, output_base.with_suffix(".svg"), "svg")
    render_with_dot(dot_file, output_base.with_suffix(".png"), "png")
    print(f"Rendered: {output_base}.svg")
    print(f"Rendered: {output_base}.png")


if __name__ == "__main__":
    main()
