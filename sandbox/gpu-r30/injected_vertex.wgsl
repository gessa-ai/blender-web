diagnostic(off, derivative_uniformity);
diagnostic(off, chromium.unreachable_code);

@id(1000) override gpu_clip_y_sign_uint : u32 = 3212836864u;

var<private> gpu_PointSize_sink : f32;

struct gl_PerVertex {
  gl_Position : vec4<f32>,
  gl_PointSize : f32,
  gl_ClipDistance : array<f32, 1u>,
  gl_CullDistance : array<f32, 1u>,
}

var<private> v : gl_PerVertex;

struct _res_id_with_custom_id_buf {
  res_id_with_custom_id_buf : array<vec2<u32>>,
}

@group(0u) @binding(4u) var<storage, read> v_1 : _res_id_with_custom_id_buf;

struct ObjectMatrices_2 {
  model : mat4x4<f32>,
  model_inverse : mat4x4<f32>,
}

struct _drw_matrix_buf_1 {
  drw_matrix_buf : array<ObjectMatrices_2>,
}

@group(0u) @binding(3u) var<storage, read> v_2 : _drw_matrix_buf_1;

struct ViewMatrices_2 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

struct _view_buf_1 {
  view_buf : array<ViewMatrices_2, 64u>,
}

@group(0u) @binding(2u) var<uniform> v_3 : _view_buf_1;

struct _materials_data {
  materials_data : array<vec4<f32>>,
}

@group(0u) @binding(1u) var<storage, read> v_4 : _materials_data;

var<private> workbench_prepass_VertOut_uv : vec2<f32>;

var<private> workbench_prepass_VertOut_normal : vec3<f32>;

var<private> workbench_prepass_VertOut_object_id : i32;

var<private> workbench_prepass_VertOut_color : vec3<f32>;

var<private> workbench_prepass_VertOut_alpha : f32;

var<private> workbench_prepass_VertOut_roughness : f32;

var<private> workbench_prepass_VertOut_metallic : f32;

struct constants {
  force_shadowing : u32,
  is_image_tile : u32,
  image_premult : u32,
  image_transparency_cutoff : f32,
}

@group(0u) @binding(5u) var<uniform> v_5 : constants;

struct _drw_clipping_ {
  drw_clipping_ : array<vec4<f32>, 6u>,
}

@group(0u) @binding(0u) var<uniform> v_6 : _drw_clipping_;

fn main_inner(gl_InstanceIndex : i32, pos : vec3<f32>, au : vec2<f32>, nor : vec3<f32>, ac : vec4<f32>) {
  gpu_PointSize_sink = 1.0f;
  v_7(gl_InstanceIndex, pos, au, nor, ac);
  v.gl_Position.z = ((v.gl_Position.z + v.gl_Position.w) * 0.5f);
  v.gl_Position.y = (v.gl_Position.y * bitcast<f32>(gpu_clip_y_sign_uint));
}

fn v_8(m : ptr<function, mat4x4<f32>>) -> mat3x3<f32> {
  let v_9 = *(m);
  return mat3x3<f32>(v_9[0u].xyz, v_9[1u].xyz, v_9[2u].xyz);
}

struct ViewMatrices_1 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

fn v_10(this_ : ViewMatrices_1, P : ptr<function, vec3<f32>>) -> vec4<f32> {
  let v_11 = *(P);
  return (this_.winmat * (this_.viewmat * vec4<f32>(v_11.x, v_11.y, v_11.z, 1.0f)));
}

struct ObjectMatrices_1 {
  model : mat4x4<f32>,
  model_inverse : mat4x4<f32>,
}

fn v_12(this_ : ObjectMatrices_1) -> mat3x3<f32> {
  var param : mat4x4<f32>;
  param = this_.model_inverse;
  return transpose(v_8(&(param)));
}

fn v_13(this_ : ObjectMatrices_1, view : ptr<function, ViewMatrices_1>, lN : ptr<function, vec3<f32>>) -> vec3<f32> {
  var param : mat4x4<f32>;
  param = (*(view)).viewmat;
  return (v_8(&(param)) * (v_12(this_) * *(lN)));
}

fn v_14(this_ : ObjectMatrices_1, lP : ptr<function, vec3<f32>>) -> vec3<f32> {
  let v_15 = *(lP);
  return ((this_.model * vec4<f32>(v_15.x, v_15.y, v_15.z, 1.0f))).xyz;
}

