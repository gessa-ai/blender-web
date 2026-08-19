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

struct ViewMatrices_2 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

struct _view_buf_1 {
  view_buf : array<ViewMatrices_2, 64u>,
}

@group(0u) @binding(0u) var<uniform> v_1 : _view_buf_1;

struct _res_id_buf {
  res_id_buf : array<u32>,
}

@group(0u) @binding(2u) var<storage, read> v_2 : _res_id_buf;

struct ObjectMatrices_1 {
  model : mat4x4<f32>,
  model_inverse : mat4x4<f32>,
}

struct _drw_matrix_buf_1 {
  drw_matrix_buf : array<ObjectMatrices_1>,
}

@group(0u) @binding(1u) var<storage, read> v_3 : _drw_matrix_buf_1;

struct ObjectInfos {
  orco_add : vec3<f32>,
  object_attrs_offset : u32,
  orco_mul : vec3<f32>,
  object_attrs_len : u32,
  ob_color : vec4<f32>,
  index : u32,
  light_and_shadow_set_membership : u32,
  random : f32,
  flag : u32,
  shadow_terminator_normal_offset : f32,
  shadow_terminator_geometry_offset : f32,
  _pad1 : f32,
  _pad2 : f32,
}

struct _drw_infos {
  drw_infos : array<ObjectInfos>,
}

@group(0u) @binding(4u) var<storage, read> v_4 : _drw_infos;

struct constants {
  is_transform : u32,
}

@group(0u) @binding(5u) var<uniform> v_5 : constants;

struct outoverlay_outline_prepass_iface {
  ob_id : u32,
}

var<private> interp : outoverlay_outline_prepass_iface;

struct ThemeColors {
  wire : vec4<f32>,
  wire_edit : vec4<f32>,
  active_object : vec4<f32>,
  object_select : vec4<f32>,
  library_select : vec4<f32>,
  library : vec4<f32>,
  transform : vec4<f32>,
  light : vec4<f32>,
  speaker : vec4<f32>,
  camera : vec4<f32>,
  camera_path : vec4<f32>,
  empty : vec4<f32>,
  vert : vec4<f32>,
  vert_select : vec4<f32>,
  vert_unreferenced : vec4<f32>,
  vert_missing_data : vec4<f32>,
  edit_mesh_active : vec4<f32>,
  edge_select : vec4<f32>,
  edge_mode_select : vec4<f32>,
  edge_seam : vec4<f32>,
  edge_sharp : vec4<f32>,
  edge_crease : vec4<f32>,
  edge_bweight : vec4<f32>,
  edge_face_select : vec4<f32>,
  edge_freestyle : vec4<f32>,
  face : vec4<f32>,
  face_select : vec4<f32>,
  face_mode_select : vec4<f32>,
  face_retopology : vec4<f32>,
  face_freestyle : vec4<f32>,
  gpencil_wire_edit : vec4<f32>,
  gpencil_vertex : vec4<f32>,
  gpencil_vertex_select : vec4<f32>,
  normal : vec4<f32>,
  vnormal : vec4<f32>,
  lnormal : vec4<f32>,
  facedot : vec4<f32>,
  skinroot : vec4<f32>,
  deselect : vec4<f32>,
  outline : vec4<f32>,
  light_no_alpha : vec4<f32>,
  background : vec4<f32>,
  background_gradient : vec4<f32>,
  checker_primary : vec4<f32>,
  checker_secondary : vec4<f32>,
  clipping_border : vec4<f32>,
  edit_mesh_middle : vec4<f32>,
  handle_free : vec4<f32>,
  handle_auto : vec4<f32>,
  handle_vect : vec4<f32>,
  handle_align : vec4<f32>,
  handle_autoclamp : vec4<f32>,
  handle_sel_free : vec4<f32>,
  handle_sel_auto : vec4<f32>,
  handle_sel_vect : vec4<f32>,
  handle_sel_align : vec4<f32>,
  handle_sel_autoclamp : vec4<f32>,
  nurb_uline : vec4<f32>,
  nurb_vline : vec4<f32>,
  nurb_sel_uline : vec4<f32>,
  nurb_sel_vline : vec4<f32>,
  bone_pose : vec4<f32>,
  bone_pose_active : vec4<f32>,
  bone_pose_active_unsel : vec4<f32>,
  bone_pose_constraint : vec4<f32>,
  bone_pose_ik : vec4<f32>,
  bone_pose_spline_ik : vec4<f32>,
  bone_pose_no_target : vec4<f32>,
  bone_solid : vec4<f32>,
  bone_locked : vec4<f32>,
  bone_active : vec4<f32>,
  bone_active_unsel : vec4<f32>,
  bone_select : vec4<f32>,
  bone_ik_line : vec4<f32>,
  bone_ik_line_no_target : vec4<f32>,
  bone_ik_line_spline : vec4<f32>,
  text : vec4<f32>,
  text_hi : vec4<f32>,
  bundle_solid : vec4<f32>,
  mball_radius : vec4<f32>,
  mball_radius_select : vec4<f32>,
  mball_stiffness : vec4<f32>,
  mball_stiffness_select : vec4<f32>,
  current_frame : vec4<f32>,
  before_frame : vec4<f32>,
  after_frame : vec4<f32>,
  grid : vec4<f32>,
  grid_emphasis : vec4<f32>,
  grid_axis_x : vec4<f32>,
  grid_axis_y : vec4<f32>,
  grid_axis_z : vec4<f32>,
  face_back : vec4<f32>,
  face_front : vec4<f32>,
  uv_shadow : vec4<f32>,
}

