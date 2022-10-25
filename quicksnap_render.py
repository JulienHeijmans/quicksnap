import bpy, gpu, blf, bgl, logging, bpy_extras
import numpy as np
from gpu_extras.batch import batch_for_shader
from .quicksnap_utils import State
from .quicksnap_utils import dump
from mathutils import Vector

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name_addon__)

shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
square_indices = ((0, 1), (1, 2), (2, 3), (3, 0))
shader_2d_uniform_color = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
shader_3d_uniform_color = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
shader_3d_smooth_color = gpu.shader.from_builtin('3D_SMOOTH_COLOR')


def draw_square_2d(position_x, position_y, size, color=(1, 1, 0, 1), line_width=1, point_width=4):
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


def draw_polygon_smooth_blend(points, indices, color, depth_test):
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glEnable(bgl.GL_DEPTH_TEST)
    colors = [color] * len(points)
    batch = batch_for_shader(shader_3d_smooth_color, 'TRIS', {"pos": points, "color": colors}, indices=indices)
    shader.uniform_float("color", color)
    shader_3d_smooth_color.bind()
    batch.draw(shader_3d_smooth_color)

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
        source_position_3d = self.snapdata_source.world_space[self.closest_source_id]
        source_position_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(context.region,
                                                                              context.space_data.region_3d,
                                                                              source_position_3d)
        # closest_position_2d = self.snapdata_source.region_2d[self.closest_source_id]
        source_x, source_y = source_position_2d[0], source_position_2d[1]
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
            # if self.target2d:
            if self.target is not None:
                target_position_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(context.region,
                                                                                      context.space_data.region_3d,
                                                                                      self.target)
                target_x, target_y = target_position_2d[0], target_position_2d[1]

                if self.closest_target_id >= 0:
                    snap_target_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(
                        context.region,
                        context.space_data.region_3d,
                        self.snapdata_target.world_space[self.closest_target_id])
                    if len(self.snapping) > 0:
                        draw_square_2d(target_x, target_y, 7,
                                       color=color, line_width=0)  # dot to target
                        draw_square_2d(snap_target_2d[0], snap_target_2d[1], 7, color=color)  # square to snapped point
                    else:
                        draw_square_2d(target_x, target_y, 7, color=color)
                else:
                    draw_square_2d(target_x, target_y, 7, color=color,
                                   line_width=0)  # dot to target

                if self.settings.draw_rubberband:
                    draw_line_2d(source_x, source_y, target_x, target_y, line_width=1, color=color)

    elif self.current_state == State.IDLE:
        # Draw grey square when tool is enabled, additional indication that the tool is active
        draw_square_2d(self.mouse_position[0], self.mouse_position[1], 7, color=(1, 1, 1, 0.3), point_width=0)


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


indices_bounds = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)


def draw_bounds(points, color=(1, 1, 0, 1), line_width=3, depth_test=False):
    if line_width != 1:
        bgl.glLineWidth(line_width)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glEnable(bgl.GL_DEPTH_TEST)
    vertices = points

    batch = batch_for_shader(shader_3d_uniform_color, 'LINES', {"pos": vertices}, indices=indices_bounds)
    shader_3d_uniform_color.bind()
    shader_3d_uniform_color.uniform_float("color", color)
    batch.draw(shader_3d_uniform_color)
    if line_width != 1:
        bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glDisable(bgl.GL_LINE_SMOOTH)
    if depth_test:
        bgl.glDisable(bgl.GL_DEPTH_TEST)


