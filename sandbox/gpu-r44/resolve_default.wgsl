
diagnostic(off, derivative_uniformity);
diagnostic(off, chromium.unreachable_code);

struct ViewMatrices_2 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

struct _view_buf_1 {
  view_buf : array<ViewMatrices_2, 64u>,
}

@group(0u) @binding(3u) var<uniform> v_1 : _view_buf_1;

struct SolidLightData {
  direction : vec4<f32>,
  specular_color : vec4<f32>,
  diffuse_color_wrap : vec4<f32>,
}

struct WorldData {
  viewport_size : vec2<f32>,
  viewport_size_inv : vec2<f32>,
  object_outline_color : vec4<f32>,
  shadow_direction_vs : vec4<f32>,
  shadow_focus : f32,
  shadow_shift : f32,
  shadow_mul : f32,
  shadow_add : f32,
  lights : array<SolidLightData, 4u>,
  ambient_color : vec4<f32>,
  cavity_sample_start : i32,
  cavity_sample_end : i32,
  cavity_sample_count_inv : f32,
  cavity_jitter_scale : f32,
  cavity_valley_factor : f32,
  cavity_ridge_factor : f32,
  cavity_attenuation : f32,
  cavity_distance : f32,
  curvature_ridge : f32,
  curvature_valley : f32,
  ui_scale : f32,
  _pad0 : f32,
  matcap_orientation : i32,
  use_specular : u32,
  xray_alpha : f32,
  _pad1 : i32,
  background_color : vec4<f32>,
}

struct _world_data {
  world_data : WorldData,
}

@group(0u) @binding(4u) var<uniform> v_2 : _world_data;

@group(0u) @binding(256u) var depth_tx_sampler : sampler;

@group(0u) @binding(0u) var depth_tx_image : texture_2d<f32>;

@group(0u) @binding(257u) var normal_tx_sampler : sampler;

@group(0u) @binding(1u) var normal_tx_image : texture_2d<f32>;

@group(0u) @binding(258u) var material_tx_sampler : sampler;

@group(0u) @binding(2u) var material_tx_image : texture_2d<f32>;

var<private> workbench_resolve_FragOut_color : vec4<f32>;

fn main_inner(gl_FragCoord : vec4<f32>) {
  v_3(gl_FragCoord);
}

struct ViewMatrices_1 {
  viewmat : mat4x4<f32>,
  viewinv : mat4x4<f32>,
  winmat : mat4x4<f32>,
  wininv : mat4x4<f32>,
}

fn v_4() -> ViewMatrices_1 {
  var v_5 : ViewMatrices_1;
  let v_6 = v_1.view_buf[0i];
  v_5.viewmat = v_6.viewmat;
  v_5.viewinv = v_6.viewinv;
  v_5.winmat = v_6.winmat;
  v_5.wininv = v_6.wininv;
  return v_5;
}

fn v_7() -> bool {
  return (v_4().winmat[3u].w == 0.0f);
}

fn v_8(vP : ptr<function, vec3<f32>>) -> vec3<f32> {
  var v_9 : vec3<f32>;
  if (v_7()) {
    v_9 = normalize(-(*(vP)));
  } else {
    v_9 = vec3<f32>(0.0f, 0.0f, 1.0f);
  }
  return v_9;
}

fn v_10(ss_P : ptr<function, vec3<f32>>) -> vec3<f32> {
  return ((*(ss_P) * 2.0f) - vec3<f32>(1.0f, 1.0f, 1.0f));
}

fn v_11(hs_P : ptr<function, vec4<f32>>) -> vec3<f32> {
  let v_12 = (*(hs_P)).xyz;
  let v_13 = (*(hs_P)).w;
  return (v_12 / vec3<f32>(v_13, v_13, v_13));
}

fn v_14(ssP : ptr<function, vec3<f32>>) -> vec3<f32> {
  var param : vec4<f32>;
  let v_15 = v_4().wininv;
  let v_16 = *(ssP);
  param = (v_15 * vec4<f32>(v_16.x, v_16.y, v_16.z, 1.0f));
  return v_11(&(param));
}

fn v_17(ssP : ptr<function, vec3<f32>>) -> vec3<f32> {
  var param : vec3<f32>;
  var param_1 : vec3<f32>;
  param = *(ssP);
  param_1 = v_10(&(param));
  return v_14(&(param_1));
}

struct workbench_World {
  _pad : i32,
}

fn v_18() -> workbench_World {
  var r : workbench_World;
  r._pad = 0i;
  return r;
}

fn v_19() -> workbench_World {
  var result : workbench_World;
  result._pad = 0i;
  return result;
}

