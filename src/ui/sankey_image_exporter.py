"""
Standalone ECharts Sankey Diagram Exporter for Court Reports and Dossiers.
Renders the exact high-fidelity ECharts Sankey Flow Diagram from the dashboard
to a PNG image utilizing Chrome Headless Shell.
"""

from __future__ import annotations
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from src.engine.victim_tracer import VictimTraceResult


def get_chrome_headless_bin() -> Optional[str]:
    """Finds chrome-headless-shell or Chrome/Edge executable."""
    candidates = [
        Path(os.path.expanduser(r"~\AppData\Local\quarto\chrome-headless-shell\chrome-headless-shell-win64\chrome-headless-shell.exe")),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("chrome") or shutil.which("msedge")


def generate_sankey_html_page(result: VictimTraceResult, output_html_path: Path) -> Path:
    """Generates a dedicated standalone HTML page containing solely the ECharts Sankey diagram."""
    vic_accts_str = ", ".join(result.victim_accounts) if result.victim_accounts else "N/A"
    target_hub_name = f"บัญชีม้าแถว 1: {result.target_account}\n({result.target_account_name})"
    victim_node_name = f"ผู้เสียหาย: {result.victim_name}\n({vic_accts_str})"

    sankey_nodes_dict: Dict[str, Dict[str, Any]] = {
        victim_node_name: {"name": victim_node_name, "itemStyle": {"color": "#f43f5e"}},
        target_hub_name: {"name": target_hub_name, "itemStyle": {"color": "#f59e0b"}},
    }
    sankey_links: List[Dict[str, Any]] = [
        {
            "source": victim_node_name,
            "target": target_hub_name,
            "value": round(result.total_inflow_thb, 2),
        }
    ]

    for d in result.top_destinations:
        dest_name = f"ลำดับ {d.rank}: {d.bank} {d.account_no}\n{d.account_name}\n(฿{d.proportional_claim_thb:,.2f})"
        color = "#38bdf8"
        if d.recommended_action == "CCTV_INSPECTION_ATM":
            color = "#fb923c"
        elif d.recommended_action == "VASP_WALLET_FREEZE":
            color = "#c084fc"
        elif d.recommended_action == "PLATFORM_SUBPOENA_EVIDENCE":
            color = "#eab308"

        sankey_nodes_dict[dest_name] = {"name": dest_name, "itemStyle": {"color": color}}
        sankey_links.append({
            "source": target_hub_name,
            "target": dest_name,
            "value": round(d.proportional_claim_thb, 2),
        })

    if result.net_residual_buffer_thb > 0:
        buf_name = f"เงินตกค้างรอฟอก\n(฿{result.net_residual_buffer_thb:,.2f})"
        sankey_nodes_dict[buf_name] = {"name": buf_name, "itemStyle": {"color": "#64748b"}}
        sankey_links.append({
            "source": target_hub_name,
            "target": buf_name,
            "value": round(result.net_residual_buffer_thb, 2),
        })

    sankey_nodes = list(sankey_nodes_dict.values())
    nodes_json = json.dumps(sankey_nodes, ensure_ascii=False)
    links_json = json.dumps(sankey_links, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <title>Sankey Flow Diagram</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body, html {{
            margin: 0;
            padding: 0;
            width: 1600px;
            height: 800px;
            background-color: #ffffff;
            font-family: 'Sarabun', 'TH Sarabun New', Tahoma, sans-serif;
            overflow: hidden;
        }}
        #sankeyContainer {{
            width: 1560px;
            height: 760px;
            margin: 20px;
            background: #ffffff;
            border-radius: 12px;
        }}
    </style>
</head>
<body>
    <div id="sankeyContainer"></div>
    <script>
        const chart = echarts.init(document.getElementById('sankeyContainer'), null, {{ renderer: 'canvas' }});
        chart.setOption({{
            animation: false,
            series: [{{
                type: 'sankey',
                layout: 'none',
                data: {nodes_json},
                links: {links_json},
                orient: 'horizontal',
                nodeWidth: 26,
                nodeGap: 24,
                draggable: false,
                label: {{
                    color: '#0f172a',
                    fontFamily: 'Sarabun, TH Sarabun New, Tahoma',
                    fontSize: 15,
                    fontWeight: 'bold',
                    lineHeight: 20
                }},
                lineStyle: {{
                    color: 'gradient',
                    curveness: 0.5,
                    opacity: 0.5
                }}
            }}]
        }});
        window.__ECHART_READY__ = true;
    </script>
</body>
</html>"""
    output_html_path.write_text(html_content, encoding="utf-8")
    return output_html_path


def render_sankey_diagram_image(
    result: VictimTraceResult,
    output_png_path: Path,
    width: int = 1600,
    height: int = 800,
    scale_factor: int = 2,
) -> Path:
    """
    Renders the exact ECharts Sankey diagram to a high-resolution PNG image
    using chrome-headless-shell or Chrome.
    Uses --force-device-scale-factor to produce crisp, high-DPI (Retina) output.
    """
    chrome_bin = get_chrome_headless_bin()
    if not chrome_bin:
        raise RuntimeError("No headless Chrome browser found to capture ECharts diagram.")

    output_png_path.parent.mkdir(parents=True, exist_ok=True)
    temp_html = output_png_path.parent / f"__temp_sankey_{output_png_path.stem}.html"
    temp_profile_dir = output_png_path.parent / f"__temp_chrome_profile_{output_png_path.stem}"
    try:
        generate_sankey_html_page(result, temp_html)
        file_url = temp_html.resolve().as_uri()

        cmd = [
            chrome_bin,
            "--headless=new",
            f"--user-data-dir={temp_profile_dir.resolve().as_posix()}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--screenshot={output_png_path.resolve().as_posix()}",
            f"--window-size={width},{height}",
            f"--force-device-scale-factor={scale_factor}",
            "--hide-scrollbars",
            "--disable-gpu",
            file_url,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if not output_png_path.exists():
            raise RuntimeError(f"Failed to capture Sankey image. Exit code: {res.returncode}\n{res.stderr or res.stdout}")

        return output_png_path
    finally:
        if temp_html.exists():
            temp_html.unlink(missing_ok=True)
        if temp_profile_dir.exists():
            shutil.rmtree(temp_profile_dir, ignore_errors=True)