struct ThemeSizes {
  pixel : f32,
  object_center : f32,
  light_center : f32,
  light_circle : f32,
  light_circle_shadow : f32,
  vert : f32,
  edge : f32,
  face_dot : f32,
  checker : f32,
  vertex_gpencil : f32,
  _pad1 : f32,
  _pad2 : f32,
}

struct UniformData {
  colors : ThemeColors,
  sizes : ThemeSizes,
  size_viewport : vec2<f32>,
  size_viewport_inv : vec2<f32>,
  fresnel_mix_edit : f32,
  pixel_fac : f32,
  backface_culling : u32,
  _pad1 : f32,
}

struct _uniform_buf {
  uniform_buf : UniformData,
}

@group(0u) @binding(3u) var<uniform> v_6 : _uniform_buf;

fn main_inner(gl_InstanceIndex : i32, pos : vec3<f32>) {
  gpu_PointSize_sink = 1.0f;
  v_7(gl_InstanceIndex, pos);
  v.gl_Position.z = ((v.gl_Position.z + v.gl_Position.w) * 0.5f);
  v.gl_Position.y = (v.gl_Position.y * bitcast<f32>(gpu_clip_y_sign_uint));
}

fn v_8(outline_id : ptr<function, u32>, object_id : ptr<function, u32>) -> u32 {
  return ((*(outline_id) << 14u) | ((*(object_id) << 18u) >> 18u));
}

struct ViewMatrices_1 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

fn v_9() -> ViewMatrices_1 {
  var v_10 : ViewMatrices_1;
  let v_11 = v_1.view_buf[0i];
  v_10.viewmat = v_11.viewmat;
  v_10.viewinv = v_11.viewinv;
  v_10.winmat = v_11.winmat;
  v_10.wininv = v_11.wininv;
  return v_10;
}

fn v_12(P : ptr<function, vec3<f32>>) -> vec4<f32> {
  let v_13 = v_9().winmat;
  let v_14 = v_9().viewmat;
  let v_15 = *(P);
  return (v_13 * (v_14 * vec4<f32>(v_15.x, v_15.y, v_15.z, 1.0f)));
}

fn v_16(gl_InstanceIndex : i32) -> u32 {
  var id : u32;
  id = v_2.res_id_buf[(0i + gl_InstanceIndex)];
  return id;
}

fn v_17(gl_InstanceIndex : i32) -> u32 {
  return (v_16(gl_InstanceIndex) >> bitcast<u32>(0i));
}

