# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M1.12 deterministic .blend state-dump (LOAD-parity fingerprint).
#
# Given a .blend path, open it through the real readfile paths and emit a
# deterministic JSON structural fingerprint of the resulting bpy.data state:
# per-datablock-collection counts, sorted names, and per-item structural
# fingerprints (geometry hashes, transforms, modifier/constraint settings,
# node graphs, fcurves, drivers, ...).
#
# The SAME script is designed to run under node-hosted bpy on the wasm build;
# its output must be byte-identical to the native oracle for a faithful load.
#
# DETERMINISM CONTRACT (why the output is byte-stable across builds):
#   * No floats appear in the JSON. Every numeric value is quantized to a
#     micro-unit integer  q(x) = round(x * 1_000_000). This removes all
#     dependence on float repr / printf formatting (the wasm-side risk).
#   * All collections/lists/dicts are keyed or sorted by name; nothing depends
#     on Python dict iteration order or RNA collection iteration order.
#     json.dumps(sort_keys=True) fixes key order; output is always LF-terminated.
#   * Runtime pointer-like handles are EXCLUDED: ID.session_uid, channelbag
#     slot_handle, memory addresses. Absolute filesystem paths are reduced to
#     basenames. No timestamps.
#   * Verbatim-from-file arrays (mesh coords, topology, attribute data, keyframe
#     coords, bone rest transforms) are quantized then sha256-hashed; these are
#     bit-exact reads so hashing is safe. Composed transforms (matrix_world,
#     matrix_basis) are stored as explicit micro-int arrays (not hashed) so the
#     comparison tool can apply per-element tolerance if a build ever differs by
#     a sub-micro ULP.
#
# Run:  oracle/bpy.sh --python state_dump.py -- <in.blend> <out.json>
#
# Ported for the web from (new file, no upstream original) @ fbe6228777e7

import bpy
import hashlib
import json
import os
import sys

SCHEMA_VERSION = 1
QUANT = 1_000_000

# Fixed, ordered set of bpy.data collections to fingerprint. Present-but-empty
# collections are emitted with count 0 so the schema is identical across files.
DATA_COLLECTIONS = [
    "scenes", "objects", "meshes", "curves", "metaballs", "fonts",
    "materials", "textures", "images", "lights", "cameras", "speakers",
    "armatures", "actions", "collections", "worlds", "node_groups",
    "particles", "texts", "grease_pencils",
]


# --- numeric quantization & hashing ----------------------------------------

def q(x):
    """Quantize a scalar to a micro-unit integer (removes float-repr risk)."""
    return int(round(float(x) * QUANT))


def qvec(seq):
    return [q(v) for v in seq]


def qmat(matrix):
    """Flatten a 4x4 matrix row-major into 16 micro-int values."""
    out = []
    for row in matrix:
        out.extend(q(v) for v in row)
    return out


def _hash_qints(ints):
    h = hashlib.sha256()
    CH = 4096
    for i in range(0, len(ints), CH):
        chunk = ints[i:i + CH]
        h.update((",".join(str(v) for v in chunk) + ";").encode("ascii"))
    return h.hexdigest()


def hash_qints(ints):
    return _hash_qints(ints)


def hash_floats(floats):
    return _hash_qints([q(v) for v in floats])


# --- generic RNA scalar snapshot (modifiers, constraints, ...) --------------

def rna_scalars(data):
    """Deterministic snapshot of an RNA struct's stored, writable, non-hidden
    scalar/array/enum/pointer properties. Skips readonly (derived/runtime) and
    hidden (UI-internal) props; pointers become '<id:NAME>'; floats quantized."""
    out = {}
    try:
        props = data.bl_rna.properties
    except Exception:
        return out
    for prop in props:
        pid = prop.identifier
        if pid == "rna_type":
            continue
        if getattr(prop, "is_hidden", False):
            continue
        if getattr(prop, "is_readonly", False):
            continue
        try:
            val = getattr(data, pid)
        except Exception:
            continue
        t = prop.type
        try:
            if getattr(prop, "is_array", False):
                if t == "FLOAT":
                    out[pid] = [q(x) for x in val]
                elif t == "INT":
                    out[pid] = [int(x) for x in val]
                elif t == "BOOLEAN":
                    out[pid] = [bool(x) for x in val]
                else:
                    continue
            else:
                if t == "FLOAT":
                    out[pid] = q(val)
                elif t == "INT":
                    out[pid] = int(val)
                elif t == "BOOLEAN":
                    out[pid] = bool(val)
                elif t == "ENUM":
                    out[pid] = str(val)
                elif t == "STRING":
                    out[pid] = str(val)
                elif t == "POINTER":
                    if val is None:
                        out[pid] = None
                    elif hasattr(val, "name"):
                        out[pid] = "<id:%s>" % val.name
                    else:
                        out[pid] = "<ptr>"
                else:
                    continue
        except Exception:
            continue
    return out


