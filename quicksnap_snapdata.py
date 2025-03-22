﻿import bpy
import numpy as np
import time
import logging
import mathutils
from mathutils import Vector
from bpy_extras import view3d_utils
from . import quicksnap_utils
from pprint import pprint

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name_addon__)


def time_it(func):
    def wrapper(*arg, **kw):
        t1 = time.time()
        for i in range(20):
            func(*arg, **kw)
        t2 = time.time()
        logger.debug(func.__name__, (t2 - t1))

    return wrapper


class ObjectPointData:
    """    Contains the world space/screen space/counts of one object in the scene.  """

    def __init__(self, obj, object_id, perspective_matrix, width, height, width_half, height_half, view_location,
                 check_select=False,
                 filter_selected=True, snap_type='POINTS', matrix_local=None):
        """Initialize the ObjectPointData, calculates WorldSpace/ScreenSpace coordinates from local space coordinates

        Args:
            obj: target object
            object_id: object id in the snapdata object list. Used to switch target object wireframe.
            perspective_matrix: 3dView perspective matrix used to calculate ScreenSpace coordinates
            width, height, width_half, height_half: context region 3d size
            view_location: world space position of the camera
            check_select: If true filter points base on point selection
            filter_selected: If true includes only selected points, if false include only un-selected points
        """
        self.completed = False
        logger.debug(f"ObjectPointData {obj.name}- check_select={check_select} - filter_selected={filter_selected}")
        matrix_world = obj.matrix_world
        if matrix_local!=None:
            matrix_world =  matrix_world @ matrix_local
        self.is_curve = obj.type == 'CURVE' and snap_type == 'POINTS'
        # Gather object space points coordinates from the mesh/curves data
        if obj.type == 'MESH':
            if snap_type == 'POINTS':
                vertices = obj.data.vertices
                max_count = len(vertices)
                shape = (max_count, 3)
                # Copy verts co points
                points_object_space = np.empty(max_count * 3, dtype=np.float64)
                vertices.foreach_get('co', points_object_space)
                points_object_space.shape = shape
                self.indices = np.arange(max_count)
                if check_select:
                    selected_mask = np.empty(max_count, dtype=bool)
                    vertices.foreach_get('select', selected_mask)
                    if filter_selected:
                        points_object_space = points_object_space[selected_mask]
                        self.indices = self.indices[selected_mask]
                    else:
                        points_object_space = points_object_space[~selected_mask]
                        self.indices = self.indices[~selected_mask]

            elif snap_type == 'MIDPOINTS':
                # Get verts
                vertices = obj.data.vertices
                verts_count = len(vertices)
                shape = (verts_count, 3)
                verts_object_space = np.empty(verts_count * 3, dtype=np.float64)
                vertices.foreach_get('co', verts_object_space)
                verts_object_space.shape = shape

                # Get edges verts id
                edges = obj.data.edges
                edge_count = len(edges)
                edges_vertid_shape = (edge_count, 2)
                edges_vertid = np.zeros((edge_count * 2), dtype=int)  # [0.0, 0.0] * len(mesh.edges)
                edges.foreach_get('vertices', edges_vertid)
                edges_vertid.shape = edges_vertid_shape
                # Get edges center points
                points_object_space = (verts_object_space[edges_vertid[:, 0]] + verts_object_space[
                    edges_vertid[:, 1]]) / 2
                self.indices = np.arange(edge_count)
                if check_select:
                    # filter out selected/unselected
                    selected_vert_mask = np.empty(verts_count, dtype=bool)
                    vertices.foreach_get('select', selected_vert_mask)

                    if filter_selected:
                        # Filter edges where both edges are selected
                        selected_mask = selected_vert_mask[edges_vertid[:, 0]] & selected_vert_mask[edges_vertid[:, 1]]
                        points_object_space = points_object_space[selected_mask]
                        self.indices = self.indices[selected_mask]
                    else:
                        # Filter edges where none of the two verts are selected
                        selected_mask = selected_vert_mask[edges_vertid[:, 0]] | selected_vert_mask[edges_vertid[:, 1]]
                        points_object_space = points_object_space[~selected_mask]
                        self.indices = self.indices[~selected_mask]

            elif snap_type == 'FACES':
                polygons = obj.data.polygons
                polygons_count = len(polygons)
                points_object_space = np.empty(polygons_count * 3, dtype=np.float64)
                polygons.foreach_get('center', points_object_space)
                points_object_space.shape = (polygons_count, 3)
                self.indices = np.arange(polygons_count)
                if check_select:
                    # get verts to find selected verts
                    vertices = obj.data.vertices
                    verts_count = len(vertices)
                    verts_selected = np.empty(verts_count, dtype=bool)
                    vertices.foreach_get('select', verts_selected)

                    # get face verts
                    polygon_vert_count = np.empty(polygons_count, dtype=int)
                    polygons.foreach_get('loop_total', polygon_vert_count)

                    polygon_vert_start_index = np.concatenate(
                        [np.zeros(1, dtype=int), np.cumsum(polygon_vert_count[1:])])

                    polygon_verts = np.empty(np.sum(polygon_vert_count), dtype=int)
                    polygons.foreach_get('vertices', polygon_verts)
                    selected_polygon_verts = verts_selected[polygon_verts]

                    if filter_selected:
                        # Filter polygons where all verts are selected
                        selected_mask = np.logical_and.reduceat(selected_polygon_verts, polygon_vert_start_index)
                        points_object_space = points_object_space[selected_mask]
                        self.indices = self.indices[selected_mask]
                    else:
                        # Filter polygons where none of the verts are selected
                        selected_mask = np.logical_or.reduceat(selected_polygon_verts, polygon_vert_start_index)
                        points_object_space = points_object_space[~selected_mask]
                        self.indices = self.indices[~selected_mask]

        elif self.is_curve:
            all_points = quicksnap_utils.flatten(
                [[(point.co, point_index, spline_index) for point_index, point in enumerate(spline.bezier_points)] for spline_index, spline in enumerate(obj.data.splines)])
            all_points.extend(quicksnap_utils.flatten([[(Vector((point.co[0], point.co[1], point.co[2])), point_index, spline_index)
                                                        for point_index, point in enumerate(spline.points)] for spline_index, spline in enumerate(obj.data.splines)]))
            # all_points_spline_index = quicksnap_utils.flatten(
            #     [[splineindex for point in spline.bezier_points] for splineindex, spline in
            #      enumerate(obj.data.splines)])
            # all_points_spline_index.extend(quicksnap_utils.flatten([[splineindex
            #                                for point in spline.points] for splineindex, spline in
            #                                enumerate(obj.data.splines)]))
            max_count = len(all_points)
            shape = (max_count, 3)
            # Copy verts co points
            points_data = np.array(all_points, dtype=object)
            points_data.shape = (max_count, 3)
            points_object_space = np.array(quicksnap_utils.flatten(points_data[:,0]))
            points_object_space.shape = shape
            self.indices = points_data[:, 1]
            self.spline_index = points_data[:, 2]
            if check_select:
                selected_mask = quicksnap_utils.flatten(
                    [[point.select_control_point for point in spline.bezier_points] for spline in obj.data.splines])
                selected_mask.extend(quicksnap_utils.flatten([[point.select for point in spline.points] for spline in
                                                              obj.data.splines]))
                selected_mask = np.array(selected_mask)
                if filter_selected:
                    points_object_space = points_object_space[selected_mask]
                    self.indices = self.indices[selected_mask]
                    self.spline_index = self.spline_index[selected_mask]
                else:
                    points_object_space = points_object_space[~selected_mask]
                    self.indices = self.indices[~selected_mask]
                    self.spline_index = self.spline_index[~selected_mask]
        else:
            self.completed = True
            return

        # Get WorldSpace
        world_space_co = np.ones(shape=(len(points_object_space), 4), dtype=np.float64)
        world_space_co[:, :-1] = points_object_space  # cos v (x,y,z,1) - point,   v(x,y,z,0)- vector
        world_space_co = np.einsum('ij,aj->ai', matrix_world, world_space_co)
        self.world_space_co = world_space_co[:, :-1]

        # Get ViewSpace
        verts_viewspace = np.einsum('ij,aj->ai', perspective_matrix, world_space_co)  # Matrix mult
        filter_behind_camera = (verts_viewspace[:, 3] > 0)
        verts_viewspace = verts_viewspace[filter_behind_camera]  # Filtering behind camera
        self.world_space_co = self.world_space_co[filter_behind_camera]
        self.indices = self.indices[filter_behind_camera]
        if self.is_curve:
            self.spline_index = self.spline_index[filter_behind_camera]

        # Get 2dScreenSpace
        self.screen_space_co = np.column_stack(
            (width_half + (verts_viewspace[:, 0] / verts_viewspace[:, 3]) * width_half,
             height_half + (verts_viewspace[:, 1] / verts_viewspace[:, 3]) * height_half,
             verts_viewspace[:, 3]))
        filter_outside_viewport = (self.screen_space_co[:, 0] > 0) & (self.screen_space_co[:, 1] > 0) & (
                self.screen_space_co[:, 0] < width) & (self.screen_space_co[:, 1] < height)
        self.screen_space_co = self.screen_space_co[filter_outside_viewport]
        self.world_space_co = self.world_space_co[filter_outside_viewport]
        self.indices = self.indices[filter_outside_viewport]
        if self.is_curve:
            self.spline_index = self.spline_index[filter_outside_viewport]
        self.count = len(self.screen_space_co)

        # Misc
        self.object_id = object_id
        self.processed_point_count = 0