struct draw_ID {
  raw_id : u32,
}

fn v_16(this_ : draw_ID) -> u32 {
  return (this_.raw_id & 0u);
}

fn v_17(this_ : draw_ID) -> u32 {
  return (this_.raw_id >> bitcast<u32>(0i));
}

struct draw_ResourceCustomID {
  _pad : i32,
}

fn v_18() -> draw_ResourceCustomID {
  var r : draw_ResourceCustomID;
  r._pad = 0i;
  return r;
}

fn v_19(this_ : ptr<function, draw_ResourceCustomID>, instance_index : ptr<function, i32>) -> draw_ID {
  return draw_ID(v_1.res_id_with_custom_id_buf[*(instance_index)].x);
}

fn v_20(this_ : ptr<function, draw_ResourceCustomID>, instance_index : ptr<function, i32>) -> u32 {
  return v_1.res_id_with_custom_id_buf[*(instance_index)].y;
}

struct draw_Model {
  _pad : i32,
}

fn v_21() -> draw_Model {
  var r : draw_Model;
  r._pad = 0i;
  return r;
}

fn v_22(this_ : ptr<function, draw_Model>, resource_id : ptr<function, u32>) -> ObjectMatrices_1 {
  var v_23 : ObjectMatrices_1;
  let v_24 = v_2.drw_matrix_buf[*(resource_id)];
  v_23.model = v_24.model;
  v_23.model_inverse = v_24.model_inverse;
  return v_23;
}

struct draw_View {
  _pad : i32,
}

fn v_25() -> draw_View {
  var r : draw_View;
  r._pad = 0i;
  return r;
}

fn v_26(this_ : ptr<function, draw_View>, view_id : ptr<function, u32>) -> ViewMatrices_1 {
  var v_27 : ViewMatrices_1;
  let v_28 = v_3.view_buf[*(view_id)];
  v_27.viewmat = v_28.viewmat;
  v_27.viewinv = v_28.viewinv;
  v_27.winmat = v_28.winmat;
  v_27.wininv = v_28.wininv;
  return v_27;
}

struct workbench_color_Materials {
  _pad : i32,
}

fn v_29() -> workbench_color_Materials {
  var r : workbench_color_Materials;
  r._pad = 0i;
  return r;
}

fn v_30(this_ : ptr<function, workbench_color_Materials>, handle : ptr<function, i32>, vertex_color : ptr<function, vec3<f32>>, color : ptr<function, vec3<f32>>, alpha : ptr<function, f32>, roughness : ptr<function, f32>, metallic : ptr<function, f32>) {
  var data : vec4<f32>;
  var v_31 : vec3<f32>;
  var encoded_data : u32;
  data = v_4.materials_data[*(handle)];
  if ((data.x == -1.0f)) {
    v_31 = *(vertex_color);
  } else {
    v_31 = data.xyz;
  }
  *(color) = v_31;
  encoded_data = bitcast<u32>(data.w);
  *(alpha) = (f32(((encoded_data >> 16u) & 255u)) * 0.0039215688593685627f);
  *(roughness) = (f32(((encoded_data >> 8u) & 255u)) * 0.0039215688593685627f);
  *(metallic) = (f32((encoded_data & 255u)) * 0.0039215688593685627f);
}

struct workbench_prepass_Mesh {
  _pad : i32,
}

fn v_32() -> workbench_prepass_Mesh {
  var r : workbench_prepass_Mesh;
  r._pad = 0i;
  return r;
}

