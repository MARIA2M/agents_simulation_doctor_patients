#!/usr/bin/env python3
# rescore.py
# ─────────────────────────────────────────────
# 5.4 — la ablación de evidencia sobre una tanda ya corrida.
#
#   python rescore.py runs/s52-bps-1
#   python rescore.py runs/s52-bps-1 --limit 4        # prueba corta primero
#
# Reanuda: una consulta con las dos condiciones ya escritas se salta, así que
# relanzar tras un corte solo paga lo que falta. `--again` fuerza a rehacerlas.
# Una consulta que revienta se anota y la pasada sigue, como en run_batch.py.
#
# Quita del transcript las frases que el médico citó y vuelve a puntuar, en frío
# y en dos condiciones —con y sin ellas—. Si el número no se mueve, la evidencia
# era decorativa.
#
# Cuesta **dos llamadas al modelo por consulta**, así que necesita el servidor.
# Escribe `report-intact.json` y `report-ablate.json` junto al informe original,
# que no se toca.
# ─────────────────────────────────────────────

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from ahead_agent import ablation, coverage
from ahead_agent import report as report_module
from ahead_agent.config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ablación de evidencia sobre una tanda")
    parser.add_argument("batch", help="un directorio de tanda, p. ej. runs/s52-bps-1")
    parser.add_argument("--profile", default="hpc", help="perfil de ejecución")
    parser.add_argument("--limit", type=int, default=0,
                        help="solo las N primeras consultas, para probar barato")
    parser.add_argument("--again", action="store_true",
                        help="reablar las consultas que ya tienen las dos condiciones")
    return parser.parse_args()


# ── Una consulta ─────────────────────────────


def run_one(config, run_dir: Path, patient_id: str) -> dict:
    """Las dos condiciones sobre una consulta. Devuelve lo que se escribe."""
    transcript = json.loads((run_dir / "transcript.json").read_text())
    payload = json.loads((run_dir / "report.json").read_text())
    conversation = transcript.get("conversation") or []

    original = (
        report_module.parse(json.dumps(payload["report"]), patient_id)
        if payload.get("report") else None
    )
    if original is None:
        return {"run": run_dir.name, "skipped": "sin informe que ablar"}

    per_turn = ablation.cited_quotes(original, conversation)
    ablated_conversation = ablation.ablate(conversation, per_turn)
    removed = ablation.removal_size(conversation, ablated_conversation)

    results = {}
    for mode, text in ((ablation.INTACT, conversation),
                       (ablation.ABLATE, ablated_conversation)):
        scored = ablation.rescore(config, text, patient_id, mode,
                                  removed if mode == ablation.ABLATE else (0, 0))
        results[mode] = scored
        (run_dir / f"report-{mode}.json").write_text(json.dumps({
            "patient_id": patient_id,
            "mode": mode,
            "removed_turns": scored.removed_turns,
            "removed_words": scored.removed_words,
            "events": scored.events,
            "report": dataclasses.asdict(scored.report) if scored.report else None,
        }, indent=2, ensure_ascii=False) + "\n")

    moved = ablation.shifts(results[ablation.INTACT].report, results[ablation.ABLATE].report)
    return {
        "run": run_dir.name,
        "removed_turns": removed[0],
        "removed_words": removed[1],
        "shifts": moved,
    }


# ── Lo que imprime ───────────────────────────


def summary_text(results: list) -> str:
    done = [r for r in results if "shifts" in r]
    if not done:
        return "ninguna consulta pudo ablarse"

    moves = [s.moved for r in done for s in r["shifts"] if s.moved is not None]
    lost = sum(1 for r in done for s in r["shifts"] if s.lost)
    unchanged = sum(1 for m in moves if m == 0)

    lines = [
        "",
        f"{'consultas':22}{len(done):>8}",
        f"{'turnos tocados':22}{sum(r['removed_turns'] for r in done):>8}",
        f"{'palabras quitadas':22}{sum(r['removed_words'] for r in done):>8}",
        "",
        f"{'dimensiones comparables':22}{len(moves):>8}",
        f"{'  sin moverse':22}{unchanged:>8}{_share(unchanged, len(moves)):>8}",
        f"{'  desplazamiento medio':22}{_cell(_mean(abs(m) for m in moves)):>8}",
        f"{'perdieron el número':22}{lost:>8}",
    ]

    if not moves:
        lines.append("\nNada que leer: ninguna dimensión tenía número en las dos condiciones.")
    elif sum(r["removed_words"] for r in done) == 0:
        lines.append("\n! No se quitó una sola palabra: esto no es una ablación.")
    else:
        lines.append(
            "\nCuanto más cerca de cero el desplazamiento, más decorativa era la\n"
            "evidencia. Un desplazamiento grande dice que el número la estaba usando."
        )
    return "\n".join(lines)


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "-"


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _cell(value) -> str:
    return "-" if value is None else f"{value:.2f}"


def main() -> None:
    args = parse_args()
    batch_dir = Path(args.batch)
    config = load_config(args.profile)

    batch = coverage.read_batch(batch_dir)
    consultations = batch.consultations[: args.limit] if args.limit else batch.consultations

    print(f"{batch.batch_id}: ablación sobre {len(consultations)} consultas, "
          f"{len(consultations) * 2} llamadas al modelo\n")

    results, failed, skipped = [], [], 0
    for number, consultation in enumerate(consultations, start=1):
        run_dir = batch_dir / consultation.run
        print(f"[{number}/{len(consultations)}] {consultation.run}")

        # Ya ablada por un lanzamiento anterior. Sin esto, relanzar tras un corte
        # vuelve a pagar dos llamadas por consulta ya hecha.
        if not args.again and _already_done(run_dir):
            print("  ya ablada, se salta")
            skipped += 1
            continue

        # Igual que run_batch: una consulta que revienta no tumba la pasada. El
        # transporte falla en vivo (3.1), y perder 38 llamadas buenas por la 39ª
        # es perder una reserva de nodo.
        try:
            results.append(run_one(config, run_dir, consultation.patient_id))
        except Exception as error:  # noqa: BLE001
            failed.append((consultation.run, f"{type(error).__name__}: {error}"))
            print(f"  ! falló: {failed[-1][1]}")

    # Sin esto, una pasada enteramente reanudada imprime "ninguna consulta pudo
    # ablarse", que dice lo contrario de lo que pasó.
    if skipped and not results:
        print(f"\nlas {skipped} consultas ya estaban abladas. --again para rehacerlas.")
    else:
        print(summary_text(results))
        if skipped:
            print(f"\n({skipped} saltadas por estar ya abladas)")

    if failed:
        print(f"\n! {len(failed)} sin ablar:")
        for run, error in failed:
            print(f"    {run}  {error}")
        print("  Relanzar el mismo comando reanuda: lo ya escrito se salta.")
    print(f"\nescrito: {batch_dir}/*/report-intact.json y report-ablate.json")


def _already_done(run_dir: Path) -> bool:
    """Las dos condiciones escritas. Una sola no vale: la comparación necesita
    el control tanto como la ablación."""
    return all((run_dir / f"report-{mode}.json").exists() for mode in ablation.MODES)


if __name__ == "__main__":
    main()