def draw_callback_3d(self, context):
    draw_snap_axis(self, context)

    coords = [self.snapdata_target.world_space[objectid] for objectid in self.snapdata_target.origins_map]
    if self.snap_to_origins:
        draw_points_3d(coords, point_width=5)
    elif self.settings.snap_objects_origin == 'ALWAYS':
        draw_points_3d(coords, color=(1, 1, 0, 0.5), point_width=3, depth_test=True)

    if self.settings.highlight_target_vertex_edges or self.settings.display_potential_target_points:
        if self.current_state == State.IDLE:
            if not self.settings.ignore_modifiers and self.hover_object != '' and \
                    self.settings.display_potential_target_points:
                if self.hover_object not in self.source_allowed_indices:
                    if not (self.no_selection and self.object_mode):
                        allowed_indices = self.snapdata_source.indices[:self.snapdata_source.added_points_np]
                        object_indices = self.snapdata_source.object_id[:self.snapdata_source.added_points_np]
                        self.source_allowed_indices[self.hover_object] = allowed_indices[
                            object_indices == self.snapdata_source.scene_meshes.index(self.hover_object)]
                    else:
                        self.source_allowed_indices[self.hover_object] = None
                draw_face_center(context,
                                 target_object=self.hover_object,
                                 face_index=self.target_face_index,
                                 allowed_indices=self.source_allowed_indices[self.hover_object],
                                 snap_type=self.snapdata_source.snap_type,
                                 ignore_modifiers=self.settings.ignore_modifiers or not self.object_mode,
                                 color=context.preferences.themes[0].view_3d.object_active
                                 )
            if self.closest_source_id in self.snapdata_source.origins_map:
                obj_name = self.snapdata_source.origins_map[self.closest_source_id]
                if obj_name not in self.target_bounds:
                    obj = bpy.data.objects[obj_name]
                    bound_points = [v[:] for v in obj.bound_box]

                    region3d = context.space_data.region_3d
                    camera_position = region3d.view_matrix.inverted().translation
                    self.target_bounds[obj_name] = [obj.matrix_world @ Vector(point) for point in bound_points]
                    self.target_bounds[obj_name] = [point + (camera_position - point) * 0.01 for
                                                    point in self.target_bounds[obj_name]]
                draw_bounds(self.target_bounds[obj_name], color=(1, 1, 0, 0.8), line_width=1, depth_test=True)
                return
            if self.settings.highlight_target_vertex_edges:
                draw_edge_highlight(context,
                                    target_object=self.target_object,
                                    target_id=self.closest_source_id,
                                    snapdata=self.snapdata_source,
                                    highlight_data=self.source_highlight_data,
                                    npdata=self.source_npdata,
                                    ignore_modifiers=self.settings.ignore_modifiers or not self.object_mode,
                                    width=self.settings.edge_highlight_width,
                                    color=self.settings.edge_highlight_color_source,
                                    opacity=self.settings.edge_highlight_opacity)

        elif self.current_state == State.SOURCE_PICKED:
            if not self.settings.ignore_modifiers:
                if self.hover_object != '' and self.settings.display_potential_target_points:
                    is_selection = self.hover_object in self.selection_objects
                    if self.hover_object not in self.target_allowed_indices:
                        if is_selection:
                            allowed_indices = self.snapdata_target.indices[:self.snapdata_target.added_points_np]
                            object_indices = self.snapdata_target.object_id[:self.snapdata_target.added_points_np]
                            self.target_allowed_indices[self.hover_object] = \
                                allowed_indices[
                                    object_indices == self.snapdata_target.scene_meshes.index(self.hover_object)]
                        else:
                            self.target_allowed_indices[self.hover_object] = None
                    draw_face_center(context,
                                     target_object=self.hover_object,
                                     face_index=self.target_face_index,
                                     allowed_indices=self.target_allowed_indices[self.hover_object],
                                     snap_type=self.snapdata_target.snap_type,
                                     ignore_modifiers=self.settings.ignore_modifiers or (
                                             is_selection and not self.object_mode),
                                     color=context.preferences.themes[0].view_3d.vertex
                                     )
            if self.closest_target_id in self.snapdata_target.origins_map:
                obj_name = self.snapdata_target.origins_map[self.closest_target_id]
                if obj_name not in self.target_bounds:
                    obj = bpy.data.objects[obj_name]
                    bound_points = [v[:] for v in obj.bound_box]

                    region3d = context.space_data.region_3d
                    camera_position = region3d.view_matrix.inverted().translation
                    self.target_bounds[obj_name] = [obj.matrix_world @ Vector(point) for point in bound_points]
                    self.target_bounds[obj_name] = [point + (camera_position - point) * 0.01 for
                                                    point in self.target_bounds[obj_name]]
                draw_bounds(self.target_bounds[obj_name], color=(1, 1, 0, 0.8), line_width=1, depth_test=True)
                return
            if self.settings.highlight_target_vertex_edges:
                draw_edge_highlight(context,
                                    target_object=self.target_object,
                                    target_id=self.closest_target_id,
                                    snapdata=self.snapdata_target,
                                    highlight_data=self.target_highlight_data,
                                    npdata=self.target_npdata,
                                    ignore_modifiers=self.settings.ignore_modifiers or (
                                            self.target_object in self.selection_objects and not self.object_mode),
                                    width=self.settings.edge_highlight_width,
                                    color=self.settings.edge_highlight_color_target,
                                    opacity=self.settings.edge_highlight_opacity)