def id_common(idb):
    return {
        "users": int(idb.users),
        "use_fake_user": bool(idb.use_fake_user),
        "library": (idb.library.name if idb.library else None),
    }


def basename(path):
    if not path:
        return ""
    p = path.replace("\\", "/")
    return p.rsplit("/", 1)[-1]


# --- node trees -------------------------------------------------------------

def socket_default(socket):
    if socket.is_linked:
        return None
    if not hasattr(socket, "default_value"):
        return None
    dv = socket.default_value
    try:
        if isinstance(dv, (bool,)):
            return bool(dv)
        if isinstance(dv, int):
            return int(dv)
        if isinstance(dv, float):
            return q(dv)
        if isinstance(dv, str):
            return str(dv)
        # bpy_prop_array (vector/color)
        return [q(x) for x in dv]
    except Exception:
        return None


def dump_nodetree(nt):
    if nt is None:
        return None
    nodes = {}
    for node in nt.nodes:
        entry = {
            "type": node.bl_idname,
            "location": qvec(node.location),
            "inputs": sorted(s.identifier for s in node.inputs),
            "outputs": sorted(s.identifier for s in node.outputs),
        }
        defaults = {}
        for s in node.inputs:
            d = socket_default(s)
            if d is not None:
                defaults[s.identifier] = d
        if defaults:
            entry["input_defaults"] = defaults
        # Node group reference (e.g. ShaderNodeGroup.node_tree).
        subtree = getattr(node, "node_tree", None)
        if subtree is not None and hasattr(subtree, "name"):
            entry["node_tree_ref"] = subtree.name
        nodes[node.name] = entry
    links = []
    for lk in nt.links:
        links.append([
            lk.from_node.name, lk.from_socket.identifier,
            lk.to_node.name, lk.to_socket.identifier,
        ])
    links.sort()
    out = {
        "node_count": len(nt.nodes),
        "node_names": sorted(n.name for n in nt.nodes),
        "nodes": nodes,
        "link_count": len(links),
        "links": links,
    }
    # Node group interface sockets (inputs/outputs of the group itself).
    iface = getattr(nt, "interface", None)
    if iface is not None:
        socks = []
        try:
            for item in iface.items_tree:
                if getattr(item, "item_type", None) == "SOCKET":
                    socks.append({
                        "name": item.name,
                        "in_out": item.in_out,
                        "socket_type": getattr(item, "socket_type", None),
                    })
        except Exception:
            pass
        socks.sort(key=lambda s: (s["in_out"], s["name"]))
        out["interface_sockets"] = socks
    return out


# --- fcurves / actions / drivers -------------------------------------------

def dump_fcurve(fc):
    n = len(fc.keyframe_points)
    co = [0.0] * (n * 2)
    if n:
        fc.keyframe_points.foreach_get("co", co)
    return {
        "data_path": fc.data_path,
        "array_index": int(fc.array_index),
        "keyframe_count": n,
        "keyframes_hash": hash_floats(co),
        "extrapolation": fc.extrapolation,
    }


def collect_action_fcurves(action):
    fcs = []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None and len(legacy):
        fcs.extend(legacy)
    layers = getattr(action, "layers", None)
    if layers is not None:
        for layer in layers:
            for strip in layer.strips:
                for cbag in getattr(strip, "channelbags", []):
                    fcs.extend(cbag.fcurves)
    return fcs


def dump_action(action):
    fcs = [dump_fcurve(fc) for fc in collect_action_fcurves(action)]
    fcs.sort(key=lambda d: (d["data_path"], d["array_index"]))
    out = {"fcurve_count": len(fcs), "fcurves": fcs}
    out.update(id_common(action))
    slots = getattr(action, "slots", None)
    if slots is not None:
        # slot_handle is a runtime handle -> excluded; identifier is stable.
        out["slot_count"] = len(slots)
        out["slot_identifiers"] = sorted(
            getattr(s, "identifier", getattr(s, "name_display", "")) for s in slots
        )
    layers = getattr(action, "layers", None)
    if layers is not None:
        out["layer_count"] = len(layers)
    try:
        out["frame_range"] = qvec(action.frame_range)
    except Exception:
        pass
    return out


