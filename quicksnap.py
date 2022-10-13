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
from . import addon_updater_ops

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
    bl_label = "QuickSnap Tool"
    bl_options = {'INTERNAL', 'UNDO'}
    bl_description = "Quickly snap selection from/to a selected vertex, curve point, object origin, edge midpoint, face" \
                     " center.\nUse the same keymap to open the tool PIE menu."

    def initialize(self, context):
        # Get 'WINDOW' region of the context. Useful when the active context region is UI within the 3DView
        region = None
        for region_item in context.area.regions:
            if region_item.type == 'WINDOW':
                region = region_item

        if not region:
            return False  # If no window region, cancel the operation.

        # Get selection, if false cancel operation
        self.selection_objects = [obj.name for obj in quicksnap_utils.get_selection_objects(context)]
        if not self.selection_objects or len(self.selection_objects) == 0:
            return False

        self.object_mode = bpy.context.active_object.mode == 'OBJECT'
        if not self.object_mode and not quicksnap_utils.has_points_selected(context, self.selection_objects):
            return False

        # Create SnapData objects that will store all the vertex/point info (World space, view space, and kdtree to
        # search the closest point)
        self.snapdata_source = SnapData(context, region, self.settings, self.selection_objects)
        self.snapdata_target = SnapData(context, region, self.settings, self.selection_objects,
                                        quicksnap_utils.get_scene_objects(True))

        # Store 3DView camera information.
        region3d = context.space_data.region_3d
        self.camera_position = region3d.view_matrix.inverted().translation
        self.mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d,
                                                                self.mouse_position)
        self.perspective_matrix = context.space_data.region_3d.perspective_matrix
        self.perspective_matrix_inverse = self.perspective_matrix.inverted()
        self.target_bounds = {}
        self.target_npdata = {}
        self.ignore_modifiers = self.settings.ignore_modifiers
        self.target_face_index = -1
        self.target_object_display_backup = {}
        self.source_highlight_data = {}
        self.target_highlight_data = {}
        self.source_allowed_indices = {}
        self.target_allowed_indices = {}
        self.source_npdata = {}
        self.backup_data(context)
        self.update(context, region)
        context.area.header_text_set(f"QuickSnap: Pick a vertex/point from the selection to start move-snapping")
        self.detect_hotkey()
        return True

    def backup_data(self, context):
        """
        Backup points positions if in Object mode, otherwise backup object positions. used for cancelling operator
        """
        self.backup_object_positions = {}
        if self.object_mode:
            selection = quicksnap_utils.keep_only_parents(
                [bpy.data.objects[obj_name] for obj_name in self.selection_objects])
            for obj in selection:
                self.backup_object_positions[obj.name] = obj.matrix_world.copy()
        else:
            self.backup_curve_points = {}
            self.bmeshs = {}
            for object_name in self.snapdata_source.selected_ids:
                obj = bpy.data.objects[object_name]
                if obj.type == "MESH":
                    self.bmeshs[object_name] = bmesh.new()
                    self.bmeshs[object_name].from_mesh(obj.data)

                elif obj.type == "CURVE":
                    self.backup_curve_points[object_name] = quicksnap_utils.flatten([[
                        (spline_index, index, point.co.copy(), 1, point.handle_left.copy(), point.handle_right.copy())
                        for index, point in enumerate(spline.bezier_points) if point.select_control_point]
                        for spline_index, spline in enumerate(obj.data.splines)])

                    self.backup_curve_points[object_name].extend(quicksnap_utils.flatten([[(
                        spline_index, index, point.co.copy(), 0, 0, 0)
                        for index, point in enumerate(spline.points) if point.select]
                        for spline_index, spline in enumerate(obj.data.splines)]))

    def store_object_display(self, object_name):
        if object_name not in self.target_object_display_backup:
            self.target_object_display_backup[object_name] = (bpy.data.objects[object_name].show_wire,
                                                              bpy.data.objects[object_name].show_name,
                                                              bpy.data.objects[object_name].show_bounds,
                                                              bpy.data.objects[object_name].display_bounds_type)

    def revert_object_display(self, object_name):
        (bpy.data.objects[object_name].show_wire,
         bpy.data.objects[object_name].show_name,
         bpy.data.objects[object_name].show_bounds,
         bpy.data.objects[object_name].display_bounds_type) = self.target_object_display_backup[object_name]

    def set_object_display(self, target_object="", hover_object="", is_root=False, mesh_vertid=-1, force=True):
        """
        Defines the target object.
        Enables wireframe/bounds/display name on the target object and disable all that on the previous target object
        """
        if self.target_object != "":
            self.revert_object_display(self.target_object)
        if self.hover_object != "" and self.settings.display_hover_wireframe:
            self.revert_object_display(self.hover_object)

        if target_object != "":
            self.store_object_display(target_object)

            bpy.data.objects[target_object].show_wire = self.settings.display_target_wireframe or \
                                                        self.target_object_display_backup[target_object][0]
            if is_root:
                bpy.data.objects[target_object].show_name = True

        self.target_object = target_object
        self.target_object_is_root = is_root

        if self.settings.display_hover_wireframe:
            if hover_object != "":
                self.store_object_display(hover_object)
                bpy.data.objects[hover_object].show_wire = True

            self.hover_object = hover_object
        self.closest_vertexid = mesh_vertid

    def revert_data(self, context, apply=False):
        """
        Revert the backed up data (verts/curve points positions if in EDIT mode, objects locations if in OBJECT mode)
        """
        if self.object_mode:
            for object_name in self.backup_object_positions:
                bpy.data.objects[object_name].matrix_world = self.backup_object_positions[object_name].copy()
        else:
            # If the operation is not cancelled, simply move the selection back.
            if not apply and self.last_translation is not None:
                bpy.ops.transform.translate(value=self.last_translation * -1,
                                            orient_type='GLOBAL',
                                            snap=False,
                                            use_automerge_and_split=False)
                return
            # Otherwise, properly revert all vertex/points data.
            object_mode_backup = quicksnap_utils.set_object_mode_if_needed()
            for object_name in self.bmeshs:
                obj = bpy.data.objects[object_name]
                self.bmeshs[object_name].to_mesh(bpy.data.objects[object_name].data)

            for object_name in self.backup_curve_points:
                obj = bpy.data.objects[object_name]
                data = obj.data
                for (curveindex, index, co, bezier, left, right) in self.backup_curve_points[object_name]:
                    if bezier == 1:
                        data.splines[curveindex].bezier_points[index].co = co
                        data.splines[curveindex].bezier_points[index].handle_left = left
                        data.splines[curveindex].bezier_points[index].handle_right = right
                    else:
                        data.splines[curveindex].points[index].co = co

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

        depsgraph = context.evaluated_depsgraph_get()
        hover_object = ""
        if self.current_state == State.IDLE:
            # Find object under the mouse
            (direct_hit, _, _, self.target_face_index, direct_hit_object, _) = context.scene.ray_cast(context.evaluated_depsgraph_get(),
                                                                                 origin=self.camera_position,
                                                                                 direction=self.mouse_vector)
            # If found, we push this object on top of the stack of objects to process
            if direct_hit and direct_hit_object.name in self.selection_objects:
                hover_object = direct_hit_object.name
                self.snapdata_source.add_object_data(direct_hit_object.name,
                                                     depsgraph=depsgraph,
                                                     is_selected=True,
                                                     set_first_priority=True)

            # Find source vert/point the closest to the mouse, change cursor crosshair
            closest = self.snapdata_source.find_closest(mouse_coord_screen_flat,
                                                        search_origins_only=self.snap_to_origins)
            if closest is not None:
                (self.closest_source_id, self.distance, target_name, is_root, mesh_vertid) = closest
                self.set_object_display(target_name, hover_object, is_root)
                if self.distance <= 15:
                    self.closest_actionable = True  # Points too far from the mouse are highlighted but can't be moved
                    bpy.context.window.cursor_set("SCROLL_XY")
                else:
                    self.closest_actionable = False
                    bpy.context.window.cursor_set("CROSSHAIR")
            else:
                self.closest_source_id = -1
                self.closest_vertexid = -1
                self.set_object_display("", hover_object)
                self.distance = -1
                self.closest_actionable = False
                bpy.context.window.cursor_set("CROSSHAIR")

        elif self.current_state == State.SOURCE_PICKED:
            # If we are only snapping to origins, only search through origin points.
            if self.snap_to_origins:
                closest = self.snapdata_target.find_closest(mouse_coord_screen_flat, search_origins_only=True)
                if closest is not None:
                    (self.closest_target_id, self.distance, target_object_name, is_root, mesh_vertid) = closest
                    self.set_object_display(target_object_name, hover_object, is_root, mesh_vertid=mesh_vertid)
                else:
                    self.closest_vertexid = -1
                    self.closest_target_id = -1
                    self.distance = -1
                    self.set_object_display("", hover_object)

            else:  # Snapping to all verts/points

                # First hide the selection mesh not to raycast against it.
                selected_objs = [bpy.data.objects[obj] for obj in self.selection_objects]
                for obj in selected_objs:
                    obj.hide_set(True)

                # Now we will search for other objects to process around the mouse.
                for obj in self.snapdata_target.processed:  # Hide already processed meshes
                    bpy.data.objects[obj].hide_set(True)

                # Look for close objects (8 raycasts 40px around the mouse cursor)
                close_objects = self.check_close_objects(context, region, depsgraph)
                for obj in self.snapdata_target.processed:  # un-hiding processed objects, for obstruction check
                    bpy.data.objects[obj].hide_set(False)
                # Add the close objects to the to-process list
                for obj in close_objects:
                    if self.object_mode and quicksnap_utils.has_parent(obj, selected_objs):
                        if obj.name not in self.snapdata_target.processed:
                            self.snapdata_target.processed.add(obj.name)
                        continue
                    self.snapdata_target.add_object_data(obj.name, depsgraph=depsgraph,
                                                         set_first_priority=True)

                # Look for object under the mouse, if found, bring it in top of the list of objects to process.
                (direct_hit, _, _, self.target_face_index, direct_hit_object, _) = context.scene.ray_cast(depsgraph,
                                                                                     origin=self.camera_position,
                                                                                     direction=self.mouse_vector)
                if direct_hit:
                    hover_object = direct_hit_object.name

                    if self.object_mode and quicksnap_utils.has_parent(direct_hit_object, selected_objs):
                        if direct_hit_object.name not in self.snapdata_target.processed:
                            self.snapdata_target.processed.add(direct_hit_object.name)
                        else:
                            self.snapdata_target.add_object_data(direct_hit_object.name, depsgraph=depsgraph,
                                                                 set_first_priority=True)

                # Revert hidden objects
                for obj in self.selection_objects:
                    bpy.data.objects[obj].hide_set(False)
                for obj in self.selection_objects:  # re-select selection that might be lost in previous steps
                    bpy.data.objects[obj].select_set(True)

                # Find the closest target points
                closest = self.snapdata_target.find_closest(mouse_coord_screen_flat)
                if closest is not None:
                    (self.closest_target_id, self.distance, target_object_name, is_root, mesh_vertid) = closest
                    self.set_object_display(target_object_name, hover_object, is_root, mesh_vertid=mesh_vertid)
                else:
                    self.closest_vertexid = -1
                    self.closest_target_id = -1
                    self.distance = -1
                    self.set_object_display("", hover_object)

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
                                                                  bpy.data.objects[self.selection_objects[0]])
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
                                                                  bpy.data.objects[self.selection_objects[0]])

            self.last_translation = (Vector(self.target) - Vector(origin))
            bpy.ops.transform.translate(value=self.last_translation,
                                        orient_type='GLOBAL',
                                        snap=False,
                                        use_automerge_and_split=False)

            # Get the 2D position of the target for ui rendering
            self.target2d = quicksnap_utils.transform_worldspace_coord2d(self.target, region,
                                                                         context.space_data.region_3d)

    def __init__(self):
        self.ignore_modifiers = None
        self.target_face_index = -1
        self.hotkey_type = 'V'
        self.hotkey_alt = False
        self.hotkey_ctrl = True
        self.hotkey_shift = True
        self.menu_open = False
        self.hover_object = ""
        self.target_bounds = None
        self.source_highlight_data = None
        self.source_allowed_indices = None
        self.target_highlight_data = None
        self.target_allowed_indices = None
        self.source_npdata = None
        self.target_npdata = None
        self.backup_curve_points = None
        self.last_translation = None
        self.translate_ops = None
        self._timer = None
        self._handle_3d = None
        self._handle = None
        self.mouse_position = None
        self.bmeshs = None
        self.backup_vertices = {}
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
        self.target_object_display_backup = None
        self.target_object_show_bounds_backup = False
        self.target_object_display_bounds_type_backup = False
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
        self.closest_vertexid = -1
        self.current_state = State.IDLE
        self.selection_objects = None
        self.settings = get_addon_settings()
        self.snapping_local = False
        self.snapping = ""

    def __del__(self):
        pass

    def refresh_vertex_data(self, context, region):
        """
        Re-Init the snapdata if the view camera moved. (Updates 2d positions of all points)
        """
        # logger.info("refresh data")
        region3d = context.space_data.region_3d
        self.camera_position = region3d.view_matrix.inverted().translation
        self.target_bounds = {}
        self.source_highlight_data = {}
        self.target_highlight_data = {}
        self.source_allowed_indices = {}
        self.target_allowed_indices = {}
        self.perspective_matrix = context.space_data.region_3d.perspective_matrix
        self.perspective_matrix_inverse = self.perspective_matrix.inverted()
        if self.current_state == State.IDLE:
            self.snapdata_source.__init__(context, region, self.settings, self.selection_objects)
        self.snapdata_target.is_enabled = False
        self.snapdata_target.__init__(context, region, self.settings, self.selection_objects,
                                      quicksnap_utils.get_scene_objects(True))

    def modal(self, context, event):

        # Get 'WINDOW' region of the current context, useful when the context region is a child UI region of the window
        region = None
        for area_region in context.area.regions:
            if area_region.type == 'WINDOW':
                region = area_region

        snapdata_updated = False
        if self.current_state == State.IDLE:
            snapdata_updated = snapdata_updated or self.snapdata_source.process_iteration(context)
            if not self.snapdata_source.keep_processing:  # if all source are processed, start processing target points
                snapdata_updated = snapdata_updated or self.snapdata_target.process_iteration(context)
        else:
            snapdata_updated = snapdata_updated or self.snapdata_target.process_iteration(context)
        context.area.tag_redraw()

        self.handle_hotkeys(context, event, region)

        if event.type in {'RIGHTMOUSE', 'ESC'} and not self.menu_open and event.value == 'PRESS':  # Cancel
            self.terminate(context, revert=True)
            return {'CANCELLED'}

        elif event.type == 'LEFTMOUSE' and not self.menu_open:  # Confirm
            if self.current_state == State.IDLE and self.closest_source_id >= 0 and self.closest_actionable:
                self.current_state = State.SOURCE_PICKED
                self.set_object_display("", "")
                self.update_header(context)
            else:
                self.terminate(context)
                return {'FINISHED'}

        elif event.type == 'MOUSEMOVE' or snapdata_updated:  # Apply
            if self.menu_open:
                self.handle_pie_menu_closed(context,event,region)
                self.menu_open = False
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
        if not self.menu_open and event_type == self.hotkey_type and event.shift == self.hotkey_shift \
                and event.ctrl == self.hotkey_ctrl and event.alt == self.hotkey_alt and self.current_state==State.IDLE:
            self.menu_open = True
            bpy.ops.wm.call_menu_pie(name="VIEW3D_MT_PIE_quicksnap")
        elif event_type == 'X':
            if event.shift:
                new_snapping = 'YZ'
            else:
                new_snapping = 'X'
            if self.snapping == new_snapping:
                if not self.snapping_local and len(self.selection_objects) == 1:
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
                if not self.snapping_local and len(self.selection_objects) == 1:
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
                if not self.snapping_local and len(self.selection_objects) == 1:
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
            self.set_object_display(self.target_object, self.hover_object, self.target_object_is_root, force=True)
        elif event_type == 'M':
            self.settings.ignore_modifiers = not self.settings.ignore_modifiers

            self.refresh_vertex_data(context, region)
            self.set_object_display(self.target_object, self.hover_object, self.target_object_is_root, force=True)
        self.update_header(context)

    def terminate(self, context, revert=False):
        """
        End modal operator, reset header, etc
        """
        # logger.info("terminate")
        if revert:
            self.revert_data(context, apply=True)

        self.set_object_display("", "")
        context.area.header_text_set(None)
        if self.object_mode:
            bpy.context.window.cursor_set("DEFAULT")
        else:
            bpy.context.window.cursor_set("CROSSHAIR")
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        self.snapdata_target.is_enabled = False
        context.window_manager.event_timer_remove(self._timer)

        # Revert mode and selection
        if self.object_mode:
            bpy.ops.object.mode_set(mode='OBJECT')
        for selected_object in self.selection_objects:
            bpy.data.objects[selected_object].select_set(True)

        if self.target_npdata is not None and len(self.target_npdata) > 0:
            for bm in self.target_npdata:
                self.target_npdata[bm] = None
            self.target_npdata = {}

    def update_mouse_position(self, context, event):
        self.mouse_position = (event.mouse_region_x, event.mouse_region_y)

    def update_header(self, context):
        ignore_modifiers_msg = ""
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
        if self.settings.ignore_modifiers:
            ignore_modifiers_msg = " [MODIFIERS ARE IGNORED]"
        if self.current_state == State.IDLE:
            context.area.header_text_set(f"QuickSnap: Pick the source vertex/point. {snapping_msg}{axis_msg} "
                                         f"{ignore_modifiers_msg}")
        elif self.current_state == State.SOURCE_PICKED:
            context.area.header_text_set(
                f"QuickSnap: Move the mouse over the target vertex/point. {snapping_msg}{axis_msg} "
                f"{ignore_modifiers_msg}")

    def invoke(self, context, event):
        if context.area is None:
            return {'CANCELLED'}
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

        self.update_mouse_position(context, event)
        if not self.initialize(context):
            return {'CANCELLED'}

        context.window.cursor_modal_set("DEFAULT")

        args = (self, context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(quicksnap_render.draw_callback_2d, args, 'WINDOW',
                                                              'POST_PIXEL')
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(quicksnap_render.draw_callback_3d, args, 'WINDOW',
                                                                 'POST_VIEW')
        self._timer = context.window_manager.event_timer_add(0.005, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def handle_pie_menu_closed(self, context, event, region):
        if self.settings.snap_source_type != self.snapdata_source.snap_type or \
                self.ignore_modifiers != self.settings.ignore_modifiers:

            self.snapdata_source.__init__(context, region, self.settings, self.selection_objects)
            self.source_highlight_data = {}
            self.target_highlight_data = {}
            self.source_allowed_indices = {}
            self.target_allowed_indices = {}
            self.source_npdata = {}
            self.target_npdata = {}
        if self.settings.snap_target_type != self.snapdata_target.snap_type or \
                self.ignore_modifiers != self.settings.ignore_modifiers:
            self.snapdata_target.is_enabled = False
            self.snapdata_target.__init__(context, region, self.settings, self.selection_objects,
                                          quicksnap_utils.get_scene_objects(True))
            self.source_highlight_data = {}
            self.target_highlight_data = {}
            self.source_allowed_indices = {}
            self.target_allowed_indices = {}
            self.source_npdata = {}
            self.target_npdata = {}
        self.ignore_modifiers = self.settings.ignore_modifiers
        pass

    def detect_hotkey(self):
        key_config = bpy.context.window_manager.keyconfigs.addon
        categories = set([cat for (cat, key) in addon_keymaps])
        id_names = [key.idname for (cat, key) in addon_keymaps]
        for cat in categories:
            active_cat = key_config.keymaps.find(cat.name, space_type=cat.space_type,
                                                 region_type=cat.region_type).active()
            for active_key in active_cat.keymap_items:
                if active_key.idname in id_names:
                    self.hotkey_type = active_key.type
                    self.hotkey_ctrl = active_key.ctrl
                    self.hotkey_shift = active_key.shift
                    self.hotkey_alt = active_key.alt
        pass


def get_addon_settings():
    addon = bpy.context.preferences.addons.get(__name_addon__)
    if addon:
        return addon.preferences
    return None


class QuickVertexSnapPreference(bpy.types.AddonPreferences):
    bl_idname = __name_addon__

    draw_rubberband: bpy.props.BoolProperty(name="Draw Rubber Band", default=True)
    snap_objects_origin: bpy.props.EnumProperty(
        name="Snap from/to objects origins",
        items=[
            ("ALWAYS", "Always ON", "", 0),
            ("KEY", "Only in 'Snap to origins' mode (\"O\" key)", "", 1)
        ],
        default="ALWAYS", )
    display_target_wireframe: bpy.props.BoolProperty(name="Display target object wireframe", default=True)
    display_hover_wireframe: bpy.props.BoolProperty(name="Display mouseover object wireframe", default=True)
    highlight_target_vertex_edges: bpy.props.BoolProperty(name="Enable highlighting of target vertex edges*",
                                                          default=True)
    edge_highlight_width: bpy.props.IntProperty(name="Highlight Width", default=2, min=1, max=5)
    edge_highlight_color_source: bpy.props.FloatVectorProperty(
       name="Highlight Color (Selected object)",
       subtype='COLOR',
       default=(1.0, 1.0, 0.0),
       min=0.0, max=1.0
       )
    edge_highlight_color_target: bpy.props.FloatVectorProperty(
        name="Highlight Color (Target object)",
        subtype='COLOR',
        default=(1.0, 1.0, 0.0),
        min=0.0, max=1.0
    )
    edge_highlight_opacity: bpy.props.FloatProperty(name="Highlight Opacity", default=1, min=0, max=1)
    display_potential_target_points: bpy.props.BoolProperty(name="Display near edge midpoints/face centers*"
                                                            ,default=True)
    ignore_modifiers: bpy.props.BoolProperty(name="Ignore modifiers (For heavy scenes)", default=False)

    snap_source_type: bpy.props.EnumProperty(
        name="Snap From",
        items=[
            ("POINTS", "Vertices, Curve points", "", 0),
            ("MIDPOINTS", "Edges mid-points", "", 1),
            ("FACES", "Face centers", "", 2)
        ],
        default="POINTS", )

    snap_target_type: bpy.props.EnumProperty(
        name="Snap To",
        items=[
            ("POINTS", "Vertices, Curve points", "", 0),
            ("MIDPOINTS", "Edges mid-points", "", 1),
            ("FACES", "Face centers", "", 2)
        ],
        default="POINTS", )

    # addon updater preferences from `__init__`, be sure to copy all of them
    auto_check_update: bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=False,
    )

    updater_interval_months: bpy.props.IntProperty(
        name='Months',
        description="Number of months between checking for updates",
        default=0,
        min=0
    )
    updater_interval_days: bpy.props.IntProperty(
        name='Days',
        description="Number of days between checking for updates",
        default=7,
        min=0,
    )
    updater_interval_hours: bpy.props.IntProperty(
        name='Hours',
        description="Number of hours between checking for updates",
        default=0,
        min=0,
        max=23
    )
    updater_interval_minutes: bpy.props.IntProperty(
        name='Minutes',
        description="Number of minutes between checking for updates",
        default=0,
        min=0,
        max=59
    )

    def draw(self, context=None):
        layout = self.layout
        col = layout.column(align=True)
        col.use_property_split = True
        col.prop(self, "ignore_modifiers")
        col.prop(self, "snap_objects_origin")
        col.prop(self, "draw_rubberband")
        col.prop(self, "display_target_wireframe")
        col.prop(self, "display_hover_wireframe")
        col.prop(self, "display_potential_target_points")
        col.separator()
        container=col.box().column()
        container.label(text="Target Edge Highlight*:")
        # container.use_property_split = False
        container.prop(self, "highlight_target_vertex_edges")
        # container.use_property_split = True
        if self.highlight_target_vertex_edges:
            container.prop(self, "edge_highlight_width")
            container.prop(self, "edge_highlight_opacity")
            container.prop(self, "edge_highlight_color_source")
            container.prop(self, "edge_highlight_color_target")

        col.label(text="*Can noticeably impact performances")
        box_content = layout.box()
        header = box_content.row(align=True)
        header.label(text="Keymap", icon='EVENT_A')
        col = box_content.column(align=True)
        col.use_property_split = False
        global addon_keymaps
        key_config = bpy.context.window_manager.keyconfigs.addon
        categories = set([cat for (cat, key) in addon_keymaps])
        id_names = [key.idname for (cat, key) in addon_keymaps]
        quicksnap_keymap = None
        for cat in categories:
            active_cat = key_config.keymaps.find(cat.name, space_type=cat.space_type,
                                                 region_type=cat.region_type).active()
            for active_key in active_cat.keymap_items:
                if active_key.idname in id_names:
                    quicksnap_keymap = active_key
                    quicksnap_utils.display_keymap(active_key, col)
        col.separator()
        col.label(text="QuickSnap hotkeys:")
        if quicksnap_keymap is not None:
            quicksnap_utils.insert_ui_hotkey(col, f'EVENT_{quicksnap_keymap.type}',
                                             "Open PIE menu (Same keymap as the QuickSnap Tool)",
                                             shift=quicksnap_keymap.shift,
                                             control=quicksnap_keymap.ctrl,
                                             alt=quicksnap_keymap.alt,
                                             )

        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_X', "Constraint to X Axis")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_X', "Constraint to X Plane", shift=True)
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Y', "Constraint to Y Axis")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Y', "Constraint to Y Plane", shift=True)
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Z', "Constraint to Z Axis")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_Z', "Constraint to Z Plane", shift=True)
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_O', "Snap to objects origins only")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_W', "Enable/Disable wireframe on target object")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_M', "Enable/Disable 'Ignore Modifiers'")
        quicksnap_utils.insert_ui_hotkey(col, 'EVENT_ESC', "Cancel Snap")
        quicksnap_utils.insert_ui_hotkey(col, 'MOUSE_RMB', "Cancel Snap")

        addon_updater_ops.update_settings_ui(self, context)


