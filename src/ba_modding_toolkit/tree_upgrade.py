# tree_upgrade.py
"""Carry Mesh and AnimationClip objects across Unity releases through their typetrees.

Mesh and AnimationClip are replaced as whole serialized bytes, which are only valid in the
layout of the Unity release that wrote them. When a mod made for one release is applied to a
bundle of another (old 2021.3 mods on the JP client that moved to Unity 6000.x), the bytes
would load without an error but give a broken mesh or clip in game. Instead, the source values
are read with the source's own typetree and written field by field into the target's layout.
Only fields the target added get a default, and only those listed below; any field that would
be lost or has no known default refuses the object.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

from UnityPy.helpers.TypeTreeHelper import FUNCTION_WRITE_MAP

from .utils import LogFunc

if TYPE_CHECKING:
    from UnityPy.environment import Environment as Env
    from UnityPy.files.ObjectReader import ObjectReader
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode

    from .models import RawAssetBytes

#: Types whose values can be carried across releases.
UPGRADE_TYPES = frozenset({"Mesh", "AnimationClip"})


class TreeUpgradeError(ValueError):
    """The source values or their stream data cannot be carried into the target."""


def _mesh_lod_info(source: dict) -> dict:
    # A single level that covers the whole mesh, as Unity writes it for meshes without LODs
    return {
        "m_LodSelectionCurve": {"m_LodSlope": 0.0, "m_LodBias": 0.0},
        "m_NumLevels": 1,
        "m_SubMeshes": [{"m_Levels": [{"m_IndexStart": 0, "m_IndexCount": 0}]} for _ in source["m_SubMeshes"]],
    }


# Fields Unity 6000.x added to Mesh and AnimationClip, with the values official 6000.x files use
_DEFAULTS = {
    ("Mesh", "m_CookingOptions"): 30,
    ("Mesh", "m_MeshLodInfo"): _mesh_lod_info,
    ("AnimationClip", "m_FloatCurves", "[]", "flags"): 0,
    ("AnimationClip", "m_PPtrCurves", "[]", "flags"): 0,
    ("AnimationClip", "m_MuscleClip", "m_Clip", "data", "m_StreamedClip", "discreteCurveCount"): 0,
    ("AnimationClip", "m_ClipBindingConstant", "genericBindings", "[]", "isIntCurve"): 0,
    ("AnimationClip", "m_ClipBindingConstant", "genericBindings", "[]", "isSerializeReferenceCurve"): 0,
}


def unity_release(version: str) -> str | None:
    """Return the major.minor of a Unity version ("2021.3.56f2" gives "2021.3"), or None."""
    match = re.match(r"^(\d+\.\d+)(?:\.|$)", version or "")
    return match[1] if match else None


def releases_differ(source: str, target: str) -> bool:
    """Whether two Unity versions belong to different releases; unknown or stripped versions never do."""
    releases = {unity_release(source), unity_release(target)}
    return len(releases) == 2 and not releases & {None, "0.0"}


def can_upgrade(kind: str, source: str | None, target: str | None) -> bool:
    """Whether values of this type can be carried from the source release to the target one."""
    return kind in UPGRADE_TYPES and source == "2021.3" and bool(target and re.fullmatch(r"6000\.\d+", target))


def shared_fields_equal(mine: Any, theirs: Any) -> bool:
    """Compare two typetrees on the fields both have; a field only one release has is left out."""
    if isinstance(mine, dict) and isinstance(theirs, dict):
        return all(shared_fields_equal(mine[key], theirs[key]) for key in mine.keys() & theirs.keys())
    if isinstance(mine, list) and isinstance(theirs, list):
        return len(mine) == len(theirs) and all(map(shared_fields_equal, mine, theirs))
    return mine == theirs


def upgrade_tree(source: dict, target: TypeTreeNode) -> dict:
    """Project source values onto the target layout, filling only the supported additions.

    Args:
        source: Object values read with the source's own typetree.
        target: Root of the target object's typetree.

    Raises:
        TreeUpgradeError: A field is missing, would be lost, or has an incompatible shape.
    """
    return _project(source, target, (target.m_Type,), source)


def _project(value: Any, node: TypeTreeNode, path: tuple[str, ...], source: dict) -> Any:
    children = node.m_Children
    if node.m_Type in FUNCTION_WRITE_MAP:
        if not isinstance(value, (dict, list, tuple)):
            return value
    elif children and children[0].m_Type == "Array":
        element = children[0].m_Children[1]
        if isinstance(value, bytes) and element.m_Type in {"UInt8", "char"}:
            return value
        if isinstance(value, (list, tuple)):
            return [_project(item, element, (*path, "[]"), source) for item in value]
    elif node.m_Type == "pair":
        if isinstance(value, (list, tuple)) and len(value) == len(children) == 2:
            return tuple(_project(item, child, (*path, child.m_Name), source) for item, child in zip(value, children))
    elif isinstance(value, dict):
        fields = {child.m_Name: child for child in children}
        for name in value.keys() - fields.keys():
            raise TreeUpgradeError(f"No target field for {'.'.join((*path, name))}")
        result = {}
        for name, child in fields.items():
            field_path = (*path, name)
            if name in value:
                field_value = value[name]
            elif field_path in _DEFAULTS:
                default = _DEFAULTS[field_path]
                field_value = default(source) if callable(default) else default
            else:
                raise TreeUpgradeError(f"No default for {'.'.join(field_path)}")
            result[name] = _project(field_value, child, field_path, source)
        return result
    raise TreeUpgradeError(f"Incompatible value at {'.'.join(path)}")


def _stream_name(stream: dict) -> str:
    return stream["path"].replace("\\", "/").rsplit("/", 1)[-1]


def _stream_range(stream: dict, payload: bytes | None) -> memoryview:
    offset, size = stream["offset"], stream["size"]
    if payload is None or offset < 0 or size < 0 or offset + size > len(payload):
        raise TreeUpgradeError("The mesh stream is missing or its byte range is invalid")
    return memoryview(payload)[offset : offset + size]


def _same_mesh_stream(source: dict, content: RawAssetBytes, target: dict, env: Env) -> bool:
    stream = source.get("m_StreamData")
    if not stream or not stream["path"]:
        return True
    name = _stream_name(stream)
    entry = env.file.files.get(_stream_name(target["m_StreamData"])) if target["m_StreamData"]["path"] else None
    try:
        return _stream_range(stream, content.companions.get(name)) == _stream_range(
            target["m_StreamData"], getattr(entry, "bytes", None)
        )
    except TreeUpgradeError:
        return False


def _install_mesh_stream(stream: dict, content: RawAssetBytes, target: ObjectReader, env: Env, log: LogFunc) -> None:
    """Attach the source's stream file to the target bundle and point the mesh at it."""
    from .asset import install_raw_content
    from .models import RawAssetBytes

    name = _stream_name(stream)
    payload = content.companions.get(name)
    _stream_range(stream, payload)
    files = env.file.files
    cab = next(cab for cab, entry in files.items() if entry is target.assets_file)
    if name in files and getattr(files[name], "bytes", None) != payload:
        # Keep the stream file the target's other meshes use under its own name
        name = f"{hashlib.sha256(payload).hexdigest()[:32]}.{name.rsplit('.', 1)[-1]}"
        if name in files and getattr(files[name], "bytes", None) != payload:
            raise TreeUpgradeError("The mesh stream file name is already in use")
    install_raw_content(RawAssetBytes(b"", {name: payload}), env, log)
    stream["path"] = f"archive:/{cab}/{name}"


