"""Archived development comparison; not part of the add-on."""
DETAILS = ("concise", "detailed")

def format_mirage(payload, detail):
    if detail not in DETAILS or not isinstance(payload, dict):
        raise ValueError("Invalid Mirage response or description style.")
    parts = []
    scene = payload.get("scene", "")
    if isinstance(scene, dict):
        summary = scene.get("description") or scene.get("summary") or scene.get("setting")
        scene = summary or "; ".join(str(k).replace("_", " ") + ": " + v
                                    for k, v in scene.items() if isinstance(v, str) and v.strip())
    if isinstance(scene, str) and scene.strip():
        parts.append(scene.strip())
    objects = payload.get("objects") or []
    names = [o.get("name", "") for o in objects if isinstance(o, dict)]
    names = list(dict.fromkeys(n for n in names if isinstance(n, str) and n.strip()))
    if names:
        parts.append("Visible objects: " + ", ".join(names[:6 if detail == "concise" else 12]) + ".")
    if detail == "detailed":
        regions = payload.get("text") or payload.get("reads") or []
        texts = [r.get("string") or r.get("text", "") for r in regions if isinstance(r, dict)]
        texts = [t.strip() for t in texts if isinstance(t, str) and t.strip()]
        if texts:
            parts.append("Visible text: " + "; ".join(texts[:12]) + ".")
    if not parts:
        raise ValueError("Mirage found no description. Try the SmolVLM2 profile.")
    return "\n\n".join(parts)
