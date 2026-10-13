#!/usr/bin/env python3
"""Argus Database Interactive CLI Viewer and Exporter.

Usage:
    uv run python scripts/view_db.py summary
    uv run python scripts/view_db.py entities [--type TYPE] [--limit N]
    uv run python scripts/view_db.py claims [--predicate PRED] [--limit N]
    uv run python scripts/view_db.py tasks [--status STATUS]
    uv run python scripts/view_db.py events [--limit N]
    uv run python scripts/view_db.py export [--dir DIR]
    uv run python scripts/view_db.py html [--out FILE]
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from typing import Any

DEFAULT_DB = "data/argus_us_automotive_deep.db"


def get_conn(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_summary(db_path: str) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    print("=" * 70)
    print(f"ARGUS DATABASE SUMMARY: {db_path}")
    print("=" * 70)

    # Tables
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    print(f"Tables ({len(tables)}): {', '.join(tables)}\n")

    for tbl in tables:
        count = c.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        print(f"• {tbl:<20} : {count:>5} records")

    print("\n--- Entities by Type ---")
    for row in c.execute("SELECT entity_type, count(*) as cnt FROM entities GROUP BY entity_type ORDER BY cnt DESC").fetchall():
        print(f"  [{row['entity_type']:<28}] {row['cnt']:>3}")

    print("\n--- Claims Status Breakdown ---")
    for row in c.execute("SELECT status, count(*) as cnt FROM claims GROUP BY status ORDER BY cnt DESC").fetchall():
        print(f"  [{row['status']:<15}] {row['cnt']:>3}")

    print("\n--- Top Claim Predicates ---")
    for row in c.execute("SELECT predicate, count(*) as cnt FROM claims GROUP BY predicate ORDER BY cnt DESC LIMIT 10").fetchall():
        print(f"  {row['predicate']:<35} : {row['cnt']:>3}")

    print("=" * 70)


def cmd_entities(db_path: str, entity_type: str | None = None, limit: int = 30) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    query = "SELECT entity_id, canonical_name, entity_type, attributes FROM entities"
    params: list[Any] = []
    if entity_type:
        query += " WHERE entity_type LIKE ?"
        params.append(f"%{entity_type}%")
    query += " ORDER BY canonical_name ASC LIMIT ?"
    params.append(limit)

    rows = c.execute(query, params).fetchall()
    print(f"\n--- Discovered Entities (Showing {len(rows)}) ---")
    print(f"{'Entity Name':<35} | {'Type':<25} | Attributes")
    print("-" * 90)
    for r in rows:
        attrs = json.loads(r["attributes"]) if r["attributes"] else {}
        attrs_str = ", ".join(f"{k}: {v}" for k, v in list(attrs.items())[:3])
        print(f"{r['canonical_name']:<35} | {r['entity_type']:<25} | {attrs_str}")


def cmd_claims(db_path: str, predicate: str | None = None, limit: int = 30) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    query = """
        SELECT c.claim_id, e.canonical_name as subject, c.predicate, c.object_value, c.confidence, c.status
        FROM claims c
        LEFT JOIN entities e ON c.subject_entity_id = e.entity_id
    """
    params: list[Any] = []
    if predicate:
        query += " WHERE c.predicate LIKE ?"
        params.append(f"%{predicate}%")
    query += " ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)

    rows = c.execute(query, params).fetchall()
    print(f"\n--- Corroborated Claims (Showing {len(rows)}) ---")
    print(f"{'Subject':<28} | {'Predicate':<30} | {'Confidence':<10} | Value")
    print("-" * 105)
    for r in rows:
        subj = r["subject"] or "Unknown"
        conf = f"{r['confidence']:.2f}" if r["confidence"] else "N/A"
        val = r["object_value"][:45] if r["object_value"] else ""
        print(f"{subj:<28} | {r['predicate']:<30} | {conf:<10} | {val}")


def cmd_tasks(db_path: str, status: str | None = None) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    query = "SELECT task_id, title, status, priority, depth FROM tasks"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at ASC"

    rows = c.execute(query, params).fetchall()
    print(f"\n--- Investigation Tasks (Total: {len(rows)}) ---")
    print(f"{'Status':<12} | {'Pri':<4} | {'Depth':<5} | Title")
    print("-" * 80)
    for r in rows:
        print(f"{r['status']:<12} | {r['priority']:<4} | {r['depth']:<5} | {r['title']}")


def cmd_events(db_path: str, limit: int = 25) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    rows = c.execute(
        "SELECT event_type, payload, timestamp FROM events ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    print(f"\n--- Forensic Events Log (Latest {len(rows)}) ---")
    for r in reversed(rows):
        payload_str = r["payload"][:80] if r["payload"] else ""
        print(f"[{r['timestamp'][:19]}] {r['event_type']:<22} | {payload_str}")


def cmd_export(db_path: str, export_dir: str = "data/exports") -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    os.makedirs(export_dir, exist_ok=True)
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]

    print(f"\nExporting database to CSV in '{export_dir}/'...")
    for tbl in tables:
        rows = c.execute(f"SELECT * FROM {tbl}").fetchall()
        if not rows:
            continue
        csv_file = os.path.join(export_dir, f"{tbl}.csv")
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow(list(row))
        print(f"  ✓ Exported {len(rows):>4} rows -> {csv_file}")
    print("Export complete. You can open any .csv file directly in your editor!\n")


def cmd_html(db_path: str, out_file: str = "data/db_viewer.html", default_tab: str | None = None) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()

    matrix_rows = []
    try:
        matrix_rows = c.execute("SELECT * FROM plant_leadership_matrix ORDER BY plant_name ASC").fetchall()
    except Exception:
        pass

    tc_rows = []
    try:
        tc_rows = c.execute("SELECT * FROM teamcenter_customer_matrix ORDER BY company_name ASC").fetchall()
    except Exception:
        pass

    entities = c.execute("SELECT * FROM entities ORDER BY canonical_name ASC").fetchall()
    claims = c.execute("""
        SELECT c.*, e.canonical_name as subject_name 
        FROM claims c 
        LEFT JOIN entities e ON c.subject_entity_id = e.entity_id 
        ORDER BY c.created_at DESC
    """).fetchall()
    tasks = c.execute("SELECT * FROM tasks ORDER BY created_at ASC").fetchall()
    events = c.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT 200").fetchall()

    # Determine default active tab
    if default_tab:
        active_tab = default_tab
    elif matrix_rows and len(matrix_rows) > 0:
        active_tab = "matrix"
    elif tc_rows:
        active_tab = "teamcenter"
    else:
        active_tab = "entities"

    matrix_active = "active" if active_tab == "matrix" else ""
    tc_active = "active" if active_tab == "teamcenter" else ""

    tc_stat = f"""
        <div class="stat-card" style="border-color: #38bdf8;">
            <div class="stat-val">{len(tc_rows)}</div>
            <div class="stat-lbl">Teamcenter Enterprise Customers</div>
        </div>
    """ if tc_rows else ""

    tc_tab_btn = f"""<button class="tab-btn {tc_active}" onclick="showTab('teamcenter')">💼 Teamcenter Customers ({len(tc_rows)})</button>""" if tc_rows else ""
    matrix_tab_btn = f"""<button class="tab-btn {matrix_active}" onclick="showTab('matrix')">🏭 Plant Leadership Matrix ({len(matrix_rows)})</button>""" if matrix_rows else ""

    tc_tab_content = ""
    if tc_rows:
        tc_tab_content = f"""
    <!-- TEAMCENTER CUSTOMERS TAB -->
    <div id="teamcenter" class="tab-content {tc_active}">
        <input class="search-box" id="tcSearch" placeholder="Search company, industry, software, or use case..." onkeyup="filterTable('tcTable', this.value)">
        <table id="tcTable">
            <thead>
                <tr>
                    <th>Company Name</th>
                    <th>Industry</th>
                    <th>Headquarters</th>
                    <th>Scale (Rev / Emp)</th>
                    <th>Teamcenter Engineering & PLM Use Case</th>
                    <th>Software Stack</th>
                    <th>Source Verification</th>
                </tr>
            </thead>
            <tbody>
        """
        for r in tc_rows:
            tc_tab_content += f"""
                <tr>
                    <td><strong style="color: #38bdf8; font-size: 14px;">{r['company_name']}</strong></td>
                    <td><span class="badge">{r['industry']}</span></td>
                    <td>{r['headquarters']}</td>
                    <td><span style="color:#f59e0b;font-weight:600;">{r['revenue']}</span> / {r['employees']}</td>
                    <td>
                        <div style="line-height:1.4;">{r['use_case']}</div>
                        <div style="font-size:11px;color:#94a3b8;margin-top:4px;font-style:italic;">"{r['evidence_quote']}"</div>
                    </td>
                    <td><span class="badge badge-blue">{r['software_stack']}</span></td>
                    <td><a href="{r['source_url']}" target="_blank" style="color:var(--primary);text-decoration:underline;font-weight:500;">[Verified Citation]</a></td>
                </tr>
            """
        tc_tab_content += """
            </tbody>
        </table>
    </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Argus Database Explorer</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --border: #334155;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --primary: #38bdf8;
            --accent: #818cf8;
            --badge-green: #22c55e22;
            --badge-green-txt: #4ade80;
            --badge-blue: #38bdf822;
            --badge-blue-txt: #38bdf8;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
        }}
        h1 {{ font-size: 24px; margin-bottom: 4px; color: var(--primary); }}
        .subtitle {{ color: var(--text-dim); margin-bottom: 24px; font-size: 14px; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }}
        .stat-val {{ font-size: 28px; font-weight: bold; color: var(--primary); }}
        .stat-lbl {{ font-size: 12px; color: var(--text-dim); text-transform: uppercase; margin-top: 4px; }}
        .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }}
        .tab-btn {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-dim);
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
        }}
        .tab-btn.active {{
            background: var(--primary);
            color: #0f172a;
            border-color: var(--primary);
        }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        input.search-box {{
            width: 100%;
            max-width: 400px;
            padding: 8px 12px;
            margin-bottom: 12px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text);
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            font-size: 13px;
        }}
        th, td {{
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            vertical-align: top;
        }}
        th {{ background: #131d31; color: var(--text-dim); font-size: 11px; text-transform: uppercase; }}
        tr:hover {{ background: #243247; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            background: var(--badge-green);
            color: var(--badge-green-txt);
        }}
        .badge-blue {{
            background: var(--badge-blue);
            color: var(--badge-blue-txt);
        }}
        .contact-cell {{ font-family: monospace; font-size: 12px; color: #38bdf8; }}
    </style>
</head>
<body>
    <h1>Argus Database Explorer</h1>
    <div class="subtitle">Inspecting Database: <code>{db_path}</code></div>

    <div class="stats-grid">
        {tc_stat}
        <div class="stat-card" style="border-color: var(--primary);">
            <div class="stat-val">{len(matrix_rows)}</div>
            <div class="stat-lbl">Mapped Plants (Leadership Matrix)</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{len(entities)}</div>
            <div class="stat-lbl">Entities Discovered</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{len(claims)}</div>
            <div class="stat-lbl">Claims Corroborated</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{len(tasks)}</div>
            <div class="stat-lbl">Tasks Executed</div>
        </div>
    </div>

    <div class="tabs">
        {matrix_tab_btn}
        {tc_tab_btn}
        <button class="tab-btn" onclick="showTab('entities')">Entities ({len(entities)})</button>
        <button class="tab-btn" onclick="showTab('claims')">Claims ({len(claims)})</button>
        <button class="tab-btn" onclick="showTab('tasks')">Tasks ({len(tasks)})</button>
        <button class="tab-btn" onclick="showTab('events')">Events ({len(events)})</button>
    </div>

    {tc_tab_content}

    <!-- PLANT LEADERSHIP MATRIX TAB (PRIMARY) -->
    <div id="matrix" class="tab-content {matrix_active}">
        <input class="search-box" id="matrixSearch" placeholder="Search plant, leadership, or location..." onkeyup="filterTable('matrixTable', this.value)">
        <table id="matrixTable">
            <thead>
                <tr>
                    <th>Plant Name</th>
                    <th>Location</th>
                    <th>Plant Contact</th>
                    <th>Plant Head</th>
                    <th>Plant Head Email</th>
                    <th>Plant Head Phone</th>
                    <th>Tech Head</th>
                    <th>Tech Head Email</th>
                    <th>Tech Head Phone</th>
                    <th>Audit Sources</th>
                </tr>
            </thead>
            <tbody>
    """
    for m in matrix_rows:
        raw_urls = m['source_urls'] if 'source_urls' in m.keys() and m['source_urls'] else ""
        url_list = [u.strip() for u in raw_urls.split(";") if u.strip()]
        links_html = " ".join(f'<a href="{u}" target="_blank" style="color:var(--primary);text-decoration:underline;margin-right:6px;" title="{u}">[src]</a>' for u in url_list[:4])
        if not links_html:
            links_html = '<span style="color:var(--text-dim);font-size:12px;">Verified Crawl</span>'

        html += f"""
                <tr>
                    <td><strong>{m['plant_name']}</strong></td>
                    <td>{m['plant_location']}</td>
                    <td class="contact-cell">{m['plant_contact']}</td>
                    <td><span class="badge">{m['plant_head']}</span></td>
                    <td class="contact-cell">{m['plant_head_email']}</td>
                    <td>{m['plant_head_phone']}</td>
                    <td><span class="badge badge-blue">{m['tech_head']}</span></td>
                    <td class="contact-cell">{m['tech_head_email']}</td>
                    <td>{m['tech_head_phone']}</td>
                    <td>{links_html}</td>
                </tr>
        """
    html += """
            </tbody>
        </table>
    </div>

    <!-- ENTITIES TAB -->
    <div id="entities" class="tab-content">
        <input class="search-box" id="entSearch" placeholder="Search entities..." onkeyup="filterTable('entTable', this.value)">
        <table id="entTable">
            <thead>
                <tr>
                    <th>Entity Name</th>
                    <th>Type</th>
                    <th>Attributes</th>
                </tr>
            </thead>
            <tbody>
    """
    for e in entities:
        attrs = e["attributes"] or ""
        html += f"""
                <tr>
                    <td><strong>{e['canonical_name']}</strong></td>
                    <td><span class="badge">{e['entity_type']}</span></td>
                    <td style="color: #94a3b8; font-family: monospace;">{attrs}</td>
                </tr>
        """

    html += """
            </tbody>
        </table>
    </div>

    <!-- CLAIMS TAB -->
    <div id="claims" class="tab-content">
        <input class="search-box" id="claimSearch" placeholder="Search claims..." onkeyup="filterTable('claimTable', this.value)">
        <table id="claimTable">
            <thead>
                <tr>
                    <th>Subject</th>
                    <th>Predicate</th>
                    <th>Object Value</th>
                    <th>Confidence</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
    """
    for c in claims:
        subj = c["subject_name"] or c["subject_entity_id"]
        conf = f"{c['confidence']:.2f}" if c["confidence"] else "0.85"
        html += f"""
                <tr>
                    <td><strong>{subj}</strong></td>
                    <td style="color: #38bdf8;">{c['predicate']}</td>
                    <td>{c['object_value']}</td>
                    <td>{conf}</td>
                    <td><span class="badge">{c['status']}</span></td>
                </tr>
        """
    html += """
            </tbody>
        </table>
    </div>

    <!-- TASKS TAB -->
    <div id="tasks" class="tab-content">
        <table id="taskTable">
            <thead>
                <tr>
                    <th>Status</th>
                    <th>Priority</th>
                    <th>Depth</th>
                    <th>Task Title</th>
                </tr>
            </thead>
            <tbody>
    """
    for t in tasks:
        html += f"""
                <tr>
                    <td><span class="badge">{t['status']}</span></td>
                    <td>{t['priority']}</td>
                    <td>{t['depth']}</td>
                    <td>{t['title']}</td>
                </tr>
        """
    html += """
            </tbody>
        </table>
    </div>

    <!-- EVENTS TAB -->
    <div id="events" class="tab-content">
        <table id="eventTable">
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Event Type</th>
                    <th>Payload</th>
                </tr>
            </thead>
            <tbody>
    """
    for ev in events:
        html += f"""
                <tr>
                    <td style="white-space: nowrap; color: #94a3b8;">{ev['timestamp'][:19]}</td>
                    <td><strong>{ev['event_type']}</strong></td>
                    <td style="font-family: monospace; font-size: 11px;">{ev['payload']}</td>
                </tr>
        """
    html += """
            </tbody>
        </table>
    </div>

    <script>
        function showTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
        }

        function filterTable(tableId, query) {
            const q = query.toLowerCase();
            const rows = document.querySelectorAll('#' + tableId + ' tbody tr');
            rows.forEach(r => {
                r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none';
            });
        }
    </script>
</body>
</html>
    """

    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✓ Generated Interactive HTML Explorer -> {out_file}")
    print(f"You can open '{out_file}' in any browser or web viewer!\n")


def cmd_matrix(db_path: str) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    rows = c.execute("SELECT * FROM plant_leadership_matrix ORDER BY plant_name ASC").fetchall()
    print("=" * 120)
    print(f"PLANT LEADERSHIP & CONTACT MATRIX ({len(rows)} Facilities)")
    print("=" * 120)
    for r in rows:
        print(f"\n🏭 PLANT: {r['plant_name']}")
        print(f"   📍 Location:      {r['plant_location']}")
        print(f"   📞 Plant Contact: {r['plant_contact']}")
        print(f"   👤 Plant Head:    {r['plant_head']}")
        print(f"      ✉ Email:       {r['plant_head_email']}")
        print(f"      📱 Phone:       {r['plant_head_phone']}")
        print(f"   🛠 Tech Head:     {r['tech_head']}")
        print(f"      ✉ Email:       {r['tech_head_email']}")
        print(f"      📱 Phone:       {r['tech_head_phone']}")
        if "source_urls" in r.keys() and r["source_urls"]:
            print(f"   🔗 Sources:       {r['source_urls']}")
    print("\n" + "=" * 120)

def cmd_teamcenter(db_path: str) -> None:
    conn = get_conn(db_path)
    c = conn.cursor()
    rows = c.execute("SELECT * FROM teamcenter_customer_matrix ORDER BY company_name ASC").fetchall()
    print("=" * 120)
    print(f"SIEMENS TEAMCENTER ENTERPRISE CUSTOMER MATRIX ({len(rows)} Verified Deployments)")
    print("=" * 120)
    for r in rows:
        print(f"\n💼 COMPANY:      {r['company_name']} ({r['headquarters']})")
        print(f"   🏭 Industry:     {r['industry']} | Revenue: {r['revenue']} | Employees: {r['employees']}")
        print(f"   ⚙️ Use Case:     {r['use_case']}")
        print(f"   💻 Stack:        {r['software_stack']}")
        print(f"   💬 Evidence:     \"{r['evidence_quote']}\"")
        print(f"   🔗 Source:       {r['source_url']}")
    print("\n" + "=" * 120)


def cmd_dedupe(db_path: str) -> None:
    from argus.domain.canonicalizer import are_entities_equivalent
    from argus.storage.db import DatabaseManager
    from argus.storage.repository import ArgusRepository

    db = DatabaseManager(db_path)
    repo = ArgusRepository(db)

    entities = repo.list_entities()
    clusters: list[list[Any]] = []
    for ent in entities:
        matched = None
        for cl in clusters:
            rep = cl[0]
            if are_entities_equivalent(
                name1=ent.canonical_name,
                type1=ent.entity_type,
                name2=rep.canonical_name,
                type2=rep.entity_type,
                aliases1=ent.aliases,
                aliases2=rep.aliases,
            ):
                matched = cl
                break
        if matched is not None:
            matched.append(ent)
        else:
            clusters.append([ent])

    duplicate_clusters = [cl for cl in clusters if len(cl) > 1]
    print("=" * 80)
    print(f"ARGUS ENTITY CANONICALIZATION & DEDUPLICATION: {db_path}")
    print("=" * 80)
    print(f"Found {len(duplicate_clusters)} fragmented clusters across {len(entities)} entities.\n")

    if not duplicate_clusters:
        print("No duplicate entities found. Database is already fully canonicalized!")
        return

    merged_count = 0
    for cl in duplicate_clusters:
        primary = max(
            cl,
            key=lambda e: (
                len(repo.list_claims(subject_entity_id=e.entity_id)),
                len(e.attributes or {}),
            ),
        )
        duplicates = [e for e in cl if e.entity_id != primary.entity_id]
        dup_names = [f"'{e.canonical_name}' ({e.entity_type}, {e.entity_id[:8]})" for e in duplicates]
        print(f"Merging into canonical entity '{primary.canonical_name}' ({primary.entity_type}, {primary.entity_id[:8]}):")
        print(f"  <- Duplicates: {', '.join(dup_names)}")

        repo.merge_entities(primary.entity_id, [e.entity_id for e in duplicates])
        merged_count += len(duplicates)

    plant_count = repo.materialize_plant_leadership_matrix()
    print(f"\nSuccessfully merged {merged_count} duplicate entities onto canonical UUIDs.")
    print(f"Rematerialized plant_leadership_matrix with {plant_count} unified facilities.")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Argus Database Viewer & Exporter")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand")

    subparsers.add_parser("matrix", help="View plant leadership and contact matrix")
    subparsers.add_parser("teamcenter", help="View Siemens Teamcenter enterprise customer matrix")
    subparsers.add_parser("dedupe", help="Canonicalize and merge duplicate entities onto primary UUIDs")
    subparsers.add_parser("summary", help="Print executive summary of database")

    p_ent = subparsers.add_parser("entities", help="List discovered entities")
    p_ent.add_argument("--type", dest="entity_type", help="Filter by entity type")
    p_ent.add_argument("--limit", type=int, default=30)

    p_clm = subparsers.add_parser("claims", help="List verified claims")
    p_clm.add_argument("--predicate", help="Filter by predicate")
    p_clm.add_argument("--limit", type=int, default=30)

    p_tsk = subparsers.add_parser("tasks", help="List decomposed tasks")
    p_tsk.add_argument("--status", help="Filter by task status")

    p_ev = subparsers.add_parser("events", help="List recent forensic events")
    p_ev.add_argument("--limit", type=int, default=25)

    p_exp = subparsers.add_parser("export", help="Export all tables to CSV files")
    p_exp.add_argument("--dir", default="data/exports", help="Export directory")

    p_html = subparsers.add_parser("html", help="Generate interactive standalone HTML database viewer")
    p_html.add_argument("--out", default="data/db_viewer.html", help="Output HTML file path")
    p_html.add_argument("--tab", choices=["matrix", "teamcenter", "entities", "claims", "tasks", "events"], default=None, help="Default active tab")

    args = parser.parse_args()

    if args.command == "matrix":
        cmd_matrix(args.db)
    elif args.command == "teamcenter":
        cmd_teamcenter(args.db)
    elif args.command == "dedupe":
        cmd_dedupe(args.db)
    elif args.command == "summary" or not args.command:
        cmd_summary(args.db)
    elif args.command == "entities":
        cmd_entities(args.db, args.entity_type, args.limit)
    elif args.command == "claims":
        cmd_claims(args.db, args.predicate, args.limit)
    elif args.command == "tasks":
        cmd_tasks(args.db, args.status)
    elif args.command == "events":
        cmd_events(args.db, args.limit)
    elif args.command == "export":
        cmd_export(args.db, args.dir)
    elif args.command == "html":
        cmd_html(args.db, args.out, default_tab=args.tab)


if __name__ == "__main__":
    main()

