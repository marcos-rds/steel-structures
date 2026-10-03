"""Camera-independent participant names in the topology's local frame."""
from collections import Counter


def participant_names(participants, span=None):
    names = {}
    for participant in participants:
        role = participant.role
        start, end = participant.axis
        delta = (end[0]-start[0]) * (1 if participant.end == "Start" else -1)
        side = " esquerda" if delta < -1e-7 else " direita" if delta > 1e-7 else ""
        if role == "END_POST" and not side and span is not None:
            side = " esquerdo" if (start[0]+end[0])/2. < span/2. else " direito"
        elif role == "END_POST":
            side = side.replace("esquerda", "esquerdo").replace("direita", "direito")
        label = {"DIAGONAL": "Diagonal", "VERTICAL": "Montante",
                 "END_POST": "Fechamento", "TOP_CHORD": "Banzo superior",
                 "BOTTOM_CHORD": "Banzo inferior"}.get(role, "Barra")
        if role in ("DIAGONAL", "END_POST") or role not in (
                "VERTICAL", "TOP_CHORD", "BOTTOM_CHORD"):
            label += side
        if participant.end == "Through":
            label = label + " (passante)" if role in ("VERTICAL", "TOP_CHORD", "BOTTOM_CHORD", "DIAGONAL", "END_POST") else "Barra passante"
        elif participant.end == "ChordBreak":
            label += " (quebra)"
        names[participant.run_key] = label
    # K diagonals can both lie on one local-X side. Distinguish their
    # local-Y branches explicitly instead of assigning arbitrary run numbers.
    for side in ("esquerda", "direita"):
        group = [p for p in participants if names[p.run_key] == "Diagonal " + side]
        dys = [(p.axis[1][1]-p.axis[0][1]) * (1 if p.end == "Start" else -1) for p in group]
        if len(group) == 2 and min(dys) < -1e-7 and max(dys) > 1e-7:
            for p in group:
                dy = (p.axis[1][1]-p.axis[0][1]) * (1 if p.end == "Start" else -1)
                names[p.run_key] += " superior" if dy > 1e-7 else " inferior"
    counts, indexes = Counter(names.values()), Counter()
    for key in sorted(names):
        label = names[key]
        indexes[label] += 1
        if counts[label] > 1:
            names[key] += " " + str(indexes[label])
    return names
