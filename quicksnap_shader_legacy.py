import gpu, bgl
from gpu_extras.batch import batch_for_shader

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
shader_2d_uniform_color = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
shader_3d_uniform_color = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
shader_3d_smooth_color = gpu.shader.from_builtin('3D_SMOOTH_COLOR')
shader_3d_polyline_smooth_color = None


def draw_line_3d_smooth_blend_versionized(points, indices, color, depth_test):
    """
        Draw a smooth blend polygon in the viewport.
    """
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glEnable(bgl.GL_DEPTH_TEST)
    colors = [color] * len(points)
    batch = batch_for_shader(shader_3d_smooth_color, 'TRIS', {"pos": points, "color": colors}, indices=indices)
    shader_3d_smooth_color.bind()
    batch.draw(shader_3d_smooth_color)

    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glDisable(bgl.GL_DEPTH_TEST)

def draw_polygon_smooth_blend_versionized(points, indices, color, depth_test):
    """
        Draw a smooth blend polygon in the viewport.
    """
    gpu.state.blend_set("ALPHA")
    if depth_test:
        gpu.state.depth_test_set("LESS")
    colors = [color] * len(points)
    batch = batch_for_shader(shader_3d_smooth_color, 'TRIS', {"pos": points, "color": colors}, indices=indices)
    shader_3d_smooth_color.bind()
    batch.draw(shader_3d_smooth_color)

    gpu.state.blend_set("NONE")
    if depth_test:
        gpu.state.depth_test_set("NONE")