fn v_20(enc : ptr<function, vec4<f32>>) -> vec3<f32> {
  var fenc : vec2<f32>;
  var f : f32;
  var g : f32;
  var n : vec3<f32>;
  fenc = (((*(enc)).xy * 4.0f) - vec2<f32>(2.0f, 2.0f));
  f = dot(fenc, fenc);
  g = sqrt((1.0f - (f / 4.0f)));
  let v_21 = (fenc * g);
  n.x = v_21.x;
  n.y = v_21.y;
  n.z = (1.0f - (f / 2.0f));
  return n;
}

fn v_22(data : ptr<function, f32>, v1 : ptr<function, f32>, v2 : ptr<function, f32>) {
  var idata : i32;
  idata = i32(*(data));
  *(v1) = (f32((idata & 31i)) * 0.03225806355476379395f);
  *(v2) = (f32((idata >> bitcast<u32>(5i))) * 0.14285714924335479736f);
}

struct workbench_Cavity {
  _pad : i32,
}

fn v_23() -> workbench_Cavity {
  var r : workbench_Cavity;
  r._pad = 0i;
  return r;
}

fn v_24(v : ptr<function, vec4<f32>>) -> vec4<f32> {
  return bitcast<vec4<f32>>((vec4<i32>(2129606411i, 2129606411i, 2129606411i, 2129606411i) - bitcast<vec4<i32>>(*(v))));
}

fn v_25(spec_color : ptr<function, vec3<f32>>, roughness : ptr<function, f32>, NV : ptr<function, f32>) -> vec3<f32> {
  var fresnel : f32;
  fresnel = (exp2((-8.3500003814697265625f * *(NV))) * (1.0f - *(roughness)));
  let v_26 = *(spec_color);
  let v_27 = fresnel;
  return mix(v_26, vec3<f32>(1.0f), vec3<f32>(v_27, v_27, v_27));
}

fn v_28(shininess : ptr<function, vec4<f32>>, spec_angle : ptr<function, vec4<f32>>, NL : ptr<function, vec4<f32>>) -> vec4<f32> {
  var normalization_factor : vec4<f32>;
  var spec_light : vec4<f32>;
  normalization_factor = ((*(shininess) * 0.125f) + vec4<f32>(1.0f, 1.0f, 1.0f, 1.0f));
  spec_light = ((pow(*(spec_angle), *(shininess)) * *(NL)) * normalization_factor);
  return spec_light;
}

fn v_29(NL : ptr<function, vec4<f32>>, w : ptr<function, vec4<f32>>) -> vec4<f32> {
  var w_1 : vec4<f32>;
  var denom : vec4<f32>;
  var param : vec4<f32>;
  w_1 = (*(w) + vec4<f32>(1.0f, 1.0f, 1.0f, 1.0f));
  param = (w_1 * w_1);
  denom = v_24(&(param));
  return clamp(((*(NL) + *(w)) * denom), vec4<f32>(0.0f, 0.0f, 0.0f, 0.0f), vec4<f32>(1.0f, 1.0f, 1.0f, 1.0f));
}

