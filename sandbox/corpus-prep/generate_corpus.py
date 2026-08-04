# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M1.12 corpus generator (ORACLE-SIDE).
#
# Authors a graduated set of synthetic .blend files, each exercising a distinct
# blenkernel readfile subsystem, by driving the native oracle's bpy and writing
# real Blender-serialized .blend files (bpy.ops.wm.save_as_mainfile). The files
# become deterministic LOAD-parity fixtures: real Blender writefile output, read
# back through the real readfile paths on both the native oracle and (later) the
# wasm build.
#
# Rationale for synthesis: the entire upstream/tests/files LFS corpus (1965
# .blend) is un-pulled pointer stubs on this checkout; the only real shipped
# .blend is upstream/release/datafiles/startup.blend. See notes/m1-corpus-prep.md.
#
# Determinism: no random values, no timestamps embedded by us. All geometry is
# generated from fixed primitive parameters or fixed formulae. Files are saved
# UNCOMPRESSED (startup.blend already exercises the zstd path).
#
# Run:  oracle/bpy.sh --python sandbox/corpus-prep/generate_corpus.py -- <out_dir>
#
# Ported for the web from (new file, no upstream original) @ fbe6228777e7

import bpy
import bmesh
import math
import os
import sys


def out_dir():
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if rest:
            return os.path.abspath(rest[0])
    return os.path.abspath("sandbox/corpus-prep/corpus")


def fresh():
    """Truly empty file: no default cube/camera/light, empty master scene."""
    bpy.ops.wm.read_homefile(use_empty=True)


def save(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=False, check_existing=False)
    print("WROTE", path)


# ---------------------------------------------------------------------------

def build_mesh_dense(path):
    """Mesh-heavy: dense grids + icosphere, multiple UV maps, color + custom
    attributes, vertex groups with formula weights. Exercises CustomData layer
    readfile across domains."""
    fresh()
    # Dense grid: 101x101 verts = 10201 verts, 10000 quad faces, 40000 loops.
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=100, y_subdivisions=100, size=2.0)
    grid = bpy.context.active_object
    grid.name = "DenseGrid"
    me = grid.data
    me.name = "DenseGridMesh"
    # Second UV map.
    me.uv_layers.new(name="UVSecond")
    # Vertex color (byte color) attribute.
    me.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
    # Custom float attribute on points, deterministic formula.
    attr = me.attributes.new(name="height", type="FLOAT", domain="POINT")
    for i, v in enumerate(me.vertices):
        attr.data[i].value = math.sin(v.co.x) * math.cos(v.co.y)
    # Vertex group with formula weights.
    vg = grid.vertex_groups.new(name="Falloff")
    for i in range(len(me.vertices)):
        vg.add([i], (i % 7) / 7.0, "REPLACE")

    # Icosphere for triangle topology.
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.0, location=(4, 0, 0))
    ico = bpy.context.active_object
    ico.name = "Ico"
    ico.data.name = "IcoMesh"
    save(path)


def build_modifiers(path):
    """Modifier stack with key props + a Boolean referencing a second object.
    Exercises ModifierData readfile and inter-object ID pointers in modifiers."""
    fresh()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.active_object
    cube.name = "ModifiedCube"

    # Cutter object for Boolean.
    bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=4.0, location=(0, 0, 0))
    cutter = bpy.context.active_object
    cutter.name = "Cutter"
    cutter.hide_render = True

    bpy.context.view_layer.objects.active = cube

    m = cube.modifiers.new(name="Subdivision", type="SUBSURF")
    m.levels = 2
    m.render_levels = 3

    m = cube.modifiers.new(name="Mirror", type="MIRROR")
    m.use_axis = (True, True, False)

    m = cube.modifiers.new(name="Array", type="ARRAY")
    m.count = 3
    m.relative_offset_displace = (1.5, 0.0, 0.0)

    m = cube.modifiers.new(name="Bevel", type="BEVEL")
    m.width = 0.05
    m.segments = 2

    m = cube.modifiers.new(name="Solidify", type="SOLIDIFY")
    m.thickness = 0.1

    m = cube.modifiers.new(name="Boolean", type="BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = cutter

    save(path)


def build_animation(path):
    """Object transform fcurves + a light energy fcurve + a driver.
    Exercises action/fcurve/keyframe and driver readfile."""
    fresh()
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    cube = bpy.context.active_object
    cube.name = "AnimCube"

    # Location keys.
    for frame, loc in ((1, (0, 0, 0)), (10, (2, 0, 1)), (20, (0, 3, 0))):
        cube.location = loc
        cube.keyframe_insert(data_path="location", frame=frame)
    # Rotation keys.
    for frame, rot in ((1, (0, 0, 0)), (15, (0, 0, math.pi)), (30, (math.pi, 0, math.pi))):
        cube.rotation_euler = rot
        cube.keyframe_insert(data_path="rotation_euler", frame=frame)
    # Scale keys.
    for frame, s in ((1, (1, 1, 1)), (25, (2, 2, 2))):
        cube.scale = s
        cube.keyframe_insert(data_path="scale", frame=frame)

    # A light with animated energy.
    bpy.ops.object.light_add(type="POINT", location=(3, 3, 3))
    light = bpy.context.active_object
    light.name = "AnimLight"
    for frame, e in ((1, 10.0), (40, 1000.0)):
        light.data.energy = e
        light.data.keyframe_insert(data_path="energy", frame=frame)

    # A driver: a second cube whose Z location is driven by AnimCube's X.
    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0, 0, 0))
    driven = bpy.context.active_object
    driven.name = "DrivenCube"
    fcurve = driven.driver_add("location", 2)
    drv = fcurve.driver
    drv.type = "SCRIPTED"
    drv.expression = "src * 2.0"
    var = drv.variables.new()
    var.name = "src"
    var.type = "TRANSFORMS"
    tgt = var.targets[0]
    tgt.id = cube
    tgt.transform_type = "LOC_X"
    tgt.transform_space = "WORLD_SPACE"

    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end = 40
    save(path)


