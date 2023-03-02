import gpu

shader_3d_polyline_smooth_color = gpu.shader.from_builtin('POLYLINE_SMOOTH_COLOR')

shader_2d_image_info = gpu.types.GPUShaderCreateInfo()

# Vertex shader inputs and uniforms that are now called constants.
shader_2d_image_info.vertex_in(0, 'VEC2', "texCoord")
shader_2d_image_info.vertex_in(1, 'VEC2', "pos")
shader_2d_image_info.sampler(0, 'FLOAT_2D', "Image")
shader_2d_image_info.push_constant('MAT4', "ModelViewProjectionMatrix")
shader_2d_image_info.push_constant('VEC4', "Color")
shader_2d_image_info.push_constant('VEC4', "Color_bg")
shader_2d_image_info.push_constant('FLOAT', "Fade")

# Define as Interface the attributes that will be transferred from the vertex shader to the fragment shader.
# Before they would be both a vertex shader output and fragment shader input.
# An interface can be flat(), no_perspective() or smooth()
shader_2d_image_interface = gpu.types.GPUStageInterfaceInfo("shader_2d_image_interface")
shader_2d_image_interface.smooth('VEC2', "texCoord_interp")
shader_2d_image_info.vertex_out(shader_2d_image_interface)

# fragment shader output
shader_2d_image_info.fragment_out(0, 'VEC4', 'fragColor')

shader_2d_image_info.vertex_source(
    '''
    void main()
    {
      gl_Position = ModelViewProjectionMatrix * vec4(pos.xy, 0.0f, 1.0f);
      gl_Position.z = 1.0;
      texCoord_interp = texCoord;
    }
    ''')
shader_2d_image_info.fragment_source(
    '''
    void main()
    {
      vec4 texture_sampled=texture(Image, texCoord_interp);
      if(texture_sampled.a>0.6)
        fragColor = Color * texture_sampled;
      else
        fragColor = Color_bg * texture_sampled;
      fragColor=vec4(fragColor.r, fragColor.g, fragColor.b, fragColor.a * smoothstep(0,1,Fade));
    }

    ''')
shader_2d_image_color = gpu.shader.create_from_info(shader_2d_image_info)
del shader_2d_image_info
del shader_2d_image_interface
