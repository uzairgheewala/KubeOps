from __future__ import annotations

from pathlib import Path

import yaml

from kubeops_pack_sdk import load_manifest, scaffold_pack, validate_manifest


def test_pack_sdk_scaffolds_loads_and_validates(tmp_path: Path) -> None:
    path = scaffold_pack(tmp_path, pack_id="example-pack", title="Example Pack", pack_kind="integration")
    manifest = load_manifest(path)
    assert manifest.pack_id == "example-pack"
    assert manifest.version == "0.1.0"
    assert manifest.pack_kind == "integration"
    assert validate_manifest(path, packs_root=tmp_path) == []


def test_pack_sdk_rejects_unknown_manifest_fields(tmp_path: Path) -> None:
    path = scaffold_pack(tmp_path, pack_id="strict-pack", title="Strict Pack", pack_kind="platform")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["arbitrary_python_entrypoint"] = "malicious.module:run"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    try:
        load_manifest(path)
    except Exception as exc:
        assert "arbitrary_python_entrypoint" in str(exc)
    else:  # pragma: no cover - strict canonical validation must reject it
        raise AssertionError("unknown executable field was accepted")
