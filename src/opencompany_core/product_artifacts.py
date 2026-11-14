"""Deterministic, no-cost SVG product artifact generation and ZIP QA."""
from __future__ import annotations
import hashlib, json, math, re, shutil, tempfile, xml.etree.ElementTree as ET, zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

ICON_NAMES = ("signal","radar","beacon","oxygen","water","food","medical","shield","battery","power","hazard","radiation","temperature","pressure","scanner","terminal","storage","crafting","repair","navigation","airlock","vehicle","drone","comms","mission","resource","lock","keycard","warning","extraction")
PALETTE = ("#b8e6ff","#79a9c9","#f2bd74","#e88b78","#a7d6b2")

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _safe_root(root: str | Path, workflow_id: str) -> Path:
    UUID(workflow_id)
    base = Path(root).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    resolved_base = base.resolve(strict=True)
    target = resolved_base / workflow_id
    if target.exists() and target.is_symlink():
        raise ValueError("artifact workflow directory cannot be a symlink")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    resolved_target = target.resolve(strict=True)
    if resolved_target.parent != resolved_base:
        raise ValueError("artifact path escaped the configured root")
    return resolved_target

def _points(seed: int, count: int, radius: float, rotation: float = -math.pi / 2) -> str:
    values = []
    for index in range(count):
        angle = rotation + (2 * math.pi * index / count)
        wobble = 0.78 + ((seed * (index + 3)) % 7) / 30
        values.append(f"{32 + math.cos(angle)*radius*wobble:.2f},{32 + math.sin(angle)*radius*wobble:.2f}")
    return " ".join(values)

def _icon_svg(name: str, index: int) -> str:
    color, accent = PALETTE[index % len(PALETTE)], PALETTE[(index + 2) % len(PALETTE)]
    outer, inner = _points(index+11, 6+index%3, 24), _points(index+19, 4+index%4, 11, rotation=-math.pi/4)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-labelledby="title">