fn v_30(world : workbench_World, base_color : ptr<function, vec3<f32>>, roughness : ptr<function, f32>, metallic : ptr<function, f32>, N : ptr<function, vec3<f32>>, I : ptr<function, vec3<f32>>) -> vec3<f32> {
  var diffuse_color : vec3<f32>;
  var specular_color : vec3<f32>;
  var specular_light : vec3<f32>;
  var diffuse_light : vec3<f32>;
  var wrap : vec4<f32>;
  var R : vec3<f32>;
  var L : vec3<f32>;
  var half_dir : vec3<f32>;
  var wrapped_NL : vec4<f32>;
  var spec_angle : vec4<f32>;
  var spec_NL : vec4<f32>;
  var L_1 : vec3<f32>;
  var half_dir_1 : vec3<f32>;
  var L_2 : vec3<f32>;
  var half_dir_2 : vec3<f32>;
  var L_3 : vec3<f32>;
  var half_dir_3 : vec3<f32>;
  var gloss : vec4<f32>;
  var shininess : vec4<f32>;
  var spec_light : vec4<f32>;
  var param : vec4<f32>;
  var param_2 : vec4<f32>;
  var param_3 : vec4<f32>;
  var w : vec4<f32>;
  var spec_env : vec4<f32>;
  var param_4 : vec4<f32>;
  var param_5 : vec4<f32>;
  var NV : f32;
  var param_6 : vec3<f32>;
  var param_7 : f32;
  var param_8 : f32;
  var diff_NL : vec4<f32>;
  var diff_light : vec4<f32>;
  var param_9 : vec4<f32>;
  var param_10 : vec4<f32>;
  var spec_energy : f32;
  if ((v_2.world_data.use_specular != 0u)) {
    let v_31 = *(base_color);
    let v_32 = *(metallic);
    diffuse_color = mix(v_31, vec3<f32>(), vec3<f32>(v_32, v_32, v_32));
    let v_33 = *(base_color);
    let v_34 = *(metallic);
    specular_color = mix(vec3<f32>(0.05000000074505805969f), v_33, vec3<f32>(v_34, v_34, v_34));
  } else {
    diffuse_color = *(base_color);
    specular_color = vec3<f32>();
  }
  specular_light = v_2.world_data.ambient_color.xyz;
  diffuse_light = v_2.world_data.ambient_color.xyz;
  wrap = vec4<f32>(v_2.world_data.lights[0i].diffuse_color_wrap.w, v_2.world_data.lights[1i].diffuse_color_wrap.w, v_2.world_data.lights[2i].diffuse_color_wrap.w, v_2.world_data.lights[3i].diffuse_color_wrap.w);
  if ((v_2.world_data.use_specular != 0u)) {
    R = -(reflect(*(I), *(N)));
    L = v_2.world_data.lights[0i].direction.xyz;
    half_dir = normalize((L + *(I)));
    wrapped_NL.x = dot(L, R);
    spec_angle.x = clamp(dot(half_dir, *(N)), 0.0f, 1.0f);
    spec_NL.x = clamp(dot(L, *(N)), 0.0f, 1.0f);
    L_1 = v_2.world_data.lights[1i].direction.xyz;
    half_dir_1 = normalize((L_1 + *(I)));
    wrapped_NL.y = dot(L_1, R);
    spec_angle.y = clamp(dot(half_dir_1, *(N)), 0.0f, 1.0f);
    spec_NL.y = clamp(dot(L_1, *(N)), 0.0f, 1.0f);
    L_2 = v_2.world_data.lights[2i].direction.xyz;
    half_dir_2 = normalize((L_2 + *(I)));
    wrapped_NL.z = dot(L_2, R);
    spec_angle.z = clamp(dot(half_dir_2, *(N)), 0.0f, 1.0f);
    spec_NL.z = clamp(dot(L_2, *(N)), 0.0f, 1.0f);
    L_3 = v_2.world_data.lights[3i].direction.xyz;
    half_dir_3 = normalize((L_3 + *(I)));
    wrapped_NL.w = dot(L_3, R);
    spec_angle.w = clamp(dot(half_dir_3, *(N)), 0.0f, 1.0f);
    spec_NL.w = clamp(dot(L_3, *(N)), 0.0f, 1.0f);
    let v_35 = (1.0f - *(roughness));
    gloss = vec4<f32>(v_35, v_35, v_35, v_35);
    let v_36 = (vec4<f32>(1.0f, 1.0f, 1.0f, 1.0f) - wrap);
    gloss = (gloss * v_36);
    shininess = exp2(((gloss * 10.0f) + vec4<f32>(1.0f, 1.0f, 1.0f, 1.0f)));
    param = shininess;
    param_2 = spec_angle;
    param_3 = spec_NL;
    spec_light = v_28(&(param), &(param_2), &(param_3));
    let v_37 = wrap;
    let v_38 = *(roughness);
    w = mix(v_37, vec4<f32>(1.0f), vec4<f32>(v_38, v_38, v_38, v_38));
    param_4 = wrapped_NL;
    param_5 = w;
    spec_env = v_29(&(param_4), &(param_5));
    spec_light = mix(spec_light, spec_env, (wrap * wrap));
    let v_39 = spec_light.x;
    let v_40 = (v_2.world_data.lights[0i].specular_color.xyz * v_39);
    specular_light = (specular_light + v_40);
    let v_41 = spec_light.y;
    let v_42 = (v_2.world_data.lights[1i].specular_color.xyz * v_41);
    specular_light = (specular_light + v_42);
    let v_43 = spec_light.z;
    let v_44 = (v_2.world_data.lights[2i].specular_color.xyz * v_43);
    specular_light = (specular_light + v_44);
    let v_45 = spec_light.w;
    let v_46 = (v_2.world_data.lights[3i].specular_color.xyz * v_45);
    specular_light = (specular_light + v_46);
    NV = clamp(dot(*(N), *(I)), 0.0f, 1.0f);
    param_6 = specular_color;
    param_7 = *(roughness);
    param_8 = NV;
    specular_color = v_25(&(param_6), &(param_7), &(param_8));
  }
  let v_47 = specular_color;
  specular_light = (specular_light * v_47);
  diff_NL.x = dot(v_2.world_data.lights[0i].direction.xyz, *(N));
  diff_NL.y = dot(v_2.world_data.lights[1i].direction.xyz, *(N));
  diff_NL.z = dot(v_2.world_data.lights[2i].direction.xyz, *(N));
  diff_NL.w = dot(v_2.world_data.lights[3i].direction.xyz, *(N));
  param_9 = diff_NL;
  param_10 = wrap;
  diff_light = v_29(&(param_9), &(param_10));
  let v_48 = diff_light.x;
  let v_49 = (v_2.world_data.lights[0i].diffuse_color_wrap.xyz * v_48);
  diffuse_light = (diffuse_light + v_49);
  let v_50 = diff_light.y;
  let v_51 = (v_2.world_data.lights[1i].diffuse_color_wrap.xyz * v_50);
  diffuse_light = (diffuse_light + v_51);
  let v_52 = diff_light.z;
  let v_53 = (v_2.world_data.lights[2i].diffuse_color_wrap.xyz * v_52);
  diffuse_light = (diffuse_light + v_53);
  let v_54 = diff_light.w;
  let v_55 = (v_2.world_data.lights[3i].diffuse_color_wrap.xyz * v_54);
  diffuse_light = (diffuse_light + v_55);
  spec_energy = dot(specular_color, vec3<f32>(0.33333000540733337402f));
  let v_56 = (diffuse_color * (1.0f - spec_energy));
  diffuse_light = (diffuse_light * v_56);
  return (diffuse_light + specular_light);
}

