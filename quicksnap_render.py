import bpy,gpu,blf,bgl
from gpu_extras.batch import batch_for_shader
from .quicksnap_utils import State
from mathutils import Vector


shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
square_indices=((0, 1), (1, 2), (2, 3), (3, 0))
shader_2d_uniform_color = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
shader_3d_uniform_color = gpu.shader.from_builtin('3D_UNIFORM_COLOR')

def draw_square_2d(posX,posY,size,color=(1, 1, 0, 1),line_width=1,point_width=3):
    if line_width!=1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if line_width>0:
        vertices = (
            (posX-size, posY-size),
            (posX+size, posY-size),
            (posX+size, posY+size),
            (posX-size, posY+size))

        batch = batch_for_shader(shader_2d_uniform_color, 'LINES', {"pos": vertices},indices=square_indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
    if(point_width>0):
        bgl.glPointSize(point_width)
        batch = batch_for_shader(shader_2d_uniform_color, 'POINTS', {"pos": [(posX,posY)]})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        bgl.glPointSize(5)

    if line_width!=1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)

def draw_line_2d(sourceX,sourceY,target_X,target_Y,color=(1, 1, 0, 1),line_width=1):
    if line_width!=1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    vertices = (
        (sourceX,sourceY),
        (target_X,target_Y))

    batch = batch_for_shader(shader_2d_uniform_color, 'LINES', {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    if line_width!=1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)

def draw_line_3d(source,target,color=(1, 1, 0, 1),line_width=1,depth_test=False):
    if line_width!=1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glEnable(bgl.GL_DEPTH_TEST)
    vertices = (
        (source[0],source[1],source[2]),
        (target[0],target[1],target[2]))

    batch = batch_for_shader(shader_3d_uniform_color, 'LINES', {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    if line_width!=1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glDisable(bgl.GL_DEPTH_TEST)

def draw_points_3d(coords,color=(1, 1, 0, 1),point_width=3,depth_test=False):
    print(f"draw_points_3d: {coords}")
    bgl.glEnable(bgl.GL_BLEND)
    if depth_test:
        bgl.glEnable(bgl.GL_DEPTH_TEST)

    bgl.glPointSize(point_width)
    batch = batch_for_shader(shader_3d_uniform_color, 'POINTS', {"pos": coords})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    bgl.glPointSize(5)
    
    bgl.glDisable(bgl.GL_BLEND)
    if depth_test:
        bgl.glDisable(bgl.GL_DEPTH_TEST)


def draw_callback_2D(self, context):

    if self.closest_source_id>=0:
        closest_position_2d=self.vertex_source_data_v2.region_2d[self.closest_source_id]
        source_x, source_y = closest_position_2d[0],closest_position_2d[1]
        #Source selection
        if not self.current_state==State.SOURCE_PICKED:#no source picked
            draw_square_2d(source_x,source_y,7)
            # # draw some text
            # font_id = 0  # XXX, need to find out how best to get this.
            # font_offset = 10
            # blf.position(font_id, source_x+font_offset, source_y-font_offset*2, 0)
            # blf.size(font_id, 20, 72)
            # blf.draw(font_id, f'Distance={self.distance}')

        else:
            
            if self.closest_target_id>=0:
                # font_id = 0  # XXX, need to find out how best to get this.
                # font_offset = 10
                # blf.position(font_id, source_x+font_offset, source_y-font_offset*2, 0)
                # blf.size(font_id, 20, 72)
                # blf.draw(font_id, f'Picked - target_id={self.closest_target_id} - obstructed={self.vertex_target_data_v2.obstructed[self.closest_target_id]}')
                color=(0, 1, 0, 1)
            else:
                color=(1, 1, 0, 1)
            draw_square_2d(source_x,source_y,7,color=color)
            if self.target2d:
                if self.closest_target_id>=0:
                    if len(self.snapping)>0 :
                        closest_position_2d=self.vertex_target_data_v2.region_2d[self.closest_target_id]
                        draw_square_2d(closest_position_2d[0],closest_position_2d[1],7,color=color) #square to snapped point 
                        draw_square_2d(self.target2d[0],self.target2d[1],7,color=color,line_width=0)#dot to target
                    else:
                        draw_square_2d(self.target2d[0],self.target2d[1],7,color=color)
                else:
                    draw_square_2d(self.target2d[0],self.target2d[1],7,color=color,line_width=0)#dot to target




            if self.settings.draw_rubberband and self.target2d:
                draw_line_2d(source_x, source_y,self.target2d[0], self.target2d[1],line_width=1,color=color)


def draw_snap_axis(self, context):
    if self.closest_source_id>=0 and self.snapping!="":
        point_position= self.vertex_source_data_v2.world_space[self.closest_source_id]
        if self.snapping_local:
            for object_name in self.selection_meshes:
                obj_matrix=bpy.data.objects[object_name].matrix_world

                if 'X' in self.snapping:
                    axis_x=Vector((obj_matrix[0][0], obj_matrix[1][0], obj_matrix[2][0])).normalized()
                    start=point_position+axis_x*10**5
                    end=point_position-axis_x*10**5
                    draw_line_3d(start,end,(1,0.5,0.5,0.6),1)
                if 'Y' in self.snapping:
                    axis_y=Vector((obj_matrix[0][1], obj_matrix[1][1], obj_matrix[2][1])).normalized()
                    start=point_position+axis_y*10**5
                    end=point_position-axis_y*10**5
                    draw_line_3d(start,end,(0.5,1,0.5,0.6),1)
                if 'Z' in self.snapping:
                    axis_z=Vector((obj_matrix[0][2], obj_matrix[1][2], obj_matrix[2][2])).normalized()
                    start=point_position+axis_z*10**5
                    end=point_position-axis_z*10**5
                    draw_line_3d(start,end,(0.2,0.6,1,0.6),1)
        else:
            if 'X' in self.snapping:
                start=point_position.copy()
                start.x=start.x+10**5
                end=point_position.copy()
                end.x=end.x-10**5
                draw_line_3d(start,end,(1,0.5,0.5,0.6),1)
            if 'Y' in self.snapping:
                start=point_position.copy()
                start.y=start.y+10**5
                end=point_position.copy()
                end.y=end.y-10**5
                draw_line_3d(start,end,(0.5,1,0.5,0.6),1)
            if 'Z' in self.snapping:
                start=point_position.copy()
                start.z=start.z+10**5
                end=point_position.copy()
                end.z=end.z-10**5
                draw_line_3d(start,end,(0.2,0.6,1,0.6),1)


def draw_callback_3D(self, context):
    draw_snap_axis(self,context)
    coords=[self.vertex_target_data_v2.world_space[objectid] for objectid in self.vertex_target_data_v2.origins_map]
    if self.snap_to_origins:
        draw_points_3d(coords,point_width=5)
    else:
        draw_points_3d(coords,color=(1,1,0,0.5),point_width=3,depth_test=True)
        