def dump_drivers(anim_data):
    drivers = []
    for dfc in anim_data.drivers:
        drv = dfc.driver
        variables = []
        for var in drv.variables:
            targets = []
            for tgt in var.targets:
                targets.append({
                    "id": (tgt.id.name if tgt.id else None),
                    "id_type": getattr(tgt, "id_type", None),
                    "data_path": getattr(tgt, "data_path", ""),
                    "transform_type": getattr(tgt, "transform_type", None),
                    "transform_space": getattr(tgt, "transform_space", None),
                    "bone_target": getattr(tgt, "bone_target", ""),
                })
            variables.append({"name": var.name, "type": var.type, "targets": targets})
        variables.sort(key=lambda v: v["name"])
        drivers.append({
            "data_path": dfc.data_path,
            "array_index": int(dfc.array_index),
            "type": drv.type,
            "expression": drv.expression,
            "use_self": bool(getattr(drv, "use_self", False)),
            "variables": variables,
        })
    drivers.sort(key=lambda d: (d["data_path"], d["array_index"]))
    return drivers


# --- per-datablock dumpers --------------------------------------------------

def dump_object(o):
    entry = {
        "type": o.type,
        "data": (o.data.name if o.data else None),
        "parent": (o.parent.name if o.parent else None),
        "parent_type": o.parent_type,
        "parent_bone": o.parent_bone,
        "rotation_mode": o.rotation_mode,
        "location": qvec(o.location),
        "rotation_euler": qvec(o.rotation_euler),
        "rotation_quaternion": qvec(o.rotation_quaternion),
        "scale": qvec(o.scale),
        "matrix_basis": qmat(o.matrix_basis),
        "matrix_parent_inverse": qmat(o.matrix_parent_inverse),
        "matrix_world": qmat(o.matrix_world),
        "empty_display_type": o.empty_display_type,
        "empty_display_size": q(o.empty_display_size),
        "instance_type": o.instance_type,
        "instance_collection": (o.instance_collection.name if o.instance_collection else None),
        "vertex_groups": [vg.name for vg in o.vertex_groups],
        "material_slots": [(ms.material.name if ms.material else None) for ms in o.material_slots],
        "modifiers": [
            {"name": m.name, "type": m.type, "props": rna_scalars(m)}
            for m in o.modifiers
        ],
        "constraints": [
            {"name": c.name, "type": c.type, "props": rna_scalars(c)}
            for c in o.constraints
        ],
    }
    entry.update(id_common(o))
    ad = o.animation_data
    if ad is not None:
        entry["action"] = (ad.action.name if ad.action else None)
        drivers = dump_drivers(ad)
        if drivers:
            entry["drivers"] = drivers
    return entry


ATTR_TYPE_READ = {
    "FLOAT": ("value", 1, True),
    "INT": ("value", 1, False),
    "INT8": ("value", 1, False),
    "BOOLEAN": ("value", 1, False),
    "FLOAT2": ("vector", 2, True),
    "FLOAT_VECTOR": ("vector", 3, True),
    "FLOAT_COLOR": ("color", 4, True),
    "BYTE_COLOR": ("color", 4, True),
    "QUATERNION": ("value", 4, True),
}


def attr_values_hash(attr):
    spec = ATTR_TYPE_READ.get(attr.data_type)
    if spec is None:
        return None
    prop, comps, is_float = spec
    n = len(attr.data)
    if n == 0:
        return hash_qints([])
    buf = [0.0 if is_float else 0] * (n * comps)
    try:
        attr.data.foreach_get(prop, buf)
    except Exception:
        return None
    return hash_floats(buf) if is_float else hash_qints([int(x) for x in buf])