<title id="title">{name.replace("-", " ").title()}</title>
<g fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
<polygon points="{outer}"/><polygon points="{inner}" stroke="{accent}" stroke-width="1.8"/>
<circle cx="32" cy="32" r="{5+index%4}"/>
<path d="M32 5 V{13+index%5} M32 {51+index%5} V59 M5 32 H{13+index%5} M{51+index%5} 32 H59"/>
<path d="M{17+index%5} {17+index%4} L{25+index%3} {25+index%4} M{47-index%4} {17+index%5} L{39-index%3} {25+index%4}"/>
<path d="M{17+index%4} {47-index%3} L{25+index%3} {39-index%4} M{47-index%5} {47-index%4} L{39-index%3} {39-index%4}"/>
<path d="M24 32 H40 M32 24 V40" opacity="{0.35+(index%5)*0.1}"/>
</g><circle cx="32" cy="32" r="2.4" fill="{accent}"/></svg>'''

def _preview_svg(names: tuple[str, ...]) -> str:
    cells = []
    for i, name in enumerate(names):
        x,y = 12+(i%6)*112,12+(i//6)*112
        icon = _icon_svg(name,i).split(">",1)[1].rsplit("</svg>",1)[0]
        cells.append(f'<g transform="translate({x},{y})"><rect width="100" height="100" rx="10" fill="#111d2d" stroke="#3b5872"/><svg x="18" y="8" width="64" height="64" viewBox="0 0 64 64">{icon}</svg><text x="50" y="88" text-anchor="middle" fill="#d8e9f5" font-size="8" font-family="sans-serif">{name}</text></g>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 696 584"><title>OUTPOST icon pack contact sheet prototype</title><rect width="696" height="584" fill="#08111d"/>'+"".join(cells)+"</svg>"

def generate_outpost_pack(workflow_id: str, root: str | Path) -> dict[str, Any]:
    target = _safe_root(root, workflow_id)
    with tempfile.TemporaryDirectory(prefix=".product-rd-", dir=target.parent) as temporary:
        staging = Path(temporary) / workflow_id
        staging.mkdir()
        files = {f"icons/{name}.svg": _icon_svg(name,i).encode() for i,name in enumerate(ICON_NAMES)}
        files["preview.svg"] = _preview_svg(ICON_NAMES).encode()
        files["README.md"] = ("# OUTPOST — Sci-Fi Survival UI Icon Pack (Prototype)\n\nOriginal geometric SVG prototype generated deterministically by OpenCompany.\n\n## Contents\n- 30 individual SVG icons\n- One 6 × 5 SVG contact sheet\n- SHA-256 manifest\n- Draft license notice\n\n## Limitations\nNo PNG exports, engine import settings, accessibility review, visual polish, legal review, or demand validation have been performed.\n").encode()
        files["LICENSE-DRAFT.txt"] = b"DRAFT ONLY - NOT AN APPROVED LICENSE. No commercial-use or redistribution grant is made. Owner/legal review is required before offering this pack to customers.\n"
        manifest = {"product":"OUTPOST Sci-Fi Survival UI Icon Pack","version":"0.1.0-prototype","generator":"OpenCompany deterministic SVG generator","icon_count":len(ICON_NAMES),"grid":"6x5","formats":["SVG"],"files":{n:_sha(d) for n,d in sorted(files.items())},"limitations":["No PNG exports","No game-engine compatibility test","No independent visual-quality review","No legal or licensing review","No market-demand validation"]}
        files["manifest.json"] = json.dumps(manifest,indent=2,sort_keys=True).encode()
        for relative,data in files.items():
            destination=staging/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(data)
        archive=staging/"package.zip"
        with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
            for relative in sorted(files):
                info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                bundle.writestr(info, (staging / relative).read_bytes())
        for child in target.iterdir():
            if child.is_symlink(): raise ValueError("unexpected symlink in artifact directory")
            if child.is_file(): child.unlink()
            elif child.is_dir(): shutil.rmtree(child)
        for relative,data in files.items():
            destination=target/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(data)
        shutil.copy2(archive,target/"package.zip")
    qa=inspect_outpost_pack(target)
    names=("package.zip","preview.svg","manifest.json","README.md","LICENSE-DRAFT.txt")
    return {"workflow_id":workflow_id,"root":str(target),"artifacts":[{"name":n,"sha256":_sha((target/n).read_bytes()),"size_bytes":(target/n).stat().st_size,"download_url":f"/product-rd/workflows/{workflow_id}/artifacts/{n}"} for n in names],"qa":qa}

def inspect_outpost_pack(target: str | Path) -> dict[str, Any]:
    folder=Path(target).resolve(strict=True)
    package=folder/"package.zip"
    passed,failed=[],[]
    untested=["Visual quality requires human review","Target game-engine compatibility not tested","PNG exports and multi-resolution variants not generated","Licensing/IP review not performed","Market demand not validated"]
    if not package.is_file() or package.is_symlink():
        return {"passed_checks":passed,"failed_checks":["package.zip is missing or unsafe"],"untested_claims":untested}
    try:
        with zipfile.ZipFile(package) as bundle:
            corrupt=bundle.testzip()
            if corrupt: failed.append(f"ZIP CRC failure: {corrupt}")
            else: passed.append("ZIP archive CRC integrity")
            entries=bundle.namelist()
            names=set(entries)
            if len(entries)!=len(names):
                failed.append("ZIP contains duplicate file entries")
            if any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name for name in entries):
                failed.append("ZIP contains an unsafe path entry")
            else:
                passed.append("ZIP paths contain no absolute, traversal, or backslash entries")
            infos=bundle.infolist()
            if len(infos)>64 or sum(info.file_size for info in infos)>2_000_000 or any(info.file_size>500_000 for info in infos):
                failed.append("ZIP exceeds the product package entry or uncompressed-size limits")
            else:
                passed.append("ZIP entry count and uncompressed sizes are within limits")
            required={"README.md","LICENSE-DRAFT.txt","manifest.json","preview.svg"}
            if required.issubset(names): passed.append("Required docs and preview exist")
            else: failed.append("Required package files are missing")
            icons=sorted(n for n in names if re.fullmatch(r"icons/[a-z0-9-]+\.svg",n))
            if len(icons)==30: passed.append("Exactly 30 individual SVG icons are present")
            else: failed.append(f"Expected 30 SVG icons; found {len(icons)}")
            manifest=json.loads(bundle.read("manifest.json"))
            expected_files=set(manifest["files"])
            if expected_files != names - {"manifest.json"}:
                failed.append("Manifest file inventory does not match archive contents")
            for name,expected in manifest["files"].items():
                if name not in names or _sha(bundle.read(name))!=expected:
                    failed.append(f"Manifest hash mismatch: {name}")
            if not any("Manifest" in failure for failure in failed):
                passed.append("Manifest inventory and SHA-256 hashes match archived files")
            for name in [*icons,"preview.svg"]: ET.fromstring(bundle.read(name))
            passed.append("All SVG files parse as well-formed XML")
    except (OSError,zipfile.BadZipFile,KeyError,ValueError,ET.ParseError) as exc:
        failed.append(f"Archive or manifest validation error: {type(exc).__name__}")
    return {"passed_checks":passed,"failed_checks":failed,"untested_claims":untested}
