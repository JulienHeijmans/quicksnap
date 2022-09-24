import bmesh
import bpy
import logging
import mathutils
from bpy_extras import view3d_utils
from mathutils import Vector

from . import quicksnap_render
from . import quicksnap_utils
from .quicksnap_snapdata import SnapData
from .quicksnap_utils import State

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name__)
addon_keymaps = []

mouse_pointer_offsets = [
    Vector((-40, -40)),
    Vector((-40, 0)),
    Vector((-40, 40)),
    Vector((0, 40)),
    Vector((40, 40)),
    Vector((40, 0)),
    Vector((40, -40)),
    Vector((0, -40))
]


class QuickVertexSnapOperator(bpy.types.Operator):
    bl_idname = "object.quick_vertex_snap"
    bl_label = "Quick Vertex Snap"
    bl_options = {'INTERNAL', 'UNDO'}

    @staticmethod
    def get_target_operator(context):
        wm = context.window_manager
        op = wm.operators[-1] if wm.operators else None
        if op:
            if op.bl_idname == "TRANSFORM_OT_translate":
                return op
            #     print(f"OP= {op.bl_idname} - searching for: {type(bpy.ops.transform.translate)}")
            # if isinstance(op, type(bpy.ops.transform.translate())):
            else:
                print(f"{op.bl_idname} != TRANSFORM_OT_translate")
        return None

    def initialize(self, context):
        logger.info("Initialize")

        # Get 'WINDOW' region of the context. Useful when the active context region is UI within the 3DView
        region = None
        for region_item in context.area.regions:
            if region_item.type == 'WINDOW':
                region = region_item

        if not region:
            return False  # If no window region, cancel the operation.

        # Get selection, if false cancel operation
        self.selection_meshes = [obj.name for obj in quicksnap_utils.get_selection_meshes()]
        if not self.selection_meshes or len(self.selection_meshes) == 0:
            return False

        self.object_mode = bpy.context.active_object.mode == 'OBJECT'

        # Create SnapData objects that will store all the vertex/point info (World space, view space, and kdtree to
        # search the closest point)
        self.snapdata_source = SnapData(context, region, self.selection_meshes)
        self.snapdata_target = SnapData(context, region, self.selection_meshes,
                                        quicksnap_utils.get_scene_meshes(True))

        # Store 3DView camera information.
        region3d = context.space_data.region_3d
        self.camera_position = region3d.view_matrix.inverted().translation
        self.mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d,
                                                                self.mouse_position)
        self.perspective_matrix = context.space_data.region_3d.perspective_matrix
        self.perspective_matrix_inverse = self.perspective_matrix.inverted()

        self.backup_data(context)
        self.update(context, region)
        context.area.header_text_set(f"QuickSnap: Pick a vertex/point from the selection to start move-snapping")
        return True

    def backup_data(self, context):
        """
        Backup vertices/curve points positions if in Object mode, otherwise backup object positions.
        """
        self.backup_object_positions = {}
        if self.object_mode:
            selection = quicksnap_utils.keep_only_parents(
                [bpy.data.objects[obj_name] for obj_name in self.selection_meshes])
            for obj in selection:
                self.backup_object_positions[obj.name] = obj.matrix_world.copy()
        else:
            self.backup_vertices_positions = {}
            self.bmeshs = {}
            for object_name in self.snapdata_source.selected_ids:
                obj = bpy.data.objects[object_name]
                if obj.type == "MESH":
                    self.bmeshs[object_name] = bmesh.new()
                    self.bmeshs[object_name].from_mesh(obj.data)
                    # self.backup_vertices_positions[object_name] = [(index, co, 0, 0, 0, 0) for (index, co, _, _) in
                    #                                                self.snapdata_source.selected_ids[object_name]]
                elif obj.type == "CURVE":
                    self.backup_vertices_positions[object_name] = []
                    for (index, co, spline_index, bezier) in self.snapdata_source.selected_ids[object_name]:
                        if bezier == 1:
                            point = obj.data.splines[spline_index].bezier_points[index]
                            logger.info(
                                f"Backup point: {point.co} - handles: {point.handle_left} - {point.handle_right}")
                            self.backup_vertices_positions[object_name].append((spline_index, index, co.copy(), bezier,
                                                                                point.handle_left.copy(),
                                                                                point.handle_right.copy()))
                        else:
                            point = obj.data.splines[spline_index].points[index]
                            self.backup_vertices_positions[object_name].append(
                                (spline_index, index, co.copy(), bezier, 0, 0))

    def set_target_object(self, target_object="", is_root=False, force=True):
        """
        Defines the target object.
        Enables wireframe/bounds/display name on the target object and disable all that on the previous target object
        """
        if self.target_object == target_object and not force:
            if self.target_object_is_root != is_root:
                bpy.data.objects[
                    self.target_object].show_texture_space = is_root or self.target_object_show_texture_space_backup
                bpy.data.objects[self.target_object].show_name = is_root or self.target_object_show_name_backup
                self.target_object_is_root = is_root
            return
        if self.target_object != "":
            bpy.data.objects[self.target_object].show_wire = self.target_object_show_wire_backup
            bpy.data.objects[self.target_object].show_texture_space = self.target_object_show_texture_space_backup
            bpy.data.objects[self.target_object].show_name = self.target_object_show_name_backup
        if target_object != "":
            self.target_object_show_wire_backup = bpy.data.objects[target_object].show_wire
            self.target_object_show_name_backup = bpy.data.objects[target_object].show_name
            self.target_object_show_texture_space_backup = bpy.data.objects[target_object].show_texture_space
            bpy.data.objects[target_object].show_wire = self.settings.display_target_wireframe
            if is_root:
                bpy.data.objects[target_object].show_texture_space = True
                bpy.data.objects[target_object].show_name = True
        self.target_object = target_object
        self.target_object_is_root = is_root

    def revert_data(self, context, apply=False):
        """
        Revert the backed up data (vertx/curve points positions if in EDIT mode, objects locations if in OBJECT mode)
        """
        if self.object_mode:
            for object_name in self.backup_object_positions:
                bpy.data.objects[object_name].matrix_world = self.backup_object_positions[object_name].copy()
        else:
            # If the operation is not cancelled, simply move the selection back.
            if not apply and self.last_translation is not None:
                bpy.ops.transform.translate(value=self.last_translation * -1, orient_type='GLOBAL')
                return
            # Otherwise, properly revert all vertex/points data.
            object_mode_backup = quicksnap_utils.set_object_mode_if_needed()
            for object_name in self.backup_vertices_positions:
                obj = bpy.data.objects[object_name]
                if obj.type == "MESH":
                    self.bmeshs[object_name].to_mesh(bpy.data.objects[object_name].data)
                elif obj.type == "CURVE" and apply:
                    data = obj.data
                    for (curveindex, index, co, bezier, left, right) in self.backup_vertices_positions[object_name]:
                        if bezier == 1:
                            data.splines[curveindex].bezier_points[index].co = co
                            data.splines[curveindex].bezier_points[index].handle_left = left
                            data.splines[curveindex].bezier_points[index].handle_right = right
                        else:
                            data.splines[curveindex].points[index].co = Vector(
                                (co[0], co[1], co[2], data.splines[curveindex].points[index].co[3]))

            quicksnap_utils.revert_mode(object_mode_backup)

    def update(self, context, region):
        """
        Main Update Loop
        """

        # Update 3DView camera information
        region3d = context.space_data.region_3d
        self.camera_position = region3d.view_matrix.inverted().translation
        self.mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d,
                                                                self.mouse_position)
        mouse_coord_screen_flat = Vector((self.mouse_position[0], self.mouse_position[1], 0))

        search_obstructed = context.space_data.shading.show_xray or not self.settings.filter_search_obstructed
        depsgraph = context.evaluated_depsgraph_get()
        if self.current_state == State.IDLE:
            # Find object under the mouse
            (direct_hit, _, _, _, direct_hit_object, _) = context.scene.ray_cast(context.evaluated_depsgraph_get(),
                                                                                 origin=self.camera_position,
                                                                                 direction=self.mouse_vector)
            # If found, we push this object on top of the stack of objects to process
            if direct_hit and direct_hit_object.name in self.selection_meshes:
                self.snapdata_source.add_mesh_target(context,
                                                     direct_hit_object.name,
                                                     depsgraph=depsgraph,
                                                     is_selected=True,
                                                     set_first_priority=True)

            # Find source vert/point the closest to the mouse, change cursor crosshair
            closest = self.snapdata_source.find_closest(mouse_coord_screen_flat,
                                                        search_obstructed=search_obstructed,
                                                        search_origins_only=self.snap_to_origins)
            if closest is not None:
                (self.closest_source_id, self.distance, target_name, is_root) = closest
                self.set_target_object(target_name, is_root)
                if self.distance <= 15:
                    self.closest_actionable = True  # Points too far from the mouse are highlighted but can't be moved
                    bpy.context.window.cursor_set("SCROLL_XY")
                else:
                    self.closest_actionable = False
                    bpy.context.window.cursor_set("CROSSHAIR")
            else:
                self.closest_source_id = -1
                self.set_target_object("")
                self.distance = -1
                self.closest_actionable = False
                bpy.context.window.cursor_set("CROSSHAIR")

        elif self.current_state == State.SOURCE_PICKED:
            # If we are only snapping to origins, only search through origin points.
            if self.snap_to_origins:
                closest = self.snapdata_target.find_closest(mouse_coord_screen_flat, search_origins_only=True)
                if closest is not None:
                    (self.closest_target_id, self.distance, target_object_name, is_root) = closest
                    self.set_target_object(target_object_name, is_root)
                else:
                    self.closest_target_id = -1
                    self.distance = -1
                    self.set_target_object("")

            else:  # Snapping to all verts/points

                # First hide the selection mesh not to raycast against it.
                for obj in self.selection_meshes:
                    bpy.data.objects[obj].hide_set(True)

                # Now we will search for other objects to process around the mouse.
                for obj in self.snapdata_target.processed:  # Hide already processed meshes
                    bpy.data.objects[obj].hide_set(True)

                # Look for close objects (8 raycasts 40px around the mouse cursor)
                close_objects = self.check_close_objects(context, region, depsgraph)
                for obj in self.snapdata_target.processed:  # un-hiding processed objects, for obstruction check
                    bpy.data.objects[obj].hide_set(False)
                # Add the close objects to the to-process list
                for obj in close_objects:
                    self.snapdata_target.add_mesh_target(context, obj.name, depsgraph=depsgraph,
                                                         set_first_priority=True)

                # Look for object under the mouse, if found, bring it in top of the list of objects to process.
                (direct_hit, _, _, _, direct_hit_object, _) = context.scene.ray_cast(depsgraph,
                                                                                     origin=self.camera_position,
                                                                                     direction=self.mouse_vector)
                if direct_hit:
                    self.snapdata_target.add_mesh_target(context, direct_hit_object.name, depsgraph=depsgraph,
                                                         set_first_priority=True)

                # Revert hidden objects
                for obj in self.selection_meshes:
                    bpy.data.objects[obj].hide_set(False)
                for obj in self.selection_meshes:  # re-select selection that might be lost in previous steps
                    bpy.data.objects[obj].select_set(True)

                # Find the closest target points
                closest = self.snapdata_target.find_closest(mouse_coord_screen_flat,
                                                            search_obstructed=search_obstructed)
                if closest is not None:
                    (self.closest_target_id, self.distance, target_object_name, is_root) = closest
                    self.set_target_object(target_object_name, is_root)
                else:
                    self.closest_target_id = -1
                    self.distance = -1
                    self.set_target_object("")

    def check_close_objects(self, context, region, depsgraph):
        """
        Cast 8 rays around the mouse, returns the hit objects.
        """
        mouse_position = Vector(self.mouse_position)
        points = [mouse_position]
        points.extend([mouse_position + point for point in mouse_pointer_offsets])
        hit_objects = []
        # logger.info(f"check_close_objects: {points}")
        for point in points:
            view_position = view3d_utils.region_2d_to_origin_3d(region, context.space_data.region_3d, point)
            mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, point)
            (hit, _, _, _, obj, *_) = context.scene.ray_cast(depsgraph, origin=view_position,
                                                             direction=mouse_vector)
            if hit:
                hit_objects.append(obj)
        # logger.info(f"hit_objects: {hit_objects}")
        return hit_objects

    def apply(self, context, region):
        """
        Apply operator modifications: Translate objects or vertices/points from source point to target point.
        """
        self.target = None
        self.target2d = None
        if self.current_state == State.SOURCE_PICKED:
            self.revert_data(context)  # We first revert objects/verts/points to their original position

            origin = self.snapdata_source.world_space[self.closest_source_id]

            # If there is a target vert/point, use it and apply axis constraint if needed.
            if self.closest_target_id >= 0:
                self.target = self.snapdata_target.world_space[self.closest_target_id]
                if len(self.snapping) == 0 or not self.snapping_local:
                    self.target = quicksnap_utils.get_axis_target(origin, self.target, self.snapping)
                else:
                    self.target = quicksnap_utils.get_axis_target(origin,
                                                                  self.snapdata_target.world_space[
                                                                      self.closest_target_id],
                                                                  self.snapping,
                                                                  bpy.data.objects[self.selection_meshes[0]])
            # If there is no target, get the target on the place perpendicular to the camera,
            # or closest to constrained axis.
            else:
                # The 3D location in this direction
                if len(self.snapping) == 0 or not self.snapping_local:
                    self.target = quicksnap_utils.get_target_free(origin, self.camera_position, self.mouse_vector,
                                                                  self.snapping)
                else:
                    self.target = quicksnap_utils.get_target_free(origin, self.camera_position, self.mouse_vector,
                                                                  self.snapping,
                                                                  bpy.data.objects[self.selection_meshes[0]])

            # Translation in a form of matrix operation:
            translation = mathutils.Matrix.Translation(Vector(self.target) - Vector(origin))
            # op = QuickVertexSnapOperator.get_target_operator(context)
            # if op:
            #     print("op found")
            #     op.value = (Vector(self.target) - Vector(origin))
            #     quicksnap_utils.dump(op)
            #     op()
            # else:
            #     print("op not found")
            # return
            self.last_translation = (Vector(self.target) - Vector(origin))
            bpy.ops.transform.translate(value=self.last_translation, orient_type='GLOBAL')
            # Apply the translations to selected objects or to selected verts/points
            # if self.object_mode:
            #     for obj_name in self.backup_object_positions:
            #         quicksnap_utils.translate_object_worldspace(bpy.data.objects[obj_name], translation)
            # else:
            #     # logger.info("apply no snapping")
            #     object_mode_backup = quicksnap_utils.set_object_mode_if_needed()
            #     for object_name in self.backup_vertices_positions:
            #         obj = bpy.data.objects[object_name]
            #         if obj.type == "MESH":
            #             vertexids = [vert[0] for vert in self.backup_vertices_positions[object_name]]
            #             quicksnap_utils.translate_vertices_worldspace(obj, self.bmeshs[object_name],
            #                                                           self.backup_vertices_positions[object_name],
            #                                                           translation)
            #         elif obj.type == "CURVE":
            #             logger.info(f"Apply - backupdata={self.backup_vertices_positions[object_name][0]}")
            #             quicksnap_utils.translate_curvepoints_worldspace(obj,
            #                                                              self.backup_vertices_positions[
            #                                                                  object_name],
            #                                                              translation)
            #     quicksnap_utils.revert_mode(object_mode_backup)

            # Get the 2D position of the target for ui rendering
            self.target2d = quicksnap_utils.transform_worldspace_coord2d(self.target, region,
                                                                         context.space_data.region_3d)

    def __init__(self):
        self.last_translation = None
        self.translate_ops = None
        self._timer = None
        self._handle_3d = None
        self._handle = None
        self.mouse_position = None
        self.bmeshs = None
        self.backup_vertices_positions = {}
        self.backup_object_positions = {}
        self.perspective_matrix_inverse = None
        self.perspective_matrix = None
        self.camera_position = None
        self.mouse_vector = None
        self.closest_target_object = ""
        self.snapdata_target = None
        self.snapdata_source = None
        self.snap_to_origins = False
        self.object_mode = None
        self.target_object_show_texture_space_backup = False
        self.target_object_show_name_backup = False
        self.target_object_show_wire_backup = False
        self.target_object_is_root = False
        self.target_object = ""
        self.camera_moved = False
        self.target2d = None
        self.target = None
        self.distance = 0
        self.closest_actionable = False
        self.closest_target_id = -1
        self.closest_source_id = -1
        self.current_state = State.IDLE
        self.selection_meshes = None
        self.settings = get_addon_settings()
        self.snapping_local = False
        self.snapping = ""
        logger.info("Start")

    def __del__(self):
        pass

    def refresh_vertex_data(self, context, region):
        """
        Re-Init the snapdata if the view camera moved. (Updates 2d positions of all points)
        """
        # logger.info("refresh data")
        region3d = context.space_data.region_3d
        self.camera_position = region3d.view_matrix.inverted().translation
        self.perspective_matrix = context.space_data.region_3d.perspective_matrix
        self.perspective_matrix_inverse = self.perspective_matrix.inverted()

        self.snapdata_source.__init__(context, region, self.selection_meshes)
        self.snapdata_target.is_enabled = False
        self.snapdata_target.__init__(context, region, self.selection_meshes,
                                      quicksnap_utils.get_scene_meshes(True))

    def modal(self, context, event):

        # Get 'WINDOW' region of the current context, useful when the context region is a child UI region of the window
        region = None
        for area_region in context.area.regions:
            if area_region.type == 'WINDOW':
                region = area_region

        snapdata_updated = False
        if self.current_state == State.IDLE:
            snapdata_updated = snapdata_updated or self.snapdata_source.process_iteration(context)
            if self.snapdata_source.iteration_finished:
                snapdata_updated = snapdata_updated or self.snapdata_target.process_iteration(context)
        else:
            snapdata_updated = snapdata_updated or self.snapdata_target.process_iteration(context)
        context.area.tag_redraw()

        self.handle_hotkeys(context, event, region)

        if event.type in {'RIGHTMOUSE', 'ESC'}:  # Cancel
            self.terminate(context, revert=True)
            return {'CANCELLED'}

        elif event.type == 'LEFTMOUSE':  # Confirm
            if self.current_state == State.IDLE and self.closest_source_id >= 0 and self.closest_actionable:
                self.current_state = State.SOURCE_PICKED
                self.set_target_object("")
                self.update_header(context)
            else:
                self.terminate(context)
                return {'FINISHED'}

        elif event.type == 'MOUSEMOVE' or snapdata_updated:  # Apply
            self.update_mouse_position(context, event)
            if self.camera_moved:
                self.refresh_vertex_data(context, region)
                self.camera_moved = False
            self.update(context, region)
            self.apply(context, region)
            self.update_header(context)

        # Allow navigation
        if self.current_state == State.IDLE and event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self.camera_moved = True
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}

    def handle_hotkeys(self, context, event, region):
        """
        Toggle axis constraint and origin snapping.
        """
        # logger.info(f"Event: {event.type}")
        if event.is_repeat or event.value != 'PRESS':
            return
        event_type = event.type
        if event_type == 'X':
            if event.shift:
                new_snapping = 'YZ'
            else:
                new_snapping = 'X'
            if self.snapping == new_snapping:
                if not self.snapping_local and len(self.selection_meshes) == 1:
                    self.snapping_local = not self.snapping_local
                else:
                    self.snapping_local = False
                    self.snapping = ""
            else:
                self.snapping = new_snapping
            self.update(context, region)
            self.apply(context, region)
        elif event_type == 'Y':
            if event.shift:
                new_snapping = 'XZ'
            else:
                new_snapping = 'Y'
            if self.snapping == new_snapping:
                if not self.snapping_local and len(self.selection_meshes) == 1:
                    self.snapping_local = not self.snapping_local
                else:
                    self.snapping_local = False
                    self.snapping = ""
            else:
                self.snapping = new_snapping
            self.update(context, region)
            self.apply(context, region)
        elif event_type == 'Z':
            if event.shift:
                new_snapping = 'XY'
            else:
                new_snapping = 'Z'
            if self.snapping == new_snapping:
                if not self.snapping_local and len(self.selection_meshes) == 1:
                    self.snapping_local = not self.snapping_local
                else:
                    self.snapping_local = False
                    self.snapping = ""
            else:
                self.snapping = new_snapping
            self.update(context, region)
            self.apply(context, region)
        elif event_type == 'O':
            self.snap_to_origins = not self.snap_to_origins
            self.update(context, region)
            self.apply(context, region)
        elif event_type == 'W':
            self.settings.display_target_wireframe = not self.settings.display_target_wireframe
            self.set_target_object(self.target_object, self.target_object_is_root, force=True)
        self.update_header(context)

    def terminate(self, context, revert=False):
        """
        End modal operator, reset header, etc
        """
        # logger.info("terminate")
        if revert:
            self.revert_data(context, apply=True)

        self.set_target_object("")
        context.area.header_text_set(None)
        context.window.cursor_set("DEFAULT")
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        self.snapdata_target.is_enabled = False
        context.window_manager.event_timer_remove(self._timer)

        # Revert mode and selection
        if self.object_mode:
            bpy.ops.object.mode_set(mode='OBJECT')
        for selected_object in self.selection_meshes:
            bpy.data.objects[selected_object].select_set(True)

    def update_mouse_position(self, context, event):
        self.mouse_position = (event.mouse_x - context.area.x, event.mouse_y - context.area.y)

    def update_header(self, context):
        axis_msg = ""
        snapping_msg = f"Use (Shift+)X/Y/Z to constraint to the world/local axis or plane. Use O to snap to object " \
                       f"origins. Right Mouse Button/ESC to cancel the operation. "
        if self.snap_to_origins:
            snapping_msg = "Snapping to origins only. "
        if len(self.snapping) > 0:
            if not self.snap_to_origins:
                snapping_msg = ""
            if len(self.snapping) == 1:
                snapping_msg = f"{snapping_msg}Constrained on {self.snapping} axis"
            if len(self.snapping) == 2:
                snapping_msg = f"{snapping_msg}Constrained on {self.snapping} plane"
            if self.snapping_local:
                axis_msg = "(Local)"
            else:
                axis_msg = "(World)"
        if self.current_state == State.IDLE:
            context.area.header_text_set(f"QuickSnap: Pick the source vertex/point. {snapping_msg}{axis_msg}")
        elif self.current_state == State.SOURCE_PICKED:
            context.area.header_text_set(
                f"QuickSnap: Move the mouse over the target vertex/point. {snapping_msg}{axis_msg}")

    def invoke(self, context, event):
        logger.info("invoke")
        if context.area is None:
            return {'CANCELLED'}
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

        context.window.cursor_set("DEFAULT")
        self.update_mouse_position(context, event)

        if not self.initialize(context):
            return {'CANCELLED'}

        args = (self, context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(quicksnap_render.draw_callback_2d, args, 'WINDOW',
                                                              'POST_PIXEL')
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(quicksnap_render.draw_callback_3d, args, 'WINDOW',
                                                                 'POST_VIEW')
        self._timer = context.window_manager.event_timer_add(0.005, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


def get_addon_settings():
    addon = bpy.context.preferences.addons.get(__name_addon__)
    if addon:
        return addon.preferences
    return None


class QuickVertexSnapPreference(bpy.types.AddonPreferences):
    bl_idname = __name_addon__

    draw_rubberband: bpy.props.BoolProperty(name="Draw Rubber Band", default=True)
    filter_search_obstructed: bpy.props.BoolProperty(name="Only snap from/to non visible points when in xRay",
                                                     default=False)
    snap_objects_origin: bpy.props.EnumProperty(
        name="Snap from/to objects origins",
        items=[
            ("ALWAYS", "Always ON", "", 0),
            ("KEY", "Only when holding \"O\" key", "", 1)
        ],
        default="ALWAYS", )
    display_target_wireframe: bpy.props.BoolProperty(name="Display target object wireframe", default=True)

    def draw(self, context=None):
        layout = self.layout
        col = layout.column(align=True)
        col.use_property_split = True
        col.prop(self, "filter_search_obstructed")
        col.prop(self, "snap_objects_origin")
        col.prop(self, "draw_rubberband")
        col.prop(self, "display_target_wireframe")

        box_content = layout.box()
        header = box_content.row(align=True)
        header.label(text="Keymap", icon='EVENT_A')
        col = box_content.column(align=True)
        col.use_property_split = False
        global addon_keymaps
        key_config = bpy.context.window_manager.keyconfigs.addon
        categories = set([cat for (cat, key) in addon_keymaps])
        id_names = [key.idname for (cat, key) in addon_keymaps]
        for cat in categories:
            active_cat = key_config.keymaps.find(cat.name, space_type=cat.space_type,
                                                 region_type=cat.region_type).active()
            for active_key in active_cat.keymap_items:
                if active_key.idname in id_names:
                    quicksnap_utils.display_keymap(active_key, col)
        col.separator()
        col.label(text="Modifier hotkeys:")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_X', "Constraint to X Axis")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_X', "Constraint to X Plane", shift=True)
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Y', "Constraint to Y Axis")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Y', "Constraint to Y Plane", shift=True)
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Z', "Constraint to Z Axis")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Z', "Constraint to Z Plane", shift=True)
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_O', "Snap to objects origins only")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_W', "Enable/Disable wireframe on target object")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_ESC', "Cancel Snap")
        quicksnap_utils.insert_ui_hotkey(col, 'MOUSE_RMB', "Cancel Snap")


# class MYADDONNAME_TOOL_mytool(bpy.types.WorkSpaceTool):
#     bl_idname = "myaddonname.mytool"
#     bl_space_type='VIEW_3D'
#     bl_context_mode='OBJECT'
#     bl_label = "My tool"
#     bl_icon = "ops.transform.vertex_random"
#     operator="object.quick_vertex_snap"

blender_classes = [
    QuickVertexSnapOperator,
    QuickVertexSnapPreference,
]


def register():
    for blender_class in blender_classes:
        bpy.utils.register_class(blender_class)
    window_manager = bpy.context.window_manager
    key_config = window_manager.keyconfigs.addon
    if key_config:
        export_category = key_config.keymaps.new('3D View', space_type='VIEW_3D', region_type='WINDOW', modal=False)
        export_key = export_category.keymap_items.new("object.quick_vertex_snap", type='V', value='PRESS', shift=True,
                                                      ctrl=True)
        addon_keymaps.append((export_category, export_key))


def unregister():
    for (cat, key) in addon_keymaps:
        cat.keymap_items.remove(key)
    addon_keymaps.clear()
    for blender_class in blender_classes:
        bpy.utils.unregister_class(blender_class)