def dump_mesh(me):
    nv, ne, nl, np_ = len(me.vertices), len(me.edges), len(me.loops), len(me.polygons)
    co = [0.0] * (nv * 3)
    if nv:
        me.vertices.foreach_get("co", co)
    ev = [0] * (ne * 2)
    if ne:
        me.edges.foreach_get("vertices", ev)
    lv = [0] * nl
    if nl:
        me.loops.foreach_get("vertex_index", lv)
    ls = [0] * np_
    lt = [0] * np_
    mi = [0] * np_
    if np_:
        me.polygons.foreach_get("loop_start", ls)
        me.polygons.foreach_get("loop_total", lt)
        me.polygons.foreach_get("material_index", mi)
    attributes = []
    for attr in me.attributes:
        attributes.append({
            "name": attr.name,
            "domain": attr.domain,
            "data_type": attr.data_type,
            "values_hash": attr_values_hash(attr),
        })
    attributes.sort(key=lambda a: a["name"])
    entry = {
        "vertex_count": nv,
        "edge_count": ne,
        "loop_count": nl,
        "polygon_count": np_,
        "position_hash": hash_floats(co),
        "edge_hash": hash_qints(ev),
        "loop_vertex_hash": hash_qints(lv),
        "poly_layout_hash": hash_qints(ls + lt),
        "material_index_hash": hash_qints(mi),
        "uv_layers": sorted(uv.name for uv in me.uv_layers),
        "color_attributes": sorted(ca.name for ca in me.color_attributes),
        "attributes": attributes,
        "materials": [(m.name if m else None) for m in me.materials],
    }
    entry.update(id_common(me))
    sk = me.shape_keys
    if sk is not None:
        entry["shape_keys"] = [kb.name for kb in sk.key_blocks]
    return entry


def dump_material(mat):
    entry = {
        "use_nodes": bool(mat.use_nodes),
        "diffuse_color": qvec(mat.diffuse_color),
        "metallic": q(mat.metallic),
        "roughness": q(mat.roughness),
    }
    entry.update(id_common(mat))
    if mat.use_nodes and mat.node_tree is not None:
        entry["node_tree"] = dump_nodetree(mat.node_tree)
    return entry


def dump_armature(arm):
    bones = {}
    for b in arm.bones:
        bones[b.name] = {
            "parent": (b.parent.name if b.parent else None),
            "head_local": qvec(b.head_local),
            "tail_local": qvec(b.tail_local),
            "use_connect": bool(b.use_connect),
            "use_deform": bool(b.use_deform),
            "matrix_local_hash": hash_qints(qmat(b.matrix_local)),
        }
    entry = {
        "bone_count": len(arm.bones),
        "bone_names": sorted(b.name for b in arm.bones),
        "bones": bones,
    }
    entry.update(id_common(arm))
    return entry


def dump_curve(cu):
    splines = []
    for sp in cu.splines:
        if sp.type == "BEZIER":
            pc = len(sp.bezier_points)
        else:
            pc = len(sp.points)
        splines.append({
            "type": sp.type,
            "point_count": pc,
            "use_cyclic_u": bool(sp.use_cyclic_u),
            "order_u": int(getattr(sp, "order_u", 0)),
        })
    entry = {
        "rna_type": cu.bl_rna.identifier,
        "dimensions": cu.dimensions,
        "bevel_depth": q(cu.bevel_depth),
        "extrude": q(cu.extrude),
        "resolution_u": int(cu.resolution_u),
        "spline_count": len(cu.splines),
        "splines": splines,
    }
    entry.update(id_common(cu))
    if hasattr(cu, "body"):  # TextCurve
        entry["body"] = cu.body
        entry["size"] = q(cu.size)
        entry["font"] = (cu.font.name if getattr(cu, "font", None) else None)
        entry["align_x"] = cu.align_x
        entry["align_y"] = cu.align_y
    return entry


def dump_light(la):
    entry = {
        "type": la.type,
        "energy": q(la.energy),
        "color": qvec(la.color),
        "use_nodes": bool(getattr(la, "use_nodes", False)),
    }
    for opt in ("shadow_soft_size", "spot_size", "spot_blend", "angle"):
        if hasattr(la, opt):
            entry[opt] = q(getattr(la, opt))
    entry.update(id_common(la))
    return entry


def dump_camera(cam):
    entry = {
        "type": cam.type,
        "lens": q(cam.lens),
        "sensor_width": q(cam.sensor_width),
        "sensor_height": q(cam.sensor_height),
        "clip_start": q(cam.clip_start),
        "clip_end": q(cam.clip_end),
        "shift_x": q(cam.shift_x),
        "shift_y": q(cam.shift_y),
        "ortho_scale": q(cam.ortho_scale),
    }
    entry.update(id_common(cam))
    return entry


def dump_image(img):
    entry = {
        "source": img.source,
        "size": [int(img.size[0]), int(img.size[1])],
        "depth": int(img.depth),
        "channels": int(img.channels),
        "filepath": basename(img.filepath),
        "colorspace": (img.colorspace_settings.name if img.colorspace_settings else None),
    }
    entry.update(id_common(img))
    return entry


