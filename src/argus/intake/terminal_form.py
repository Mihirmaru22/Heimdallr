"""The brief filled in at the terminal: `osint-terminal --form`.

The same fields as the web form, asked one at a time. What each field changes is printed with it,
so nothing is answered blind. Nothing is sent anywhere; the filled-in form is saved under
`exports/briefs/` and can be re-run with `--brief <file>`.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from argus.intake.brief import DEPTHS, EVIDENCE_FLOORS, FIELDS, FormField, ResearchBrief

console = Console()


def _ask(field: FormField) -> Any:
    """Ask one field, showing what it changes, until the answer is usable."""
    console.print()
    console.print(Text(field.label, style="bold bright_green"))
    console.print(Text(f"  {field.help}", style="dim white"))
    console.print(Text(f"  What it changes: {field.effect}", style="dim cyan"))

    if field.kind == "choice":
        for name in field.choices:
            note = EVIDENCE_FLOORS.get(name) or (f"about {DEPTHS[name]} steps" if name in DEPTHS else "")
            console.print(Text(f"    {name}" + (f" — {note}" if note else ""), style="dim white"))
        return Prompt.ask("  >", choices=list(field.choices), default=str(field.default or field.choices[0]))

    if field.kind == "multi_choice":
        for i, name in enumerate(field.choices, start=1):
            console.print(Text(f"    {i}. {name}", style="dim white"))
        raw = Prompt.ask("  > numbers, comma separated (empty for none)", default="")
        picked = []
        for part in raw.replace(" ", "").split(","):
            if part.isdigit() and 1 <= int(part) <= len(field.choices):
                picked.append(field.choices[int(part) - 1])
        return picked

    if field.kind == "long_text":
        console.print(Text("  One per line. Finish with an empty line.", style="dim white"))
        lines: list[str] = []
        while True:
            line = Prompt.ask("  >", default="", show_default=False)
            if not line.strip():
                return lines
            lines.append(line.strip())

    hint = f" (e.g. {field.placeholder})" if field.placeholder else ""
    while True:
        answer = Prompt.ask(f"  >{hint}", default=str(field.default or ""), show_default=False).strip()
        if answer or not field.required:
            return answer
        console.print(Text("  This one is needed.", style="yellow"))


def fill_in_brief() -> ResearchBrief:
    """Walk the form at the terminal and return the brief, with the question shown for a check."""
    console.print(Panel(
        Text.assemble(
            ("Research brief\n", "bold bright_green"),
            ("Answer what matters and leave the rest empty. Every field changes the run; what it "
             "changes is printed with it.", "dim white"),
        ),
        border_style="bright_green",
    ))

    answers: dict[str, Any] = {}
    while True:
        for field in FIELDS:
            if field.name not in answers:
                answers[field.name] = _ask(field)
        try:
            brief = ResearchBrief.from_answers(answers)
        except ValueError as exc:
            console.print(Text(f"\n{exc}", style="bold yellow"))
            for field in FIELDS:  # ask the required ones again, keep the rest
                if field.required:
                    answers.pop(field.name, None)
            continue

        console.print()
        console.print(Panel(Text(brief.to_objective(), style="bold white"),
                            title="[bold bright_green]The question this becomes[/bold bright_green]",
                            border_style="bright_green"))
        if Prompt.ask("Start the research?", choices=["y", "n"], default="y") == "y":
            return brief
        answers = {}