def add_camera_offset(co, camera_position, camera_vector, is_ortho):
    cam_point_vector = camera_position - co
    if is_ortho:
        # return co
        return co - camera_vector * np.sqrt(cam_point_vector.dot(cam_point_vector)) * 0.005
    else:
        return co + cam_point_vector * 0.01


def draw_edge_highlight(context,
                        target_object,
                        target_id,
                        snapdata,
                        highlight_data,
                        npdata,
                        ignore_modifiers,
                        width=2,
                        color=(1, 1, 0),
                        opacity=1
                        ):
    if target_id >= 0:
        if len(snapdata.indices) <= target_id:
            return
        vert_index = snapdata.indices[target_id]
        if vert_index < 0:
            return
        vert_object = bpy.data.objects[target_object]
        if vert_object.type != "MESH":
            return
        if target_object not in highlight_data:
            highlight_data[target_object] = {}
        if vert_index not in highlight_data[target_object]:
            matrix = vert_object.matrix_world
            if ignore_modifiers:
                data = vert_object.data
            else:
                data = vert_object.evaluated_get(context.evaluated_depsgraph_get()).data

            if snapdata.snap_type == 'POINTS':
                if target_object not in npdata:
                    npdata[target_object] = {}
                if "edge_verts" not in npdata[target_object]:
                    arr = np.zeros(len(data.edges) * 2, dtype=np.int)
                    data.edges.foreach_get('vertices', arr)
                    arr.shape = (len(data.edges), 2)
                    npdata[target_object]["edge_verts"] = arr

                filter_left = npdata[target_object]["edge_verts"][
                    npdata[target_object]["edge_verts"][:, 0] == vert_index]
                filter_right = npdata[target_object]["edge_verts"][
                    npdata[target_object]["edge_verts"][:, 1] == vert_index]
                highlight_data[target_object][vert_index] = {}
                highlight_data[target_object][vert_index]["edges"] = []
                for match in filter_left:
                    highlight_data[target_object][vert_index]["edges"].append((matrix @ data.vertices[match[0]].co,
                                                                               matrix @ data.vertices[match[1]].co))
                for match in filter_right:
                    highlight_data[target_object][vert_index]["edges"].append((matrix @ data.vertices[match[1]].co,
                                                                               matrix @ data.vertices[match[0]].co))
            elif snapdata.snap_type == 'MIDPOINTS':
                verts = data.vertices
                edges = data.edges
                if len(edges) <= vert_index:
                    return
                highlight_data[target_object][vert_index] = {}
                highlight_data[target_object][vert_index]["edges"] = []
                highlight_data[target_object][vert_index]["edges"].append(
                    (snapdata.world_space[target_id],
                     matrix @ verts[edges[vert_index].vertices[0]].co))
                highlight_data[target_object][vert_index]["edges"].append(
                    (snapdata.world_space[target_id],
                     matrix @ verts[edges[vert_index].vertices[1]].co))

            elif snapdata.snap_type == 'FACES':
                if target_object not in npdata:
                    npdata[target_object] = {}
                if "polygon_loop_tri_idx" not in npdata[target_object]:
                    data.calc_loop_triangles()
                    arr = np.zeros(len(data.loop_triangles), dtype=np.int)
                    data.loop_triangles.foreach_get('polygon_index', arr)
                    npdata[target_object]["polygon_loop_tri_idx"] = arr
                    arr2 = np.zeros(len(data.loop_triangles) * 3, dtype=np.int)
                    data.loop_triangles.foreach_get('vertices', arr2)
                    arr2.shape = (len(data.loop_triangles), 3)
                    npdata[target_object]["polygon_loop_verts"] = arr2

                verts = data.vertices
                polygons = data.polygons
                loops = data.loops
                highlight_data[target_object][vert_index] = {}
                highlight_data[target_object][vert_index]["edges"] = []
                highlight_data[target_object][vert_index]["face_co"] = []
                highlight_data[target_object][vert_index]["face_indices"] = []
                if len(polygons) <= vert_index:
                    return
                poly = polygons[vert_index]
                region3d = context.space_data.region_3d
                camera_position = region3d.view_matrix.inverted().translation
                camera_vector = region3d.view_rotation @ Vector((0.0, 0.0, -1.0))
                is_ortho = region3d.view_perspective == 'ORTHO'

                vert_local_index = {}
                verts_co = {}
                for idx in range(0, poly.loop_total):
                    current_loop = poly.loop_start + idx
                    loop_second = poly.loop_start + ((idx + 1) % poly.loop_total)
                    vert_index_a = loops[current_loop].vertex_index
                    vert_index_b = loops[loop_second].vertex_index
                    if vert_index_a not in verts_co:
                        verts_co[vert_index_a] = matrix @ verts[vert_index_a].co
                        verts_co[vert_index_a] = add_camera_offset(verts_co[vert_index_a],
                                                                   camera_position,
                                                                   camera_vector,
                                                                   is_ortho)
                        new_index = len(highlight_data[target_object][vert_index]["face_co"])
                        vert_local_index[vert_index_a] = new_index
                        highlight_data[target_object][vert_index]["face_co"].append(verts_co[vert_index_a])
                    if vert_index_b not in verts_co:
                        verts_co[vert_index_b] = matrix @ verts[vert_index_b].co
                        verts_co[vert_index_b] = add_camera_offset(verts_co[vert_index_b],
                                                                   camera_position,
                                                                   camera_vector,
                                                                   is_ortho)

                        new_index = len(highlight_data[target_object][vert_index]["face_co"])
                        vert_local_index[vert_index_b] = new_index
                        highlight_data[target_object][vert_index]["face_co"].append(verts_co[vert_index_b])
                    highlight_data[target_object][vert_index]["edges"].append(
                        (verts_co[vert_index_a], verts_co[vert_index_b]))

                filtered = np.argwhere(npdata[target_object]["polygon_loop_tri_idx"] == vert_index)
                for triangle_index in filtered:
                    triangle = npdata[target_object]["polygon_loop_verts"][triangle_index].flatten()
                    highlight_data[target_object][vert_index]["face_indices"].extend(
                        [[vert_local_index[vertid] for vertid in triangle]])

        if snapdata.snap_type == 'POINTS':
            alpha_end = 0
        else:
            alpha_end = opacity

        for edge in highlight_data[target_object][vert_index]["edges"]:
            draw_line_3d_smooth_blend(edge[0],
                                      edge[1],
                                      color_a=(*color, opacity),
                                      color_b=(*color, alpha_end),
                                      line_width=width, depth_test=False)
        if snapdata.snap_type == 'FACES':
            draw_polygon_smooth_blend(highlight_data[target_object][vert_index]["face_co"],
                                      highlight_data[target_object][vert_index]["face_indices"],
                                      color=(*color, 0.1),
                                      depth_test=True)


