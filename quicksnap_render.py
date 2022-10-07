import bpy, gpu, blf, bgl, logging
from gpu_extras.batch import batch_for_shader
from .quicksnap_utils import State
from .quicksnap_utils import ignore_modifiers
from .quicksnap_utils import revert_modifiers
from mathutils import Vector
import bmesh

logger = logging.getLogger(__name__)

shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
square_indices = ((0, 1), (1, 2), (2, 3), (3, 0))
shader_2d_uniform_color = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
shader_3d_uniform_color = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
shader_3d_smooth_color = gpu.shader.from_builtin('3D_SMOOTH_COLOR')


def draw_square_2d(position_x, position_y, size, color=(1, 1, 0, 1), line_width=1, point_width=3):
    """
    Draw a 2D square of size {size}, color {color}, line_width, and draw 2D point of width {point_width}
    if line_width==0: Only draw point.
    if point_width==0: Only draw square.
    """
    if line_width != 1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if line_width > 0:
        vertices = (
            (position_x - size, position_y - size),
            (position_x + size, position_y - size),
            (position_x + size, position_y + size),
            (position_x - size, position_y + size))

        batch = batch_for_shader(shader_2d_uniform_color, 'LINES', {"pos": vertices}, indices=square_indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
    if point_width > 0:
        bgl.glPointSize(point_width)
        batch = batch_for_shader(shader_2d_uniform_color, 'POINTS', {"pos": [(position_x, position_y)]})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        bgl.glPointSize(5)

    if line_width != 1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)