fn v_18(gl_InstanceIndex : i32) -> mat4x4<f32> {
  return v_3.drw_matrix_buf[v_17(gl_InstanceIndex)].model;
}

fn v_19(lP : ptr<function, vec3<f32>>, gl_InstanceIndex : i32) -> vec3<f32> {
  let v_20 = v_18(gl_InstanceIndex);
  let v_21 = *(lP);
  return ((v_20 * vec4<f32>(v_21.x, v_21.y, v_21.z, 1.0f))).xyz;
}

struct ObjectInfos_1 {
  orco_add : vec3<f32>,
  object_attrs_offset : u32,
  orco_mul : vec3<f32>,
  object_attrs_len : u32,
  ob_color : vec4<f32>,
  index : u32,
  light_and_shadow_set_membership : u32,
  random : f32,
  flag : u32,
  shadow_terminator_normal_offset : f32,
  shadow_terminator_geometry_offset : f32,
  _pad1 : f32,
  _pad2 : f32,
}

fn v_22(gl_InstanceIndex : i32) -> ObjectInfos_1 {
  var v_23 : ObjectInfos_1;
  let v_24 = v_4.drw_infos[v_17(gl_InstanceIndex)];
  v_23.orco_add = v_24.orco_add;
  v_23.object_attrs_offset = v_24.object_attrs_offset;
  v_23.orco_mul = v_24.orco_mul;
  v_23.object_attrs_len = v_24.object_attrs_len;
  v_23.ob_color = v_24.ob_color;
  v_23.index = v_24.index;
  v_23.light_and_shadow_set_membership = v_24.light_and_shadow_set_membership;
  v_23.random = v_24.random;
  v_23.flag = v_24.flag;
  v_23.shadow_terminator_normal_offset = v_24.shadow_terminator_normal_offset;
  v_23.shadow_terminator_geometry_offset = v_24.shadow_terminator_geometry_offset;
  v_23._pad1 = v_24._pad1;
  v_23._pad2 = v_24._pad2;
  return v_23;
}

fn v_25(wpos : ptr<function, vec3<f32>>) {
}

fn v_26(flag : ptr<function, u32>, val : ptr<function, u32>) -> bool {
  return ((*(flag) & *(val)) != 0u);
}

fn v_27(gl_InstanceIndex : i32) -> u32 {
  var ob_flag : u32;
  var is_active : bool;
  var param : u32;
  var param_1 : u32;
  ob_flag = v_22(gl_InstanceIndex).flag;
  param = ob_flag;
  param_1 = 8u;
  is_active = v_26(&(param), &(param_1));
  if ((v_5.is_transform != 0u)) {
    return 0u;
  } else if (is_active) {
    return 3u;
  } else {
    return 1u;
  }
  return u32();
}

fn v_7(gl_InstanceIndex : i32, pos : vec3<f32>) {
  var world_pos : vec3<f32>;
  var param : vec3<f32>;
  var param_2 : vec3<f32>;
  var outline_id : u32;
  var param_3 : u32;
  var param_4 : u32;
  var param_5 : vec3<f32>;
  param = pos;
  world_pos = v_19(&(param), gl_InstanceIndex);
  param_2 = world_pos;
  v.gl_Position = v_12(&(param_2));
  v.gl_Position.z = (v.gl_Position.z - 0.00100000004749745131f);
  interp.ob_id = (v_17(gl_InstanceIndex) + 1u);
  outline_id = v_27(gl_InstanceIndex);
  param_3 = outline_id;
  param_4 = interp.ob_id;
  interp.ob_id = v_8(&(param_3), &(param_4));
  param_5 = world_pos;
  v_25(&(param_5));
}

struct tint_symbol {
  @builtin(position)
  gl_Position : vec4<f32>,
  @location(0u) @interpolate(flat)
  ob_id : u32,
}

@vertex
fn main(@builtin(instance_index) gl_InstanceIndex : u32, @location(0u) pos : vec3<f32>) -> tint_symbol {
  main_inner(i32(gl_InstanceIndex), pos);
  return tint_symbol(v.gl_Position, interp.ob_id);
}