def carry_across_releases(target: ObjectReader, content: RawAssetBytes, env: Env, log: LogFunc) -> bool:
    """Write a source object of another Unity release into the target through the typetrees.

    Args:
        target: The object to replace, in the target bundle.
        content: Extracted source bytes, with the source's values and Unity version.
        env: The target bundle's environment (for stream files).
        log: Receives stream file messages.

    Returns:
        False when the source equals the target on the fields both releases share (the target
        keeps its own object), True when the upgraded values were written.

    Raises:
        TreeUpgradeError: The release pair, the target's typetree or the stream data cannot be used.
    """
    kind = target.type.name
    source_release = unity_release(content.unity_version) or content.unity_version
    target_version = target.assets_file.unity_version
    target_release = unity_release(target_version) or target_version
    source = content.source_tree
    theirs = target.read_typetree()
    if shared_fields_equal(source, theirs) and (kind != "Mesh" or _same_mesh_stream(source, content, theirs, env)):
        return False
    if not can_upgrade(kind, source_release, target_release):
        raise TreeUpgradeError(f"Cannot carry {kind} from Unity {content.unity_version} to {target_version}")
    serialized = target.serialized_type
    if serialized is None or serialized.node is None:
        raise TreeUpgradeError("The target has no embedded typetree")
    tree = upgrade_tree(source, serialized.node)
    if kind == "Mesh" and (stream := tree.get("m_StreamData")) and stream["path"]:
        _install_mesh_stream(stream, content, target, env, log)
    target.save_typetree(tree)
    return True
