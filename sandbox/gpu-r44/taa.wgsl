
diagnostic(off, derivative_uniformity);
diagnostic(off, chromium.unreachable_code);

@group(0u) @binding(256u) var color_buffer_sampler : sampler;

@group(0u) @binding(0u) var color_buffer_image : texture_2d<f32>;

var<private> frag_color : vec4<f32>;

struct tint_padded_array_element {
  @size(16u)
  tint_element : f32,
}

struct constants_1 {
  samplesWeights : array<tint_padded_array_element, 9u>,
}

@group(0u) @binding(1u) var<uniform> v : constants_1;

fn main_inner(gl_FragCoord : vec4<f32>) {
  var texel_size : vec2<f32>;
  var uv : vec2<f32>;
  var i : i32;
  var y : i32;
  var color : vec4<f32>;
  var color_1 : vec4<f32>;
  var color_2 : vec4<f32>;
  var y_1 : i32;
  var color_3 : vec4<f32>;
  var color_4 : vec4<f32>;
  var color_5 : vec4<f32>;
  var y_2 : i32;
  var color_6 : vec4<f32>;
  var color_7 : vec4<f32>;
  var color_8 : vec4<f32>;
  _ = color_buffer_sampler;
  texel_size = (vec2<f32>(1.0f, 1.0f) / vec2<f32>(vec2<i32>(textureDimensions(color_buffer_image, 0i))));
  uv = (gl_FragCoord.xy * texel_size);
  frag_color = vec4<f32>();
  i = 0i;
  y = -1i;
  color = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(-1.0f, f32(y)) * texel_size)));
  color = clamp(color, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_1 = log2((color.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color.x = v_1.x;
  color.y = v_1.y;
  color.z = v_1.z;
  let v_2 = (color * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_2);
  y = (y + 1i);
  i = (i + 1i);
  color_1 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(-1.0f, f32(y)) * texel_size)));
  color_1 = clamp(color_1, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_3 = log2((color_1.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_1.x = v_3.x;
  color_1.y = v_3.y;
  color_1.z = v_3.z;
  let v_4 = (color_1 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_4);
  y = (y + 1i);
  i = (i + 1i);
  color_2 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(-1.0f, f32(y)) * texel_size)));
  color_2 = clamp(color_2, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_5 = log2((color_2.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_2.x = v_5.x;
  color_2.y = v_5.y;
  color_2.z = v_5.z;
  let v_6 = (color_2 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_6);
  y = (y + 1i);
  i = (i + 1i);
  y_1 = -1i;
  color_3 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(0.0f, f32(y_1)) * texel_size)));
  color_3 = clamp(color_3, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_7 = log2((color_3.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_3.x = v_7.x;
  color_3.y = v_7.y;
  color_3.z = v_7.z;
  let v_8 = (color_3 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_8);
  y_1 = (y_1 + 1i);
  i = (i + 1i);
  color_4 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(0.0f, f32(y_1)) * texel_size)));
  color_4 = clamp(color_4, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_9 = log2((color_4.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_4.x = v_9.x;
  color_4.y = v_9.y;
  color_4.z = v_9.z;
  let v_10 = (color_4 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_10);
  y_1 = (y_1 + 1i);
  i = (i + 1i);
  color_5 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(0.0f, f32(y_1)) * texel_size)));
  color_5 = clamp(color_5, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_11 = log2((color_5.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_5.x = v_11.x;
  color_5.y = v_11.y;
  color_5.z = v_11.z;
  let v_12 = (color_5 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_12);
  y_1 = (y_1 + 1i);
  i = (i + 1i);
  y_2 = -1i;
  color_6 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(1.0f, f32(y_2)) * texel_size)));
  color_6 = clamp(color_6, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_13 = log2((color_6.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_6.x = v_13.x;
  color_6.y = v_13.y;
  color_6.z = v_13.z;
  let v_14 = (color_6 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_14);
  y_2 = (y_2 + 1i);
  i = (i + 1i);
  color_7 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(1.0f, f32(y_2)) * texel_size)));
  color_7 = clamp(color_7, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_15 = log2((color_7.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_7.x = v_15.x;
  color_7.y = v_15.y;
  color_7.z = v_15.z;
  let v_16 = (color_7 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_16);
  y_2 = (y_2 + 1i);
  i = (i + 1i);
  color_8 = textureSample(color_buffer_image, color_buffer_sampler, (uv + (vec2<f32>(1.0f, f32(y_2)) * texel_size)));
  color_8 = clamp(color_8, vec4<f32>(), vec4<f32>(10000000000.0f));
  let v_17 = log2((color_8.xyz + vec3<f32>(1.0f, 1.0f, 1.0f)));
  color_8.x = v_17.x;
  color_8.y = v_17.y;
  color_8.z = v_17.z;
  let v_18 = (color_8 * v.samplesWeights[i].tint_element);
  frag_color = (frag_color + v_18);
  y_2 = (y_2 + 1i);
  i = (i + 1i);
}

@fragment
fn main(@builtin(position) gl_FragCoord : vec4<f32>) -> @location(0u) vec4<f32> {
  main_inner(gl_FragCoord);
  return frag_color;
}

