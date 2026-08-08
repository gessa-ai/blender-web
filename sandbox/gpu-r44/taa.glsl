
#version 450






 





#pragma no_processing

































































































































































































struct string_t {
  uint hash;
};



































































layout(binding = 1, std140) uniform constants
{
  float samplesWeights[9];
};

layout(location = 0) out vec4 frag_color;


 















layout(binding = 0) uniform sampler2D color_buffer; 

































































 



void main()
{
  vec2 texel_size = 1.0f / vec2(textureSize(color_buffer, 0));
  vec2 uv = gl_FragCoord.xy * texel_size;

  frag_color = vec4(0.0f);
  int i = 0;

{

                                           {
        {int y = -1;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(-1, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(-1, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(-1, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

    }
  }

                                           {
        {int y = -1;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(0, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(0, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(0, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

    }
  }

                                           {
        {int y = -1;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(1, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(1, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

                                                  {
      vec4 color = texture(color_buffer, uv + vec2(1, y) * texel_size);

      color = clamp(color, vec4(0.0f), vec4(1e10f));

      color.rgb = log2(color.rgb + 1.0f);

      frag_color += color * samplesWeights[i];
    }

                             y++, i++;

    }
  }

  }
}