def draw_face_center(context,
                     target_object,
                     face_index,
                     allowed_indices,
                     snap_type,
                     ignore_modifiers,
                     color):
    if face_index < 0 or snap_type == 'POINTS' or target_object == '':
        return
    obj = bpy.data.objects[target_object]
    if obj.type != 'MESH':
        return
    if ignore_modifiers:
        data = obj.data
    else:
        data = obj.evaluated_get(context.evaluated_depsgraph_get()).data

    region3d = context.space_data.region_3d
    camera_position = region3d.view_matrix.inverted().translation
    camera_vector = region3d.view_rotation @ Vector((0.0, 0.0, -1.0))
    is_ortho = region3d.view_perspective == 'ORTHO'
    if snap_type == 'FACES':
        # and face_index in allowed_indices
        # print(f"face index:{face_index}")
        # print(f"len(data.polygons):{len(data.polygons)}")
        if face_index < len(data.polygons) and (allowed_indices is None or face_index in allowed_indices):
            target_polygon = data.polygons[face_index]
            center = obj.matrix_world @ target_polygon.center
            region3d = context.space_data.region_3d
            camera_position = region3d.view_matrix.inverted().translation
            center = add_camera_offset(center,
                                       camera_position,
                                       camera_vector,
                                       is_ortho)
            draw_points_3d([center], color=(*color, 1), point_width=4,
                           depth_test=True)

    elif snap_type == 'MIDPOINTS':
        if face_index < len(data.polygons):
            target_polygon = data.polygons[face_index]
            camera_position = context.space_data.region_3d.view_matrix.inverted().translation
            midpoints = []
            for loop_index in range(0, target_polygon.loop_total):
                current_loop = data.loops[target_polygon.loop_start + loop_index]
                if allowed_indices is not None and current_loop.edge_index not in allowed_indices:
                    continue
                loop_second = data.loops[target_polygon.loop_start + ((loop_index + 1) % target_polygon.loop_total)]
                midpoint = obj.matrix_world @ ((data.vertices[current_loop.vertex_index].co +
                                                data.vertices[loop_second.vertex_index].co) / 2)
                midpoint = add_camera_offset(midpoint,
                                             camera_position,
                                             camera_vector,
                                             is_ortho)
                midpoints.append(midpoint)
            draw_points_3d(midpoints, color=(*color, 1), point_width=4, depth_test=True)