fn v_33(gl_InstanceIndex : i32, pos : vec3<f32>, au : vec2<f32>, nor : vec3<f32>, ac : vec4<f32>) {
  var mesh : workbench_prepass_Mesh;
  var materials : workbench_color_Materials;
  var views : draw_View;
  var models : draw_Model;
  var resources : draw_ResourceCustomID;
  var custom_id : i32;
  var param : draw_ResourceCustomID;
  var param_1 : i32;
  var id : draw_ID;
  var param_2 : draw_ResourceCustomID;
  var param_3 : i32;
  var view : ViewMatrices_1;
  var param_4 : draw_View;
  var param_5 : u32;
  var obj : ObjectMatrices_1;
  var param_6 : draw_Model;
  var param_7 : u32;
  var world_pos : vec3<f32>;
  var param_8 : vec3<f32>;
  var param_9 : vec3<f32>;
  var param_10 : ViewMatrices_1;
  var param_11 : vec3<f32>;
  var param_12 : workbench_color_Materials;
  var param_13 : i32;
  var param_14 : vec3<f32>;
  var param_15 : vec3<f32>;
  var param_16 : f32;
  var param_17 : f32;
  var param_18 : f32;
  mesh = v_32();
  materials = v_29();
  views = v_25();
  models = v_21();
  resources = v_18();
  param = resources;
  param_1 = gl_InstanceIndex;
  custom_id = bitcast<i32>(v_20(&(param), &(param_1)));
  param_2 = resources;
  param_3 = gl_InstanceIndex;
  id = v_19(&(param_2), &(param_3));
  let v_34 = v_16(id);
  param_4 = views;
  param_5 = v_34;
  view = v_26(&(param_4), &(param_5));
  let v_35 = v_17(id);
  param_6 = models;
  param_7 = v_35;
  obj = v_22(&(param_6), &(param_7));
  let v_36 = obj;
  param_8 = pos;
  world_pos = v_14(v_36, &(param_8));
  let v_37 = view;
  param_9 = world_pos;
  v.gl_Position = v_10(v_37, &(param_9));
  workbench_prepass_VertOut_uv = au;
  let v_38 = obj;
  param_10 = view;
  param_11 = nor;
  workbench_prepass_VertOut_normal = normalize(v_13(v_38, &(param_10), &(param_11)));
  workbench_prepass_VertOut_object_id = (bitcast<i32>((v_17(id) & 65535u)) + 1i);
  param_12 = materials;
  param_13 = custom_id;
  param_14 = ac.xyz;
  param_15 = workbench_prepass_VertOut_color;
  param_16 = workbench_prepass_VertOut_alpha;
  param_17 = workbench_prepass_VertOut_roughness;
  param_18 = workbench_prepass_VertOut_metallic;
  v_30(&(param_12), &(param_13), &(param_14), &(param_15), &(param_16), &(param_17), &(param_18));
  workbench_prepass_VertOut_color = param_15;
  workbench_prepass_VertOut_alpha = param_16;
  workbench_prepass_VertOut_roughness = param_17;
  workbench_prepass_VertOut_metallic = param_18;
}

fn v_7(gl_InstanceIndex : i32, pos : vec3<f32>, au : vec2<f32>, nor : vec3<f32>, ac : vec4<f32>) {
  v_33(gl_InstanceIndex, pos, au, nor, ac);
}

struct tint_symbol {
  @builtin(position)
  gl_Position : vec4<f32>,
  @location(2u)
  workbench_prepass_VertOut_uv : vec2<f32>,
  @location(0u)
  workbench_prepass_VertOut_normal : vec3<f32>,
  @location(4u) @interpolate(flat)
  workbench_prepass_VertOut_object_id : i32,
  @location(1u)
  workbench_prepass_VertOut_color : vec3<f32>,
  @location(3u)
  workbench_prepass_VertOut_alpha : f32,
  @location(5u) @interpolate(flat)
  workbench_prepass_VertOut_roughness : f32,
  @location(6u) @interpolate(flat)
  workbench_prepass_VertOut_metallic : f32,
}

@vertex
fn main(@builtin(vertex_index) bw_vid : u32, @builtin(instance_index) gl_InstanceIndex : u32, @location(0u) pos : vec3<f32>, @location(3u) au : vec2<f32>, @location(1u) nor : vec3<f32>, @location(2u) ac : vec4<f32>) -> tint_symbol {
  main_inner(i32(gl_InstanceIndex), pos, au, nor, ac);
  var bw_tri = array<vec2<f32>, 3u>(vec2<f32>(-0.5f, -0.5f), vec2<f32>(0.5f, -0.5f), vec2<f32>(0.0f, 0.5f)); v.gl_Position = vec4<f32>(bw_tri[(bw_vid % 3u)], 0.5f, 1.0f); return tint_symbol(v.gl_Position, workbench_prepass_VertOut_uv, workbench_prepass_VertOut_normal, workbench_prepass_VertOut_object_id, workbench_prepass_VertOut_color, workbench_prepass_VertOut_alpha, workbench_prepass_VertOut_roughness, workbench_prepass_VertOut_metallic);
}

