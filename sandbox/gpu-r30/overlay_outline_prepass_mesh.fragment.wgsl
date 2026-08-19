diagnostic(off, derivative_uniformity);
diagnostic(off, chromium.unreachable_code);

var<private> out_object_id : u32;

struct constants {
  is_transform : u32,
}

@group(0u) @binding(5u) var<uniform> v : constants;

struct _res_id_buf {
  res_id_buf : array<u32>,
}

@group(0u) @binding(2u) var<storage, read> v_1 : _res_id_buf;

struct ObjectMatrices_1 {
  model : mat4x4<f32>,
  model_inverse : mat4x4<f32>,
}

struct _drw_matrix_buf_1 {
  drw_matrix_buf : array<ObjectMatrices_1>,
}

@group(0u) @binding(1u) var<storage, read> v_2 : _drw_matrix_buf_1;

struct ViewMatrices_1 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

struct _view_buf_1 {
  view_buf : array<ViewMatrices_1, 64u>,
}

@group(0u) @binding(0u) var<uniform> v_3 : _view_buf_1;

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

@group(0u) @binding(3u) var<uniform> v_5 : _uniform_buf;

struct inoverlay_outline_prepass_iface {
  ob_id : u32,
}

fn main_inner(interp : inoverlay_outline_prepass_iface) {
  out_object_id = interp.ob_id;
}

@fragment
fn main(@location(0u) @interpolate(flat) v_6 : u32) -> @location(0u) @interpolate(flat) u32 {
  let interp = inoverlay_outline_prepass_iface(v_6);
  main_inner(interp);
  return out_object_id;
}