def build_materials_nodes(path):
    """Multiple node-based materials (Principled + texture graph), a shader
    node group, multi-slot assignment with per-face material_index. Exercises
    node tree / node group / socket / link readfile."""
    fresh()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.active_object
    cube.name = "MatCube"
    me = cube.data

    # A reusable shader node group.
    grp = bpy.data.node_groups.new(name="TintGroup", type="ShaderNodeTree")
    grp.interface.new_socket(name="Fac", in_out="INPUT", socket_type="NodeSocketFloat")
    grp.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    gin = grp.nodes.new("NodeGroupInput")
    gin.location = (-200, 0)
    gout = grp.nodes.new("NodeGroupOutput")
    gout.location = (200, 0)
    ramp = grp.nodes.new("ShaderNodeValToRGB")
    ramp.location = (0, 0)
    grp.links.new(gin.outputs["Fac"], ramp.inputs["Fac"])
    grp.links.new(ramp.outputs["Color"], gout.inputs["Color"])

    def make_material(name, base_color, use_group):
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        out.location = (400, 0)
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (100, 0)
        bsdf.inputs["Base Color"].default_value = base_color
        bsdf.inputs["Roughness"].default_value = 0.4
        bsdf.inputs["Metallic"].default_value = 0.1
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        texco = nt.nodes.new("ShaderNodeTexCoord")
        texco.location = (-600, 0)
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.location = (-400, 0)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-200, 0)
        noise.inputs["Scale"].default_value = 5.0
        nt.links.new(texco.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        if use_group:
            g = nt.nodes.new("ShaderNodeGroup")
            g.node_tree = grp
            g.location = (-50, -250)
            nt.links.new(noise.outputs["Fac"], g.inputs["Fac"])
            nt.links.new(g.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            nt.links.new(noise.outputs["Color"], bsdf.inputs["Base Color"])
        return mat

    m1 = make_material("RedMat", (0.8, 0.1, 0.1, 1.0), True)
    m2 = make_material("BlueMat", (0.1, 0.1, 0.8, 1.0), False)
    m3 = make_material("GreenMat", (0.1, 0.8, 0.1, 1.0), False)
    m3.use_fake_user = True  # orphan datablock with fake user

    me.materials.append(m1)
    me.materials.append(m2)
    # Assign per-face material_index deterministically.
    for i, poly in enumerate(me.polygons):
        poly.material_index = i % 2

    save(path)


def build_curves_text(path):
    """Text object (VFont curve), bezier + nurbs curves. Exercises Curve
    datablock and VFont readfile."""
    fresh()
    bpy.ops.object.text_add()
    txt = bpy.context.active_object
    txt.name = "Label"
    txt.data.name = "LabelCurve"
    txt.data.body = "Blender Web 5.2"
    txt.data.size = 1.5
    txt.data.extrude = 0.05
    txt.data.dimensions = "3D"

    bpy.ops.curve.primitive_bezier_circle_add(radius=1.0, location=(3, 0, 0))
    bez = bpy.context.active_object
    bez.name = "BezCircle"
    bez.data.name = "BezCircleCurve"
    bez.data.bevel_depth = 0.05

    bpy.ops.curve.primitive_nurbs_path_add(location=(-3, 0, 0))
    nur = bpy.context.active_object
    nur.name = "NurbsPath"
    nur.data.name = "NurbsPathCurve"

    save(path)


def build_armature(path):
    """Armature with a fixed bone chain + a skinned mesh (Armature modifier +
    vertex groups). Exercises Armature/Bone readfile and armature deform."""
    fresh()
    bpy.ops.object.armature_add(enter_editmode=True)
    arm_obj = bpy.context.active_object
    arm_obj.name = "Rig"
    arm = arm_obj.data
    arm.name = "RigData"
    ebones = arm.edit_bones
    # Default armature has one "Bone"; rename it as root, then chain.
    root = ebones[0]
    root.name = "root"
    root.head = (0, 0, 0)
    root.tail = (0, 0, 1)
    root.roll = 0.0
    spine = ebones.new("spine")
    spine.head = (0, 0, 1)
    spine.tail = (0, 0, 2)
    spine.parent = root
    spine.use_connect = True
    head = ebones.new("head")
    head.head = (0, 0, 2)
    head.tail = (0, 0, 3)
    head.parent = spine
    head.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")

    # Skinned cylinder.
    bpy.ops.mesh.primitive_cylinder_add(radius=0.4, depth=3.0, location=(0, 0, 1.5))
    mesh_obj = bpy.context.active_object
    mesh_obj.name = "Skin"
    mesh_obj.data.name = "SkinMesh"
    for bone_name in ("root", "spine", "head"):
        mesh_obj.vertex_groups.new(name=bone_name)
    # Weight verts by height band, deterministic.
    me = mesh_obj.data
    for i, v in enumerate(me.vertices):
        z = v.co.z
        name = "root" if z < 0 else ("spine" if z < 1.0 else "head")
        mesh_obj.vertex_groups[name].add([i], 1.0, "REPLACE")
    mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = arm_obj
    mesh_obj.parent = arm_obj

    save(path)


def build_collections(path):
    """Nested collection hierarchy + a collection-instance empty. Exercises
    Collection hierarchy and object instancing (dupli) readfile."""
    fresh()
    scene = bpy.context.scene
    root = bpy.data.collections.new("Root")
    group_a = bpy.data.collections.new("GroupA")
    group_b = bpy.data.collections.new("GroupB")
    scene.collection.children.link(root)
    root.children.link(group_a)
    root.children.link(group_b)

    def add_cube(name, coll, loc):
        me = bpy.data.meshes.new(name + "Mesh")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        coll.objects.link(ob)
        return ob

    add_cube("A1", group_a, (0, 0, 0))
    add_cube("A2", group_a, (2, 0, 0))
    add_cube("B1", group_b, (0, 2, 0))

    # Collection-instance empty referencing GroupA.
    inst = bpy.data.objects.new("GroupA_Instance", None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = group_a
    inst.location = (0, -4, 0)
    group_b.objects.link(inst)
    group_a.instance_offset = (0.5, 0.0, 0.0)

    save(path)


def build_stress_mixed(path):
    """Everything at once: shared mesh (multi-user), shared material, driver,
    action, fake-user orphan, nested collections. Exercises ID linking, user
    counts, and orphan handling in readfile."""
    fresh()
    scene = bpy.context.scene

    # One shared mesh used by many objects (linked duplicates).
    shared_me = bpy.data.meshes.new("SharedMesh")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
    bm.to_mesh(shared_me)
    bm.free()

    shared_mat = bpy.data.materials.new("SharedMat")
    shared_mat.use_nodes = True
    shared_me.materials.append(shared_mat)

    coll = bpy.data.collections.new("Instances")
    scene.collection.children.link(coll)
    objs = []
    for i in range(20):
        ob = bpy.data.objects.new(f"Inst{i:02d}", shared_me)
        ob.location = (i % 5 * 2.0, i // 5 * 2.0, 0.0)
        coll.objects.link(ob)
        objs.append(ob)

    # Animate the first object.
    a = objs[0]
    for frame, loc in ((1, (0, 0, 0)), (24, (0, 0, 5))):
        a.location = loc
        a.keyframe_insert(data_path="location", frame=frame)

    # A driver on the second object driven by the first.
    fc = objs[1].driver_add("location", 2)
    d = fc.driver
    d.type = "AVERAGE"
    var = d.variables.new()
    var.name = "z"
    var.type = "TRANSFORMS"
    var.targets[0].id = objs[0]
    var.targets[0].transform_type = "LOC_Z"

    # A fake-user orphan material and mesh.
    orphan_mat = bpy.data.materials.new("OrphanMat")
    orphan_mat.use_fake_user = True
    orphan_me = bpy.data.meshes.new("OrphanMesh")
    orphan_me.use_fake_user = True

    # Two empties parented in a chain.
    e1 = bpy.data.objects.new("Pivot", None)
    e2 = bpy.data.objects.new("PivotChild", None)
    e2.parent = e1
    coll.objects.link(e1)
    coll.objects.link(e2)

    scene.frame_start = 1
    scene.frame_end = 24
    save(path)


def main():
    d = out_dir()
    os.makedirs(d, exist_ok=True)
    builders = [
        ("mesh_dense.blend", build_mesh_dense),
        ("modifiers.blend", build_modifiers),
        ("animation.blend", build_animation),
        ("materials_nodes.blend", build_materials_nodes),
        ("curves_text.blend", build_curves_text),
        ("armature.blend", build_armature),
        ("collections_instancing.blend", build_collections),
        ("stress_mixed.blend", build_stress_mixed),
    ]
    ok, fail = [], []
    for fname, fn in builders:
        path = os.path.join(d, fname)
        try:
            fn(path)
            ok.append(fname)
        except Exception as e:
            import traceback
            print("BUILD_FAIL", fname, repr(e))
            traceback.print_exc()
            fail.append(fname)
    print("CORPUS_OK", ok)
    print("CORPUS_FAIL", fail)


if __name__ == "__main__":
    main()
