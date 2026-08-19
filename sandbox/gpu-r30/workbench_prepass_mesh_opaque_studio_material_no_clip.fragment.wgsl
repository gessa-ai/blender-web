diagnostic(off, derivative_uniformity);
diagnostic(off, chromium.unreachable_code);

var<private> workbench_prepass_OpaqueOut_object_id : u32;

var<private> workbench_prepass_OpaqueOut_normal : vec2<f32>;

var<private> workbench_prepass_OpaqueOut_material : vec4<f32>;

struct constants {
  force_shadowing : u32,
  is_image_tile : u32,
  image_premult : u32,
  image_transparency_cutoff : f32,
}

@group(0u) @binding(5u) var<uniform> v : constants;

struct _drw_clipping_ {
  drw_clipping_ : array<vec4<f32>, 6u>,
}

@group(0u) @binding(0u) var<uniform> v_1 : _drw_clipping_;

struct _res_id_with_custom_id_buf {
  res_id_with_custom_id_buf : array<vec2<u32>>,
}

@group(0u) @binding(4u) var<storage, read> v_2 : _res_id_with_custom_id_buf;

struct ObjectMatrices_1 {
  model : mat4x4<f32>,
  model_inverse : mat4x4<f32>,
}

struct _drw_matrix_buf_1 {
  drw_matrix_buf : array<ObjectMatrices_1>,
}

@group(0u) @binding(3u) var<storage, read> v_3 : _drw_matrix_buf_1;

struct ViewMatrices_1 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

struct _view_buf_1 {
  view_buf : array<ViewMatrices_1, 64u>,
}

@group(0u) @binding(2u) var<uniform> v_4 : _view_buf_1;

struct _materials_data {
  materials_data : array<vec4<f32>>,
}

@group(0u) @binding(1u) var<storage, read> v_5 : _materials_data;

fn main_inner(workbench_prepass_VertOut_object_id : i32, gl_FrontFacing : bool, workbench_prepass_VertOut_normal : vec3<f32>, workbench_prepass_VertOut_color : vec3<f32>, workbench_prepass_VertOut_roughness : f32, workbench_prepass_VertOut_metallic : f32, workbench_prepass_VertOut_uv : vec2<f32>, workbench_prepass_VertOut_alpha : f32) {
  v_6(workbench_prepass_VertOut_object_id, gl_FrontFacing, workbench_prepass_VertOut_normal, workbench_prepass_VertOut_color, workbench_prepass_VertOut_roughness, workbench_prepass_VertOut_metallic);
}

fn v_7(front_face : ptr<function, bool>, n : ptr<function, vec3<f32>>) -> vec2<f32> {
  var v_8 : vec3<f32>;
  var p : f32;
  if (*(front_face)) {
    v_8 = *(n);
  } else {
    v_8 = -(*(n));
  }
  *(n) = normalize(v_8);
  p = sqrt((((*(n)).z * 8.0f) + 8.0f));
  let v_9 = (*(n)).xy;
  let v_10 = p;
  let v_11 = clamp(((v_9 / vec2<f32>(v_10, v_10)) + vec2<f32>(0.5f, 0.5f)), vec2<f32>(0.0f, 0.0f), vec2<f32>(1.0f, 1.0f));
  (*(n)).x = v_11.x;
  (*(n)).y = v_11.y;
  return (*(n)).xy;
}

fn v_12(v1 : ptr<function, f32>, v2 : ptr<function, f32>) -> f32 {
  var iv1 : i32;
  var iv2 : i32;
  iv1 = i32((*(v1) * 31.0f));
  iv2 = (i32((*(v2) * 7.0f)) << bitcast<u32>(5i));
  return f32((iv1 | iv2));
}

struct workbench_color_Texture {
  _pad : i32,
}

fn v_13() -> workbench_color_Texture {
  var r : workbench_color_Texture;
  r._pad = 0i;
  return r;
}

struct workbench_prepass_Resources {
  texture : workbench_color_Texture,
}

fn v_14() -> workbench_prepass_Resources {
  var r : workbench_prepass_Resources;
  r.texture = v_13();
  return r;
}

fn v_6(workbench_prepass_VertOut_object_id : i32, gl_FrontFacing : bool, workbench_prepass_VertOut_normal : vec3<f32>, workbench_prepass_VertOut_color : vec3<f32>, workbench_prepass_VertOut_roughness : f32, workbench_prepass_VertOut_metallic : f32) {
  var srt : workbench_prepass_Resources;
  var param : bool;
  var param_1 : vec3<f32>;
  var param_2 : f32;
  var param_3 : f32;
  srt = v_14();
  workbench_prepass_OpaqueOut_object_id = bitcast<u32>(workbench_prepass_VertOut_object_id);
  param = gl_FrontFacing;
  param_1 = workbench_prepass_VertOut_normal;
  workbench_prepass_OpaqueOut_normal = v_7(&(param), &(param_1));
  param_2 = workbench_prepass_VertOut_roughness;
  param_3 = workbench_prepass_VertOut_metallic;
  workbench_prepass_OpaqueOut_material = vec4<f32>(workbench_prepass_VertOut_color.x, workbench_prepass_VertOut_color.y, workbench_prepass_VertOut_color.z, v_12(&(param_2), &(param_3)));
}

struct tint_symbol {
  @location(2u) @interpolate(flat)
  workbench_prepass_OpaqueOut_object_id : u32,
  @location(1u)
  workbench_prepass_OpaqueOut_normal : vec2<f32>,
  @location(0u)
  workbench_prepass_OpaqueOut_material : vec4<f32>,
}

@fragment
fn main(@location(4u) @interpolate(flat) workbench_prepass_VertOut_object_id : i32, @builtin(front_facing) gl_FrontFacing : bool, @location(0u) workbench_prepass_VertOut_normal : vec3<f32>, @location(1u) workbench_prepass_VertOut_color : vec3<f32>, @location(5u) @interpolate(flat) workbench_prepass_VertOut_roughness : f32, @location(6u) @interpolate(flat) workbench_prepass_VertOut_metallic : f32, @location(2u) workbench_prepass_VertOut_uv : vec2<f32>, @location(3u) workbench_prepass_VertOut_alpha : f32) -> tint_symbol {
  main_inner(workbench_prepass_VertOut_object_id, gl_FrontFacing, workbench_prepass_VertOut_normal, workbench_prepass_VertOut_color, workbench_prepass_VertOut_roughness, workbench_prepass_VertOut_metallic, workbench_prepass_VertOut_uv, workbench_prepass_VertOut_alpha);
  return tint_symbol(workbench_prepass_OpaqueOut_object_id, workbench_prepass_OpaqueOut_normal, workbench_prepass_OpaqueOut_material);
}