def draw_line_2d(source_x, source_y, target_x, target_y, color=(1, 1, 0, 1), line_width=1):
    if line_width != 1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    vertices = (
        (source_x, source_y),
        (target_x, target_y))

    batch = batch_for_shader(shader_2d_uniform_color, 'LINES', {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    if line_width != 1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)


def draw_line_3d(source, target, color=(1, 1, 0, 1), line_width=1, depth_test=False):
    if line_width != 1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glEnable(bgl.GL_DEPTH_TEST)
    vertices = (
        (source[0], source[1], source[2]),
        (target[0], target[1], target[2]))

    batch = batch_for_shader(shader_3d_uniform_color, 'LINES', {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    if line_width != 1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glDisable(bgl.GL_DEPTH_TEST)


def draw_line_3d_smooth_blend(source, target, color_a=(1, 0, 0, 1), color_b=(0, 1, 0, 1), line_width=1,
                              depth_test=False):
    if line_width != 1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glEnable(bgl.GL_DEPTH_TEST)
    vertices = (
        (source[0], source[1], source[2]),
        (target[0], target[1], target[2]))
    color_fade = (color_a, color_b)

    batch = batch_for_shader(shader_3d_smooth_color, 'LINES', {"pos": vertices, "color": color_fade})
    shader_3d_smooth_color.bind()
    batch.draw(shader_3d_smooth_color)
    if line_width != 1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glDisable(bgl.GL_DEPTH_TEST)


def draw_points_3d(coords, color=(1, 1, 0, 1), point_width=3, depth_test=False):
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


def draw_callback_2d(self, context):
    # logger.info("draw_callback_2D")
    if self.closest_source_id >= 0:
        closest_position_2d = self.snapdata_source.region_2d[self.closest_source_id]
        source_x, source_y = closest_position_2d[0], closest_position_2d[1]
        # Source selection
        if self.current_state == State.IDLE:  # no source picked
            # logger.info("no source picked")
            draw_square_2d(source_x, source_y, 7)

        else:
            # logger.info(f"source picked . self.target2d={self.target2d} -  self.settings.draw_rubberband={self.settings.draw_rubberband}")
            if self.closest_target_id >= 0:
                color = (0, 1, 0, 1)
            else:
                color = (1, 1, 0, 1)
            if self.settings.draw_rubberband:
                draw_square_2d(source_x, source_y, 7, color=color)
            if self.target2d:
                if self.closest_target_id >= 0:
                    if len(self.snapping) > 0:
                        closest_position_2d = self.snapdata_target.region_2d[self.closest_target_id]
                        draw_square_2d(closest_position_2d[0], closest_position_2d[1], 7,
                                       color=color)  # square to snapped point
                        draw_square_2d(self.target2d[0], self.target2d[1], 7, color=color,
                                       line_width=0)  # dot to target
                    else:
                        draw_square_2d(self.target2d[0], self.target2d[1], 7, color=color)
                else:
                    draw_square_2d(self.target2d[0], self.target2d[1], 7, color=color, line_width=0)  # dot to target

            if self.settings.draw_rubberband and self.target2d:
                draw_line_2d(source_x, source_y, self.target2d[0], self.target2d[1], line_width=1, color=color)


def draw_snap_axis(self, context):
    """
    Draw axis lines depending on QuickSNap operator snapping settings.
    """
    if self.closest_source_id >= 0 and self.snapping != "":
        point_position = self.snapdata_source.world_space[self.closest_source_id]
        if self.snapping_local:
            for object_name in self.selection_objects:
                obj_matrix = bpy.data.objects[object_name].matrix_world

                if 'X' in self.snapping:
                    axis_x = Vector((obj_matrix[0][0], obj_matrix[1][0], obj_matrix[2][0])).normalized()
                    start = point_position + axis_x * 10 ** 5
                    end = point_position - axis_x * 10 ** 5
                    draw_line_3d(start, end, (1, 0.5, 0.5, 0.6), 1)
                if 'Y' in self.snapping:
                    axis_y = Vector((obj_matrix[0][1], obj_matrix[1][1], obj_matrix[2][1])).normalized()
                    start = point_position + axis_y * 10 ** 5
                    end = point_position - axis_y * 10 ** 5
                    draw_line_3d(start, end, (0.5, 1, 0.5, 0.6), 1)
                if 'Z' in self.snapping:
                    axis_z = Vector((obj_matrix[0][2], obj_matrix[1][2], obj_matrix[2][2])).normalized()
                    start = point_position + axis_z * 10 ** 5
                    end = point_position - axis_z * 10 ** 5
                    draw_line_3d(start, end, (0.2, 0.6, 1, 0.6), 1)
        else:
            if 'X' in self.snapping:
                start = point_position.copy()
                start[0] = start[0] + 10 ** 5
                end = point_position.copy()
                end[0] = end[0] - 10 ** 5
                draw_line_3d(start, end, (1, 0.5, 0.5, 0.6), 1)
            if 'Y' in self.snapping:
                start = point_position.copy()
                start[1] = start[1] + 10 ** 5
                end = point_position.copy()
                end[1] = end[1] - 10 ** 5
                draw_line_3d(start, end, (0.5, 1, 0.5, 0.6), 1)
            if 'Z' in self.snapping:
                start = point_position.copy()
                start[2] = start[2] + 10 ** 5
                end = point_position.copy()
                end[2] = end[2] - 10 ** 5
                draw_line_3d(start, end, (0.2, 0.6, 1, 0.6), 1)


def draw_callback_3d(self, context):
    draw_snap_axis(self, context)

    coords = [self.snapdata_target.world_space[objectid] for objectid in self.snapdata_target.origins_map]
    if self.snap_to_origins:
        draw_points_3d(coords, point_width=5)
    else:
        draw_points_3d(coords, color=(1, 1, 0, 0.5), point_width=3, depth_test=True)

    if self.closest_target_id >= 0 and self.settings.highlight_target_vertex_edges:
        vert_index = self.snapdata_target.indices[self.closest_target_id]
        if vert_index < 0:
            return
        vert_object = bpy.data.objects[self.target_object]
        if self.target_object not in self.edge_links:
            self.edge_links[self.target_object] = {}
        if vert_index not in self.edge_links[self.target_object]:
            matrix = vert_object.matrix_world
            # vert_bmesh.from_mesh(vert_object.data)
            if self.target_object in self.selection_objects:
                # vert_bmesh.from_mesh(vert_object.data)
                if self.target_object not in self.target_bmeshs:
                    self.target_bmeshs[self.target_object] = bmesh.from_edit_mesh(vert_object.data)
                vert_bmesh = self.target_bmeshs[self.target_object]
            else:
                if self.target_object not in self.target_bmeshs:
                    self.target_bmeshs[self.target_object] = bmesh.new()  # create an empty BMesh
                    # if self.settings.ignore_modifiers_target and self.settings.ignore_mirror_modifier_target:
                    #     self.target_bmeshs[self.target_object].from_object(vert_object)
                    # else:
                    self.target_bmeshs[self.target_object].from_object(vert_object, context.evaluated_depsgraph_get())
                vert_bmesh = self.target_bmeshs[self.target_object]
            verts = vert_bmesh.verts
            verts.ensure_lookup_table()
            vert = vert_bmesh.verts[vert_index]
            edges = vert.link_edges
            self.edge_links[self.target_object][vert_index]=[]
            for edge in edges:
                if edge.verts[0] == vert:
                    first_vert = 0
                    second_vert = 1
                else:
                    first_vert = 1
                    second_vert = 0
                self.edge_links[self.target_object][vert_index].append((matrix @ edge.verts[first_vert].co,
                                                                        matrix @ edge.verts[second_vert].co))
        for edge in self.edge_links[self.target_object][vert_index]:
            draw_line_3d_smooth_blend(edge[0],
                                      edge[1],
                                      color_a=(1, 1, 0, 1),
                                      color_b=(1, 1, 0, 0),
                                      line_width=1, depth_test=False)
