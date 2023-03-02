import gpu

shader_2d_image_vertex = '''
        uniform mat4 ModelViewProjectionMatrix;
        in vec2 texCoord;
        in vec2 pos;
        out vec2 texCoord_interp;
        void main()
        {
          gl_Position = ModelViewProjectionMatrix * vec4(pos.xy, 0.0f, 1.0f);
          gl_Position.z = 1.0;
          texCoord_interp = texCoord;
        }
    '''
shader_2d_image_fragment = '''
    uniform vec4 Color;
    uniform vec4 Color_bg;
    uniform float Fade;
    in vec2 texCoord_interp;
    out vec4 fragColor;
    uniform sampler2D Image;
    void main()
    {
      vec4 texture_sampled=texture(Image, texCoord_interp);
      if(texture_sampled.a>0.6)
        fragColor = Color * texture_sampled;
      else
        fragColor = Color_bg * texture_sampled;
      fragColor=vec4(fragColor.r, fragColor.g, fragColor.b, fragColor.a * smoothstep(0,1,Fade));
    }
'''
shader_2d_image_color = gpu.types.GPUShader(shader_2d_image_vertex, shader_2d_image_fragment)