def dump_font(font):
    entry = {"filepath": basename(font.filepath)}
    entry.update(id_common(font))
    return entry


def dump_text(txt):
    body = txt.as_string()
    entry = {
        "line_count": len(txt.lines),
        "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    entry.update(id_common(txt))
    return entry


def dump_texture(tex):
    entry = {"type": tex.type, "use_nodes": bool(getattr(tex, "use_nodes", False))}
    entry.update(id_common(tex))
    return entry


def dump_world(world):
    entry = {
        "use_nodes": bool(world.use_nodes),
        "color": qvec(world.color),
    }
    entry.update(id_common(world))
    if world.use_nodes and world.node_tree is not None:
        entry["node_tree"] = dump_nodetree(world.node_tree)
    return entry


def dump_nodegroup(ng):
    entry = dump_nodetree(ng)
    if entry is None:
        entry = {}
    entry["bl_idname"] = ng.bl_idname
    entry.update(id_common(ng))
    return entry


def collection_tree(coll):
    return {
        "objects": sorted(o.name for o in coll.objects),
        "children": {c.name: collection_tree(c) for c in coll.children},
    }


def dump_collection(coll):
    entry = {
        "objects": sorted(o.name for o in coll.objects),
        "children": sorted(c.name for c in coll.children),
        "instance_offset": qvec(coll.instance_offset),
    }
    entry.update(id_common(coll))
    return entry


def dump_scene(sc):
    entry = {
        "frame_start": int(sc.frame_start),
        "frame_end": int(sc.frame_end),
        "frame_current": int(sc.frame_current),
        "fps": int(sc.render.fps),
        "fps_base": q(sc.render.fps_base),
        "engine": sc.render.engine,
        "resolution_x": int(sc.render.resolution_x),
        "resolution_y": int(sc.render.resolution_y),
        "resolution_percentage": int(sc.render.resolution_percentage),
        "film_transparent": bool(sc.render.film_transparent),
        "world": (sc.world.name if sc.world else None),
        "camera": (sc.camera.name if sc.camera else None),
        "view_layers": sorted(vl.name for vl in sc.view_layers),
        "collection_tree": collection_tree(sc.collection),
        "compositor": (sc.compositing_node_group.name if sc.compositing_node_group else None),
        "unit_system": sc.unit_settings.system,
        "unit_scale_length": q(sc.unit_settings.scale_length),
    }
    entry.update(id_common(sc))
    return entry


COLLECTION_DUMPERS = {
    "scenes": dump_scene,
    "objects": dump_object,
    "meshes": dump_mesh,
    "materials": dump_material,
    "armatures": dump_armature,
    "curves": dump_curve,
    "lights": dump_light,
    "cameras": dump_camera,
    "images": dump_image,
    "fonts": dump_font,
    "texts": dump_text,
    "textures": dump_texture,
    "worlds": dump_world,
    "node_groups": dump_nodegroup,
    "actions": dump_action,
    "collections": dump_collection,
}


def dump_generic(idb):
    """Fallback for collections without a dedicated dumper: identity only."""
    return id_common(idb)


def build_dump(source_name):
    collections = {}
    for attr in DATA_COLLECTIONS:
        data = getattr(bpy.data, attr, None)
        if data is None:
            collections[attr] = {"count": 0, "names": [], "items": {}}
            continue
        dumper = COLLECTION_DUMPERS.get(attr, dump_generic)
        items = {}
        for idb in data:
            key = idb.name
            if idb.library:
                key = "%s [%s]" % (idb.name, idb.library.name)
            try:
                items[key] = dumper(idb)
            except Exception as exc:
                items[key] = {"_dump_error": repr(exc)}
        collections[attr] = {
            "count": len(data),
            "names": sorted(items.keys()),
            "items": items,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "quant_scale": QUANT,
        "source_name": source_name,
        "collections": collections,
    }


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(args) < 2:
        print("STATE_DUMP_USAGE state_dump.py -- <in.blend> <out.json>")
        sys.exit(2)
    blendfile = os.path.abspath(args[0])
    outpath = os.path.abspath(args[1])
    bpy.ops.wm.open_mainfile(filepath=blendfile)
    dump = build_dump(os.path.basename(blendfile))
    text = json.dumps(dump, sort_keys=True, ensure_ascii=True, indent=1)
    with open(outpath, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.write("\n")
    print("STATE_DUMP_OK", outpath, "sha256=%s" % hashlib.sha256(
        (text + "\n").encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main()