class SnapData:
    """
        Contains all the necessary data to find the closest point to the mouse
    """

    def __init__(self, context, region, settings, selected_meshes, scene_meshes=None, is_origin=False,
                 no_selection=False):
        self.no_selection = no_selection
        self.settings = settings
        self.is_origin_snapdata = is_origin
        self.object_mode = context.active_object is None or context.active_object.mode == 'OBJECT'
        # print(f"init - is origin:{is_origin} - no selection={no_selection} - self.object_mode={self.object_mode}")
        # print(f"selected_meshes")
        # print(selected_meshes)
        # print(f"scene_meshes")
        # print(scene_meshes)
        if scene_meshes is None:
            scene_meshes = []
        if self.is_origin_snapdata:
            self.snap_type = settings.snap_source_type
        else:
            self.snap_type = settings.snap_target_type
        self.keep_processing = True
        self.width_half = region.width / 2.0
        self.height_half = region.height / 2.0
        self.width = region.width
        self.height = region.height
        rv3d = context.space_data.region_3d
        self.perspective_matrix = rv3d.perspective_matrix
        self.view_location = rv3d.view_matrix.inverted().translation

        # Lists to track processed/to process objects
        self.to_process_selected = []
        self.to_process_scene = []
        self.processed = set()

        self.selected_ids = {}
        self.objects_point_data = {}
        self.origins_map = {}
        self.snap_origins = quicksnap_utils.get_addon_settings().snap_objects_origin
        
        # Track all instances
        self.instances_map=quicksnap_utils.gather_scene_instance_map()
        pprint(self.instances_map)
        # Initialize kdtrees-target points nparray with correct size
        max_vertex_count = self.get_max_vertex_count(context, selected_meshes, scene_meshes)
        self.kd = mathutils.kdtree.KDTree(max_vertex_count)
        self.world_space = np.empty((max_vertex_count, 3), dtype=np.float64)
        self.region_2d = np.empty((max_vertex_count, 3), dtype=np.float64)
        self.depth = np.empty(max_vertex_count, dtype=np.float64)
        self.indices = np.empty(max_vertex_count, dtype=int)
        self.spline_index = np.empty(max_vertex_count, dtype=int)
        self.object_id = np.empty(max_vertex_count, dtype=int)
        self.added_points_np = 0

        # figure out origin count
        if not self.is_origin_snapdata or self.no_selection:  # Add all scene origins
            self.scene_meshes = scene_meshes.copy()
            self.scene_meshes.extend(selected_meshes.copy())
            self.kd_origins = mathutils.kdtree.KDTree(len(self.scene_meshes))
            self.add_scene_roots(context, selected_meshes, scene_meshes)
        else:   # Add selection origins
            self.scene_meshes = selected_meshes.copy()
            self.kd_origins = mathutils.kdtree.KDTree(len(selected_meshes))
            self.add_scene_roots(context, selected_meshes)

        self.meshes_selection = selected_meshes
        depsgraph = context.evaluated_depsgraph_get()

        if self.snap_type != 'ORIGINS':
            # Add initial objects for target destination.
            if not self.is_origin_snapdata or (self.no_selection and self.object_mode):  # Add scene + selection
                selected_objs = [bpy.data.objects[obj] for obj in selected_meshes]
                # If Snapdata contains target points and we are in edit mode, add all selected meshes to
                # target objects lists (for snapping to unselected verts).
                if not self.object_mode:
                    for selected_mesh in selected_meshes:
                        self.add_object_data(selected_mesh, depsgraph=depsgraph, is_selected=not no_selection)

                # Add meshes that do not have polygons. (cannot be found via ray-cast)
                for object_name in scene_meshes:
                    obj = bpy.data.objects[object_name]
                    if self.object_mode and quicksnap_utils.has_parent(obj, selected_objs):  # Do not add child objs
                        if obj.name not in self.processed:
                            self.processed.add(obj.name)
                        continue
                    
                    if object_name not in selected_meshes and (
                            obj.type == 'CURVE' or (
                            obj.type == 'MESH' and len(obj.data.vertices) > 0 and len(obj.data.polygons) == 0)):
                        self.add_object_data(object_name, depsgraph=depsgraph)
                    elif obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION':
                        self.add_object_data(object_name, depsgraph=depsgraph)
                        

            # Add all objects for the snap origin (selected objects only).
            elif self.is_origin_snapdata:
                for selected_mesh in selected_meshes:
                    self.add_object_data(selected_mesh, is_selected=True, depsgraph=depsgraph)

            # if origin snapdata, start processing points immediately
            if self.is_origin_snapdata:
                self.process_iteration(context)
                # self.process_iteration(context, max_run_duration=0.5)
                # self.process_iteration(context,max_run_duration=5)
        else:
            self.process_iteration(context)
            self.keep_processing=False

    def add_object_data(self, object_name, is_selected=False, depsgraph=None, set_first_priority=False, parent_name=None, matrix_local=None,root_name=None):
        """
        Creates ObjectPointData for the object.
        Adds object to the "To Process" list.
        If object is already in the list, eventually set to first in the priority list, for objects under the mouse.
        """

        logger.debug(f"add_object_data {object_name} - parent_name: {parent_name} - root_name: {root_name}")
        if root_name == None:
            root_name = object_name
        if parent_name!=None:
            full_object_name = parent_name + ">" + object_name
        else:
            full_object_name = object_name
        
        if full_object_name in self.processed:  # Skip already processed objects.
            return
        if not (bpy.data.objects[object_name].type == 'MESH' or bpy.data.objects[object_name].type == 'CURVE' or (bpy.data.objects[object_name].type == 'EMPTY' and bpy.data.objects[object_name].instance_type == 'COLLECTION')):
            logger.debug(f"add_object_data {object_name} - skipped type: {bpy.data.objects[object_name].type}")
            self.processed.add(full_object_name)
            return
        logger.debug(f"add_object_data {full_object_name} - adding")
        if is_selected:  # Process selected objects first.
            # Prioritize object if is in the list but not first in list.
            if full_object_name in self.to_process_selected:
                if self.to_process_selected.index(full_object_name) > 0:
                    # logger.debug(f"add_object_data:{object_name} - PRIORITIZE SELECTED")
                    self.to_process_selected.remove(full_object_name)
                    self.to_process_selected.insert(0, full_object_name)

            # Add object in the list if it is not already
            else:
                # logger.debug(f"add_object_data:{object_name} - First add - is origin:{self.is_origin_snapdata}")
                if self.is_origin_snapdata:
                    current_mode = quicksnap_utils.set_object_mode_if_needed()
                if self.object_mode and not self.settings.ignore_modifiers:
                    obj = bpy.data.objects[object_name].evaluated_get(depsgraph)
                else:
                    obj = bpy.data.objects[object_name]
                if not (obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION'):
                    object_id=self.scene_meshes.index(root_name)
                    self.objects_point_data[full_object_name] = ObjectPointData(obj,
                                                                        object_id,
                                                                        self.perspective_matrix,
                                                                        width=self.width,
                                                                        height=self.height,
                                                                        width_half=self.width_half,
                                                                        height_half=self.height_half,
                                                                        view_location=self.view_location,
                                                                        check_select=not self.object_mode and not self.no_selection,
                                                                        filter_selected=self.is_origin_snapdata,
                                                                        snap_type=self.snap_type,
                                                                        matrix_local=matrix_local)
                    self.to_process_selected.insert(0, full_object_name)
                else:
                    instanced_collection = obj.instance_collection
                    if parent_name!=None:
                        object_name=parent_name + ">" + object_name
                    else:
                        object_name=object_name
                    if matrix_local!=None:
                        matrix_local=matrix_local @ obj.matrix_local
                    else:
                        matrix_local=obj.matrix_local
                    # Loop through all objects in the instanced collection
                    logger.debug(f"Addmesh:{object_name} -  Is a collection instance")
                    for instanced_obj in instanced_collection.objects:
                        logger.debug(f"Addmesh:{object_name} -  Add collection instance object: {instanced_obj.name} - Type: {instanced_obj.type}")
                        self.add_object_data(instanced_obj.name, is_selected=is_selected, depsgraph=depsgraph, set_first_priority=set_first_priority, parent_name=full_object_name, matrix_local=matrix_local,root_name=root_name)
                logger.debug(f"to_process_selected:{full_object_name}")
                if self.is_origin_snapdata:
                    quicksnap_utils.revert_mode(current_mode)
                    self.selected_ids[object_name] = []
        else:
            # Prioritize object if is in the list but not first in list.
            if full_object_name in self.to_process_scene:
                if self.to_process_scene.index(full_object_name) > 0 and set_first_priority:
                    # logger.debug(f"Addmesh:{object_name} - PRIORITIZE SCENE")
                    self.to_process_scene.remove(full_object_name)
                    self.to_process_scene.insert(0, full_object_name)

            # Add object in the list if it is not already
            else:
                logger.debug(f"Addmesh:{object_name} -  FIRST ADD Scene")
                if self.settings.ignore_modifiers:
                    obj = bpy.data.objects[object_name]
                else:
                    obj = bpy.data.objects[object_name].evaluated_get(depsgraph)

                if root_name!=None:
                    object_index=self.scene_meshes.index(root_name)
                elif root_name not in self.scene_meshes:
                    object_index = -1
                else:
                    object_index = self.scene_meshes.index(root_name)
                
                if not (obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION'):
                    
                    self.objects_point_data[full_object_name] = ObjectPointData(obj,
                                                                       object_index,
                                                                       self.perspective_matrix,
                                                                       width=self.width,
                                                                       height=self.height,
                                                                       width_half=self.width_half,
                                                                       height_half=self.height_half,
                                                                       view_location=self.view_location,
                                                                       snap_type=self.snap_type,
                                                                       matrix_local=matrix_local)
                    self.to_process_scene.append(full_object_name)
                else:
                    instanced_collection = obj.instance_collection
                    if parent_name!=None:
                        object_name=parent_name + ">" + object_name
                    else:
                        object_name=object_name
                    if matrix_local!=None:
                        matrix_local=matrix_local @ obj.matrix_local
                    else:
                        matrix_local=obj.matrix_local
                    # Loop through all objects in the instanced collection
                    logger.debug(f"Addmesh:{object_name} -  Is a collection instance")
                    for instanced_obj in instanced_collection.objects:
                        logger.debug(f"Addmesh:{object_name} -  Add collection instance object: {instanced_obj.name} - Type: {instanced_obj.type}")
                        self.add_object_data(instanced_obj.name, is_selected=is_selected, depsgraph=depsgraph, set_first_priority=set_first_priority, parent_name=full_object_name, matrix_local=matrix_local,root_name=root_name)
                
                # logger.debug(f"Adding to target verts data scene:{object_name}")

    def add_scene_roots(self, context, selected_meshes, scene_meshes=None):
        """
        Add the origin of all objects to the points.
        scene_meshes is None when processing the origin snapdata.
        """

        current_camera = ""
        if context.region_data.view_perspective == 'CAMERA':
            current_camera = context.space_data.camera.name

        # Source SnapData: Add origin only when we are in object mode.
        # print(f"add_scene_roots - self.is_origin_snapdata ={self.is_origin_snapdata } - self.no_selection={self.no_selection} - self.object_mode={self.object_mode}")
        if self.is_origin_snapdata and not (self.no_selection and self.object_mode):
            if self.object_mode or self.no_selection:
                for object_name in selected_meshes:
                    if object_name == current_camera:
                        continue
                    self.add_object_root(context, object_name)

        # Target SnapData: Add selection origins only when we are not in object mode.
        # and add all non-selected objects origins, as well as cursor location.
        else:
            if not self.object_mode:
                add_roots = scene_meshes
                add_roots.extend(selected_meshes)
                add_roots = set(add_roots)
            else:
                selected_objs = [bpy.data.objects[obj_name] for obj_name in selected_meshes]
                add_roots = [object_name for object_name in scene_meshes if
                             object_name not in selected_meshes and
                             not quicksnap_utils.has_parent(bpy.data.objects[object_name], selected_objs)]
            # logger.debug(f"add_scene_roots: {len(add_roots)}")
            for object_name in add_roots:
                if object_name == current_camera:
                    continue
                self.add_object_root(context, object_name)

        if not self.is_origin_snapdata:
            # Add cursor location
            self.add_point(context, bpy.context.scene.cursor.location, mathutils.Matrix.Identity(4), object_index=-1)

        self.kd.balance()
        self.kd_origins.balance()

    def add_object_root(self, context, object_name):
        """
        Add single object origin to points list and to origins kdtree
        """
        logger.debug(f"[origin:{self.is_origin_snapdata}] - Add object root: {object_name}")
        if not self.add_point(context, Vector((0, 0, 0)), bpy.data.objects[object_name].matrix_world,
                              self.scene_meshes.index(object_name), add_to_kd=self.snap_origins == "ALWAYS"):
            return
        insert_index = self.added_points_np - 1
        logger.debug(f"[origin:{self.is_origin_snapdata}] - add_object_root: {object_name} - insert index={insert_index}")
        self.origins_map[insert_index] = object_name
        self.kd_origins.insert(Vector((self.region_2d[insert_index][0], self.region_2d[insert_index][1], 0)),
                               insert_index)

    def add_point(self, context, vertex_co, world_space_matrix, object_index, add_to_kd=True):
        """
        Add single point to SnapData. Use this for single points: object origins, cursor.
        It is too slow to process large amount of points use ObjectPointData instead.
        """
        ws = world_space_matrix @ vertex_co
        ws_2 = Vector((ws[0], ws[1], ws[2], 1))
        view_space_projection = self.perspective_matrix @ ws_2

        if view_space_projection.w <= 0:  # Skip behind camera
            return False

        region3d = context.space_data.region_3d
        if region3d.view_perspective == 'CAMERA' and not region3d.is_perspective:
            rotation = view3d_utils.region_2d_to_vector_3d(context.region, region3d, (0, 0)).normalized()
            view_location = context.space_data.camera.location
            cam_to_point_vector = (ws - view_location).normalized()
            dot = cam_to_point_vector.dot(rotation)
            if dot < 0: #behing camera in ortho camera
                print(f"dot: {dot} - behind camera")
                return False


        coord_2d = quicksnap_utils.transform_viewspace_coord2d(view_space_projection, self.width_half, self.height_half)

        # Skip out of view
        if coord_2d.x <= 0 or coord_2d.y <= 0 or coord_2d.x >= self.width or coord_2d.y >= self.height:
            return False

        # Point/Vert is in camera frustum, store world/view position.
        current_index = self.added_points_np
        # logger.debug(f"inserting point in tree at index: {current_index}")
        self.world_space[current_index] = ws
        self.region_2d[current_index] = (coord_2d[0], coord_2d[1], view_space_projection.w * 0.00000001)
        self.indices[current_index] = -1
        self.object_id[current_index] = object_index
        if add_to_kd:
            self.kd.insert(self.region_2d[current_index], current_index)
        self.added_points_np += 1

        return True

    def process_points_data_batch(self, object_name, batch_size=500):
        """
        Inject {batch_size} points from object's objects_point_data into the SnapData points.
        Updates snapdata completed status
        """
        logger.debug(f"process_points_data_batch - {object_name}")
        points_data = self.objects_point_data[object_name]
        # Get start/end indices of points we want to insert.
        start_index = points_data.processed_point_count
        end_index = min(start_index + batch_size - 1, len(points_data.screen_space_co) - 1) + 1
        insert_count = end_index - start_index
        # Get start/end indices in the array get are copying them into.
        start_insert = self.added_points_np
        end_insert = start_insert + insert_count
        logger.debug(f"Process batch [{object_name}] - batch_size={batch_size} - insert_count={insert_count} - "
                     f"start_index={start_index} - end_index={end_index} - start_insert={start_insert} - "
                     f"end_insert={end_insert} - len world_space={len(self.world_space)} ")

        # Copy points to target points arrays.
        self.world_space[start_insert:end_insert] = points_data.world_space_co[start_index:end_index]
        self.region_2d[start_insert:end_insert] = points_data.screen_space_co[start_index:end_index]
        self.region_2d[start_insert:end_insert, 2] = points_data.screen_space_co[start_index:end_index, 2] * 0.00000001
        self.depth[start_insert:end_insert] = points_data.screen_space_co[start_index:end_index, 2]
        self.object_id[start_insert:end_insert] = np.full(insert_count, points_data.object_id, dtype=int)
        self.indices[start_insert:end_insert] = points_data.indices[start_index:end_index]
        if points_data.is_curve:
            self.spline_index[start_insert:end_insert] = points_data.spline_index[start_index:end_index]
        else:
            self.spline_index[start_insert:end_insert] = -1

        # Update count of processed points and check if we are done with the current object.
        self.added_points_np += insert_count
        points_data.processed_point_count = end_index
        if points_data.processed_point_count == points_data.count:
            points_data.completed = True

    def balance_tree(self, start_index=None, end_index=None):
        """
        Adds stored points from start_index to end_index into the kdtrees, then balance the trees
        If is not set, only balance the trees.
        """
        logger.debug(f"balance_tree - Source:{self.is_origin_snapdata}")
        if start_index is not None and end_index is not None:
            logger.debug(f"balance_tree - start_index:{start_index} - end_index:{end_index}")
            insert = self.kd.insert
            for i in range(start_index, end_index):
                insert(self.region_2d[i], i)
        self.kd.balance()

    def process_iteration(self, context, max_run_duration=0.01):
        """
        To be called every frame. Process verts/points per batch until the function has run for {max_run_duration}
        """
        if not self or not self.keep_processing:
            return False
        start_time = time.perf_counter()
        elapsed_time = 0
        # Process selected objects first
        if (self.is_origin_snapdata or not self.object_mode) and len(self.to_process_selected) > 0:
            logger.debug(f"Process selection - is_origin_snapdata={self.is_origin_snapdata}")
            for object_name in self.to_process_selected.copy():
                logger.debug(
                    f"process_iteration selected: {object_name} - added points:{self.added_points_np} - max vertex count:{len(self.world_space)}")
                start_insert_id = self.added_points_np
                while not self.objects_point_data[object_name].completed:  # copy object points into snapdata until
                    self.process_points_data_batch(object_name, 1000)
                    if self.objects_point_data[object_name].completed:
                        logger.debug(f"process_iteration scene:{object_name} - ALL VERTS ADDED")
                        self.to_process_selected.remove(object_name)
                        self.processed.add(object_name)
                        self.balance_tree(start_insert_id, self.added_points_np)
                        break
                    elapsed_time = (time.perf_counter() - start_time)
                    if elapsed_time > max_run_duration:
                        self.balance_tree(start_insert_id, self.added_points_np)
                        return True

                if elapsed_time > max_run_duration:
                    self.balance_tree(start_insert_id, self.added_points_np)
                    return True

        # If origin snapdata, stop iterating if all src obj are processed, otherwise ignore scene objects and return
        if self.is_origin_snapdata and not (self.no_selection and self.object_mode):
            if len(self.to_process_selected) == 0:
                self.keep_processing = False
                return False
            return False

        # Process scene objects
        if len(self.to_process_scene) > 0:
            for selected_object in self.meshes_selection:
                bpy.data.objects[selected_object].hide_set(True)
            for object_name in self.to_process_scene.copy():
                if object_name not in self.objects_point_data:
                    continue
                logger.debug(
                    f"process_iteration unselected: {object_name} - added points:{self.added_points_np} - max vertex count:{len(self.world_space)}")
                start_time_batch = time.perf_counter()
                counter = 0
                start_insert_id = self.added_points_np
                while not self.objects_point_data[object_name].completed:
                    self.process_points_data_batch(object_name, 1000)
                    counter += 1
                    if self.objects_point_data[object_name].completed:
                        logger.debug(f"process_iteration scene:{object_name} - ALL VERTS ADDED")
                        self.to_process_scene.remove(object_name)
                        self.processed.add(object_name)
                        self.balance_tree(start_insert_id, self.added_points_np)
                        break
                    elapsed_time = (time.perf_counter() - start_time)
                    if elapsed_time > max_run_duration:
                        self.balance_tree(start_insert_id, self.added_points_np)
                        return True
            for selected_object in self.meshes_selection:
                bpy.data.objects[selected_object].hide_set(False)
                bpy.data.objects[selected_object].select_set(True)
        return False

    def find_closest(self, mouse_coord_screen_flat, search_origins_only=False):
        """
        Returns the closest point to mouse cursor amongst SnapData's points
        returns tuple:
         (Closest point ID, closest point distance to mouse, target object name, bool: is the point an object origin)
        """

        if not len(self.region_2d) > 0:
            return None
        closest_point_data = None
        close_points = []

        if search_origins_only:
            points = self.kd_origins.find_n(mouse_coord_screen_flat, 1)
            for (co, index, dist) in points:
                if dist > 40:
                    break
                origin = self.world_space[index]
                close_points.append((origin, index, dist, dist, -1))
                break

        else:
            # Search all points
            search_distance = 20  # Radius in pixels around the mouse position
            points_found = self.kd.find_range(mouse_coord_screen_flat, search_distance)
            if len(points_found) > 0:
                points_array = np.array(points_found, dtype=object)

                # normalize distance
                dist = points_array[:, 2] / search_distance

                # Convert <Vector> array into <float, float,float> array.
                depth = np.array([x for x in points_array[:, 0]])
                # Depth was multiplied by 10e-8 for depth to not affect kdtree closest search.
                depth = depth[:, 2] * 100000000
                depth = depth / np.amax(depth)  # Normalized depth
                weight_depth = 3
                weight_dist = 1

                score = (depth * weight_depth + dist * weight_dist + dist * depth) / (weight_depth + weight_dist)

                best_match_i = np.argmin(score)  # index of best score within the points found.
                match_index = points_found[best_match_i][1]  # index of best score within all points arrays
                origin = self.world_space[match_index]
                mesh_index = self.indices[match_index]
                close_points.append((origin, match_index, points_found[best_match_i][2], points_found[best_match_i][2],
                                     mesh_index))

        # sort possible closest points if more than one point
        if len(close_points) == 1:
            # logger.debug(f"Closest id: {close_points[0][1]} - is origin: {close_points[0][1] in self.origins_map}")
            closest_point_data = (
                close_points[0][1], close_points[0][3], self.scene_meshes[self.object_id[close_points[0][1]]],
                close_points[0][1] in self.origins_map, close_points[0][4])
        elif len(close_points) > 1:
            # If multiple points, sort by distance to mouse
            closest = sorted(close_points, key=lambda point: point[2])[0]
            # logger.debug(f"Closest id: {close_points[0][1]} - is origin: {close_points[0][1] in self.origins_map}")
            closest_point_data = (closest[1], closest[3], self.scene_meshes[self.object_id[close_points[0][1]]],
                                  closest[0][1] in self.origins_map, close_points[0][4])
        return closest_point_data

    def get_max_vertex_count_obj(self, obj_name, depsgraph,use_object_mode=False,ignore_modifiers=False):
        max_vertex_count=0
        obj = bpy.data.objects[obj_name]
        if obj.type == 'MESH':
            if use_object_mode and self.object_mode or ignore_modifiers and self.settings.ignore_modifiers:
                data = obj.evaluated_get(depsgraph).data
            else:
                data = obj.data

            if self.snap_type == 'POINTS':
                max_vertex_count += len(data.vertices)
            elif self.snap_type == 'MIDPOINTS':
                max_vertex_count += len(data.edges)
            elif self.snap_type == 'FACES':
                max_vertex_count += len(data.polygons)

        elif obj.type == 'CURVE':
            max_vertex_count += sum(
                [(len(spline.points) + len(spline.bezier_points)) for spline in obj.data.splines])
        elif obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION':
            instanced_collection = obj.instance_collection
            for instanced_obj in instanced_collection.objects:
                max_vertex_count += self.get_max_vertex_count_obj(instanced_obj.name, depsgraph,use_object_mode,ignore_modifiers)
        return max_vertex_count

    def get_max_vertex_count(self, context, selected_objects, scene_objects):
        """
        Returns the maximum count of visible verts/points/origins in the scene
        """
        if self.is_origin_snapdata and not self.no_selection:
            depsgraph = context.evaluated_depsgraph_get()
            max_vertex_count = len(selected_objects)
            if self.snap_type != 'ORIGINS':
                for obj_name in selected_objects:
                    max_vertex_count+=self.get_max_vertex_count_obj(obj_name,depsgraph=depsgraph,use_object_mode=True)
        else:
            all_meshes = scene_objects.copy()
            all_meshes.extend(selected_objects)
            max_vertex_count = len(all_meshes) + 1  # All objects origins + cursor

            if self.snap_type != 'ORIGINS':
                depsgraph = context.evaluated_depsgraph_get()
                for obj_name in all_meshes:
                    max_vertex_count+=self.get_max_vertex_count_obj(obj_name,depsgraph=depsgraph,ignore_modifiers=True)
                for obj_name in selected_objects:
                    max_vertex_count+=self.get_max_vertex_count_obj(obj_name,depsgraph=depsgraph)

        logger.info(f"Max vertex count: {max_vertex_count} - is_origin_snapdata={self.is_origin_snapdata}")
        return max_vertex_count

    def add_nearby_objects(self, context, region, depsgraph, mouse_position, selected_objs=[]):
        # Now we will search for other objects to process around the mouse.
        for obj in self.processed:  # Hide already processed meshes
            if obj not in bpy.data.objects:
                continue
            bpy.data.objects[obj].hide_set(True)


        # Look for close objects (8 raycasts 40px around the mouse cursor)
        close_objects = quicksnap_utils.check_close_objects(context, region, depsgraph, mouse_position,self.instances_map)
        for obj in self.processed:  # un-hiding processed objects, for obstruction check
            if obj not in bpy.data.objects:
                continue
            bpy.data.objects[obj].hide_set(False)

        # Add the close objects to the to-process list
        for obj in close_objects:
            if self.object_mode and quicksnap_utils.has_parent(obj, selected_objs):
                if obj.name not in self.processed:
                    self.processed.add(obj.name)
                continue
            self.add_object_data(obj.name, depsgraph=depsgraph, set_first_priority=True)

        if region.data.view_perspective == 'CAMERA' and not region.data.is_perspective:
            depth_location = context.space_data.camera.location
            view_position = view3d_utils.region_2d_to_location_3d(region, region.data, mouse_position,
                                                                  depth_location)
        else:
            view_position = view3d_utils.region_2d_to_origin_3d(region, region.data, mouse_position)
        # view_position = view3d_utils.region_2d_to_origin_3d(region, context.space_data.region_3d, mouse_position)
        mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, mouse_position)
        # Look for object under the mouse, if found, bring it in top of the list of objects to process.
        (direct_hit, _, _, target_face_index, direct_hit_object, _) = context.scene.ray_cast(depsgraph,
                                                                                             origin=view_position,
                                                                                             direction=mouse_vector)
        # for obj in selected_objs:
        #     bpy.data.objects[obj].select_set(True)
        if direct_hit:
            if self.object_mode and quicksnap_utils.has_parent(direct_hit_object, selected_objs):
                if direct_hit_object.name not in self.processed:
                    self.processed.add(direct_hit_object.name)
                else:
                    self.add_object_data(direct_hit_object.name, depsgraph=depsgraph, set_first_priority=True)

            return True, direct_hit_object.name, target_face_index

        return False, None, -1

    def get_object_name_at_index(self, index):
        object_id = self.object_id[index]
        if len(self.scene_meshes) < object_id:
            return None
        return self.scene_meshes[object_id]

    def select_points(self, obj, point_index):
        if obj.type == 'MESH':
            if self.snap_type == 'POINTS':
                obj.data.vertices[self.indices[point_index]].select = True
            elif self.snap_type == 'MIDPOINTS':
                vert_id_a = obj.data.edges[self.indices[point_index]].vertices[0]
                vert_id_b = obj.data.edges[self.indices[point_index]].vertices[1]
                obj.data.vertices[vert_id_a].select = True
                obj.data.vertices[vert_id_b].select = True
            elif self.snap_type == 'FACES':
                poly_vertices = obj.data.polygons[self.indices[point_index]].vertices
                for vert_id in poly_vertices:
                    obj.data.vertices[vert_id].select = True
        elif obj.type == 'CURVE':
            spline = obj.data.splines[self.spline_index[point_index]]
            if len(spline.points) > 0:
                spline.points[self.indices[point_index]].select = True
            elif len(spline.bezier_points) > 0:
                spline.bezier_points[self.indices[point_index]].select_control_point = True

