# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Render one controlled Cycles edge-attribution variant.

The loaded .blend is changed only in memory.  Each invocation writes a display
PNG, a 32-bit multilayer EXR, and a compact settings receipt.
"""

import argparse
import json
import os
from pathlib import Path
import sys

import bpy


def script_arguments():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(arguments)


def ensure_cycles():
    scene = bpy.context.scene
    try:
        scene.render.engine = "CYCLES"
        return "preregistered"
    except TypeError:
        pass

    addon_parent = os.environ.get("M6_CYCLES_ADDON_PARENT")
    if addon_parent and addon_parent not in sys.path:
        sys.path.insert(0, addon_parent)
    import cycles

    cycles.register()
    scene.render.engine = "CYCLES"
    return "addon-registered"


def named_object(name):
    obj = bpy.context.scene.objects.get(name)
    if obj is None:
        raise RuntimeError(f"required object is missing: {name}")
    return obj


def principled_node(obj):
    material = obj.active_material
    if material is None or material.node_tree is None:
        raise RuntimeError(f"{obj.name} has no node material")
    nodes = [node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"]
    if len(nodes) != 1:
        raise RuntimeError(f"expected one Principled node on {obj.name}, got {len(nodes)}")
    return material, nodes[0]


def set_alpha_one(obj):
    material, node = principled_node(obj)
    socket = node.inputs["Alpha"]
    removed = len(socket.links)
    for link in list(socket.links):
        material.node_tree.links.remove(link)
    socket.default_value = 1.0
    return f"alpha_links_removed={removed}"


def replace_with_diffuse(obj):
    material, principled = principled_node(obj)
    tree = material.node_tree
    outputs = [node for node in tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial"]
    if len(outputs) != 1:
        raise RuntimeError(f"expected one material output on {obj.name}, got {len(outputs)}")
    surface = outputs[0].inputs["Surface"]
    for link in list(surface.links):
        tree.links.remove(link)

    diffuse = tree.nodes.new("ShaderNodeBsdfDiffuse")
    base = principled.inputs["Base Color"]
    if base.is_linked:
        tree.links.new(base.links[0].from_socket, diffuse.inputs["Color"])
    else:
        diffuse.inputs["Color"].default_value = base.default_value
    diffuse.inputs["Roughness"].default_value = principled.inputs["Roughness"].default_value
    tree.links.new(diffuse.outputs["BSDF"], surface)
    return "sphere_surface=diffuse"


def apply_variant(variant, scene):
    sphere = named_object("Sphere")
    if variant == "baseline":
        return "unchanged"
    if variant == "film_transparent":
        scene.render.film_transparent = True
        return "film_transparent=true"
    if variant == "alpha_one":
        return set_alpha_one(sphere)
    if variant == "samples_1":
        scene.cycles.samples = 1
        return "samples=1"
    if variant == "samples_100":
        scene.cycles.samples = 100
        return "samples=100"
    if variant == "sampling_tabulated_sobol":
        previous = scene.cycles.sampling_pattern
        scene.cycles.sampling_pattern = "TABULATED_SOBOL"
        return f"sampling_pattern={previous}->TABULATED_SOBOL"
    if variant == "sampling_blue_noise_pure":
        previous = scene.cycles.sampling_pattern
        scene.cycles.sampling_pattern = "BLUE_NOISE"
        return f"sampling_pattern={previous}->BLUE_NOISE"
    if variant == "adaptive_off":
        previous = scene.cycles.use_adaptive_sampling
        scene.cycles.use_adaptive_sampling = False
        return f"use_adaptive_sampling={previous}->False"
    if variant == "light_tree_off":
        previous = scene.cycles.use_light_tree
        scene.cycles.use_light_tree = False
        return f"use_light_tree={previous}->False"
    if variant == "sampling_tabulated_adaptive_off":
        scene.cycles.sampling_pattern = "TABULATED_SOBOL"
        scene.cycles.use_adaptive_sampling = False
        return "sampling_pattern=TABULATED_SOBOL; use_adaptive_sampling=False"
    if variant == "sampling_tabulated_light_tree_off":
        scene.cycles.sampling_pattern = "TABULATED_SOBOL"
        scene.cycles.use_light_tree = False
        return "sampling_pattern=TABULATED_SOBOL; use_light_tree=False"
    if variant == "legacy_triplet":
        scene.cycles.sampling_pattern = "TABULATED_SOBOL"
        scene.cycles.use_adaptive_sampling = False
        scene.cycles.use_light_tree = False
        return "sampling_pattern=TABULATED_SOBOL; adaptive=False; light_tree=False"
    if variant == "addon_do_versions":
        previous = scene.cycles.sampling_pattern
        from cycles import version_update

        version_update.do_versions(None)
        return f"cycles.do_versions; sampling_pattern={previous}->{scene.cycles.sampling_pattern}"
    if variant == "pixel_jitter":
        scene.cycles.use_pixel_jitter = True
        return "use_pixel_jitter=true"
    if variant == "filter_box":
        scene.cycles.pixel_filter_type = "BOX"
        return "pixel_filter_type=BOX"
    if variant == "shader_diffuse":
        return replace_with_diffuse(sphere)
    if variant == "geometry_flat":
        changed = sum(1 for polygon in sphere.data.polygons if polygon.use_smooth)
        for polygon in sphere.data.polygons:
            polygon.use_smooth = False
        return f"smooth_polygons_disabled={changed}"
    if variant == "geometry_no_subsurf":
        changed = 0
        for modifier in sphere.modifiers:
            if modifier.type == "SUBSURF" and modifier.show_render:
                modifier.show_render = False
                changed += 1
        return f"subsurf_disabled={changed}"
    if variant == "geometry_plane_only":
        sphere.hide_render = True
        return "sphere.hide_render=true"
    if variant == "geometry_sphere_only":
        named_object("Plane").hide_render = True
        return "plane.hide_render=true"
    raise RuntimeError(f"unknown variant: {variant}")


def enable_float_passes(view_layer):
    pass_properties = (
        "use_pass_z",
        "use_pass_mist",
        "use_pass_position",
        "use_pass_normal",
        "use_pass_vector",
        "use_pass_uv",
        "use_pass_object_index",
        "use_pass_material_index",
        "use_pass_ambient_occlusion",
        "use_pass_shadow",
        "use_pass_emit",
        "use_pass_environment",
        "use_pass_diffuse_direct",
        "use_pass_diffuse_indirect",
        "use_pass_diffuse_color",
        "use_pass_glossy_direct",
        "use_pass_glossy_indirect",
        "use_pass_glossy_color",
        "use_pass_transmission_direct",
        "use_pass_transmission_indirect",
        "use_pass_transmission_color",
    )
    enabled = []
    for name in pass_properties:
        if hasattr(view_layer, name):
            setattr(view_layer, name, True)
            enabled.append(name)
    return enabled


args = script_arguments()
out_base = Path(args.out)
out_base.parent.mkdir(parents=True, exist_ok=True)

registration = ensure_cycles()
scene = bpy.context.scene
scene.cycles.device = "CPU"
scene.render.threads_mode = "FIXED"
scene.render.threads = 1
scene.frame_set(1)

enabled_passes = enable_float_passes(bpy.context.view_layer)
change = apply_variant(args.variant, scene)

bpy.ops.render.render()
render_result = bpy.data.images.get("Render Result")
if render_result is None:
    raise RuntimeError("render produced no Render Result")

scene.render.image_settings.media_type = "MULTI_LAYER_IMAGE"
scene.render.image_settings.file_format = "OPEN_EXR_MULTILAYER"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "32"
scene.render.image_settings.exr_codec = "ZIP"
render_result.save_render(str(out_base.with_suffix(".exr")), scene=scene)

scene.render.image_settings.media_type = "IMAGE"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"
render_result.save_render(str(out_base.with_suffix(".png")), scene=scene)

receipt = {
    "schema": "blender-web.m6-cycles-edge-render.v1",
    "input": bpy.data.filepath,
    "variant": args.variant,
    "change": change,
    "cyclesRegistration": registration,
    "samples": scene.cycles.samples,
    "samplingPattern": scene.cycles.sampling_pattern,
    "seed": scene.cycles.seed,
    "usePixelJitter": scene.cycles.use_pixel_jitter,
    "pixelFilter": scene.cycles.pixel_filter_type,
    "filterWidth": scene.cycles.filter_width,
    "filmTransparent": scene.render.film_transparent,
    "resolution": [
        scene.render.resolution_x * scene.render.resolution_percentage // 100,
        scene.render.resolution_y * scene.render.resolution_percentage // 100,
    ],
    "enabledPassProperties": enabled_passes,
    "cyclesSettings": {
        name: getattr(scene.cycles, name)
        for name in (
            "samples",
            "use_adaptive_sampling",
            "sampling_pattern",
            "scrambling_distance",
            "seed",
            "use_pixel_jitter",
            "use_light_tree",
            "light_sampling_threshold",
            "blur_glossy",
            "sample_clamp_direct",
            "sample_clamp_indirect",
            "ao_bounces",
            "ao_bounces_render",
            "use_fast_gi",
            "use_auto_tile",
            "tile_size",
            "min_light_bounces",
            "max_bounces",
            "diffuse_bounces",
            "glossy_bounces",
            "transmission_bounces",
            "transparent_max_bounces",
            "min_transparent_bounces",
            "use_denoising",
            "film_transparent_glass",
            "film_transparent_roughness",
        )
    },
    "fileVersion": list(bpy.data.version),
    "worldSettings": {
        world.name: {
            "sampling_method": world.cycles.sampling_method,
            "sample_map_resolution": world.cycles.sample_map_resolution,
        }
        for world in bpy.data.worlds
    },
    "lightSettings": {
        light.name: {
            "use_multiple_importance_sampling": light.cycles.use_multiple_importance_sampling,
        }
        for light in bpy.data.lights
    },
    "materialSettings": {
        material.name: {
            "displacement_method": material.cycles.get("displacement_method", "unset"),
            "volume_sampling": material.cycles.volume_sampling,
            "emission_sampling": material.cycles.emission_sampling,
        }
        for material in bpy.data.materials
    },
}
out_base.with_suffix(".json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(
    "M6_EDGE_RENDER_OK",
    f"variant={args.variant}",
    f"samples={scene.cycles.samples}",
    f"requested_passes={len(enabled_passes)}",
    change,
)