# class MYADDONNAME_TOOL_mytool(bpy.types.WorkSpaceTool):
#     bl_idname = "myaddonname.mytool"
#     bl_space_type='VIEW_3D'
#     bl_context_mode='OBJECT'
#     bl_label = "My tool"
#     bl_icon = "ops.transform.vertex_random"
#     operator="object.quick_vertex_snap"


class VIEW3D_MT_PIE_quicksnap(bpy.types.Menu):
    # label is displayed at the center of the pie menu.
    bl_label = "QuickSnap_Pie"

    def draw(self, context):
        layout = self.layout
        settings=get_addon_settings()

        pie = layout.menu_pie()
        source_column = pie.column()
        source_column.label(text="Snap From:")
        source_column.prop(settings, "snap_source_type", expand=True)

        # operator_enum will just spread all available options
        # for the type enum of the operator on the pie
        target_column = pie.column()
        target_column.label(text="Snap To:")
        target_column.prop(settings, "snap_target_type", expand=True)
        pie.operator("quicksnap.open_settings")
        pie.prop(settings, "ignore_modifiers")


class QUICKSNAP_OT_OpenSettings(bpy.types.Operator):
    bl_idname = "quicksnap.open_settings"
    bl_label = "Open Addon Settings"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        bpy.ops.screen.userpref_show()
        bpy.context.preferences.active_section = 'ADDONS'
        bpy.data.window_managers["WinMan"].addon_search = "QuickSnap"
        bpy.data.window_managers["WinMan"].addon_filter = 'All'
        return {"FINISHED"}

blender_classes = [
    QuickVertexSnapOperator,
    QuickVertexSnapPreference,
    QUICKSNAP_OT_OpenSettings,
    VIEW3D_MT_PIE_quicksnap
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