struct workbench_resolve_Resources {
  world : workbench_World,
  cavity : workbench_Cavity,
}

fn v_57() -> workbench_resolve_Resources {
  var r : workbench_resolve_Resources;
  r.world = v_18();
  r.cavity = v_23();
  return r;
}

fn v_3(gl_FragCoord : vec4<f32>) {
  var srt : workbench_resolve_Resources;
  var uv : vec2<f32>;
  var depth : f32;
  var P : vec3<f32>;
  var param : vec3<f32>;
  var V : vec3<f32>;
  var param_11 : vec3<f32>;
  var N : vec3<f32>;
  var param_12 : vec4<f32>;
  var mat_data : vec4<f32>;
  var base_color : vec3<f32>;
  var color : vec4<f32>;
  var roughness : f32;
  var metallic : f32;
  var param_13 : f32;
  var param_14 : f32;
  var param_15 : f32;
  var param_16 : vec3<f32>;
  var param_17 : f32;
  var param_18 : f32;
  var param_19 : vec3<f32>;
  var param_20 : vec3<f32>;
  var cavity : f32;
  var edges : f32;
  var curvature : f32;
  srt = v_57();
  _ = depth_tx_sampler;
  uv = (gl_FragCoord.xy / vec2<f32>(vec2<i32>(textureDimensions(depth_tx_image, 0i))));
  depth = textureSample(depth_tx_image, depth_tx_sampler, uv).x;
  if ((depth == 1.0f)) {
    discard;
    return;
  }
  let v_58 = uv;
  param = vec3<f32>(v_58.x, v_58.y, 0.5f);
  P = v_17(&(param));
  param_11 = P;
  V = v_8(&(param_11));
  param_12 = textureSample(normal_tx_image, normal_tx_sampler, uv);
  N = v_20(&(param_12));
  mat_data = textureSample(material_tx_image, material_tx_sampler, uv);
  base_color = mat_data.xyz;
  color = vec4<f32>(1.0f);
  roughness = 0.0f;
  metallic = 0.0f;
  param_13 = mat_data.w;
  param_14 = roughness;
  param_15 = metallic;
  v_22(&(param_13), &(param_14), &(param_15));
  roughness = param_14;
  metallic = param_15;
  let v_59 = v_19();
  param_16 = base_color;
  param_17 = roughness;
  param_18 = metallic;
  param_19 = N;
  param_20 = V;
  let v_60 = v_30(v_59, &(param_16), &(param_17), &(param_18), &(param_19), &(param_20));
  color.x = v_60.x;
  color.y = v_60.y;
  color.z = v_60.z;
  cavity = 0.0f;
  edges = 0.0f;
  curvature = 0.0f;
  let v_61 = clamp((((1.0f - cavity) * (1.0f + edges)) * (1.0f + curvature)), 0.0f, 4.0f);
  let v_62 = (color.xyz * v_61);
  color.x = v_62.x;
  color.y = v_62.y;
  color.z = v_62.z;
  workbench_resolve_FragOut_color = color;
}

@fragment
fn main(@builtin(position) gl_FragCoord : vec4<f32>) -> @location(0u) vec4<f32> {
  main_inner(gl_FragCoord);
  return workbench_resolve_FragOut_color;
}

