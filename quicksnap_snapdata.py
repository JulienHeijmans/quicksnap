import bpy
import numpy as np
import time
import logging
import mathutils
from mathutils import Vector

from . import quicksnap_utils

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name__)


def time_it(func):
    def wrapper(*arg, **kw):
        t1 = time.time()
        for i in range(20):
            func(*arg, **kw)
        t2 = time.time()
        print(func.__name__, (t2 - t1))

    return wrapper


class ObjectPointData:
    """
    calculate and stores the information of points that need to be added to kdtrees. (process screen space coord)
    -count
    -object_id
    -world_space_co
    -screen_space_co
    -processed_point_count
    """

    def __init__(self, obj, object_id, perspective_matrix, width, height, width_half, height_half, view_location,
                 check_select=False,
                 filter_selected=True):
        self.completed = False
        print(f"ObjectPointData {obj.name}- check_select={check_select}")
        matrix_world = obj.matrix_world
        if obj.type == 'MESH':
            vertices = obj.data.vertices
            self.count = len(vertices)
            shape = (self.count, 3)

            # Copy verts co points
            points_object_space = np.empty(self.count * 3, dtype=np.float64)
            vertices.foreach_get('co', points_object_space)
            points_object_space.shape = shape
            if check_select:
                selected_mask = np.empty(self.count, dtype=bool)
                vertices.foreach_get('select', selected_mask)
                if filter_selected:
                    points_object_space = points_object_space[selected_mask]
                else:
                    points_object_space = points_object_space[~selected_mask]

        if obj.type == 'CURVE':
            all_points = quicksnap_utils.flatten(
                [[point.co for point in spline.bezier_points] for spline in obj.data.splines])
            all_points.extend(quicksnap_utils.flatten([[Vector((point.co[0], point.co[1], point.co[2]))
                                                        for point in spline.points] for spline in obj.data.splines]))
            self.count = len(all_points)
            shape = (self.count, 3)

            # Copy verts co points
            points_object_space = np.array(all_points)
            points_object_space.shape = shape
            if check_select:
                selected_mask = quicksnap_utils.flatten(
                    [[point.select_control_point for point in spline.bezier_points] for spline in obj.data.splines])
                selected_mask.extend(quicksnap_utils.flatten([[point.select for point in spline.points] for spline in
                                                              obj.data.splines]))
                selected_mask = np.array(selected_mask)
                if filter_selected:
                    points_object_space = points_object_space[selected_mask]
                else:
                    points_object_space = points_object_space[~selected_mask]

        # Get WorldSpace
        world_space_co = np.ones(shape=(len(points_object_space), 4), dtype=np.float64)
        world_space_co[:, :-1] = points_object_space  # cos v (x,y,z,1) - point,   v(x,y,z,0)- vector
        world_space_co = np.einsum('ij,aj->ai', matrix_world, world_space_co)
        self.world_space_co = world_space_co[:, :-1]

        # Get ViewSpace
        verts_viewspace = np.einsum('ij,aj->ai', perspective_matrix, world_space_co)  # Matrix mult
        filter_behind_camera = (verts_viewspace[:, 3] > 0)
        verts_viewspace = verts_viewspace[filter_behind_camera]  # Filtering behind camera

        # Get 2dScreenSpace
        self.screen_space_co = np.column_stack(
            (width_half + (verts_viewspace[:, 0] / verts_viewspace[:, 3]) * width_half,
             height_half + (verts_viewspace[:, 1] / verts_viewspace[:, 3]) * height_half))
        filter_outside_viewport = (self.screen_space_co[:, 0] > 0) & (self.screen_space_co[:, 1] > 0) & (
                self.screen_space_co[:, 0] < width) & (self.screen_space_co[:, 1] < height)
        self.screen_space_co = self.screen_space_co[filter_outside_viewport]

        # Raycast vars
        view_location = np.array(view_location)
        world_space_3d = self.world_space_co
        point_to_cam_vector = np.subtract(world_space_3d, view_location)
        self.raycast_distance = np.sqrt(np.einsum("ij,ij->i", point_to_cam_vector, point_to_cam_vector))
        self.raycast_direction = point_to_cam_vector / self.raycast_distance[:, None]

        # Misc
        self.object_id = object_id
        self.obstructed = []
        self.processed_point_count = 0

    def get_points_data(self, context, view_location, kdtree_insert, kdtree_obstructed_insert, kdtree_insert_index, batch_size):
        start_index=self.processed_point_count
        end_index = min(self.processed_point_count + batch_size, self.count - 1)
        result_points = []
        # print(f"start index:{start_index} - endIndex={end_index} - batch_size={batch_size}")
        for counter, index in enumerate(range(start_index, end_index + 1)):
            insert_id=kdtree_insert_index + counter
            # world_space[insert_id]=self.world_space_co[index]
            # coord_2d[insert_id]=self.screen_space_co[index]
            # object_id[insert_id]=self.object_id
            # world_space.append(self.world_space_co[index])
            # coord_2d.append(self.screen_space_co[index])
            # object_id.append(self.object_id)
            # (hit, hit_location, _, _, _, _) = bpy.context.scene.ray_cast(context.evaluated_depsgraph_get(),

            # hit = bpy.context.scene.ray_cast(context.evaluated_depsgraph_get(),
            #                                                              origin=view_location,
            #                                                              direction=self.raycast_direction[index],
            #                                                              distance=self.raycast_distance[index])
            # if not hit[0] or not (np.linalg.norm(np.array(hit[1])-self.world_space_co[index]) >= 0.001 * self.raycast_distance[index]):
            # if not hit[0] or not (np.sqrt(np.sum((np.array(hit[1])-self.world_space_co[index])**2)) >= 0.001 * self.raycast_distance[index]):
            kdtree_insert(self.world_space_co[index], insert_id)
            continue
            if not hit[0]:
                kdtree_insert(self.world_space_co[index], insert_id)
                # self.obstructed.append(False)
            else:

                vec = Vector(np.array(hit[1])-self.world_space_co[index])
                # if np.sqrt(np.dot(vec.T, vec)) >= 0.001 * self.raycast_distance[index]:
                if vec.length >= 0.001 * self.raycast_distance[index]:
                    kdtree_obstructed_insert(self.world_space_co[index], insert_id)
                else:
                    kdtree_insert(self.world_space_co[index], insert_id)
                # If the ray-cast hit, check how far the hit is to the point,
                # if it is close enough it is treated as non-obstructed.
                # self.obstructed.append((hit_location - Vector(self.world_space_co[index])).length >= 0.001 * Vector(self.raycast_distance[index]))
                # self.obstructed.append(np.linalg.norm(np.array(hit[1])-self.world_space_co[index]) >= 0.001 * self.raycast_distance[index])
                # self.obstructed.append(True)
                # print(f"distance={distance} - Obstructed: {np.linalg.norm(np.array(hit_location)-self.world_space_co[index]) >= 0.001 * self.raycast_distance}")
            # result_points.append((self.screen_space_co[index], self.obstructed[index]))
        self.processed_point_count = end_index+1
        if self.processed_point_count == self.count:
            self.completed = True
        # print(f"self.processed_point_count:{self.processed_point_count} - point_count:={self.count} - actual count:{end_index-start_index} - target count:{len(self.world_space_co[start_index:end_index + 1])}")
        return self.world_space_co[start_index:end_index + 1], self.screen_space_co[start_index:end_index + 1], np.full(end_index-start_index+1, self.object_id)
        # return end_index - start_index + 1


class SnapData:
    """
    SnapData stores the necessary to find the closest point in 2D amongst selection/scene verts, curve points, origins
    Transforming object/world position into 2D coordinates, and testing if they are obstructed via raycast is slow,
        therefor those operation are spread over multiple frames.
    """

    def __init__(self, context, region, selected_meshes, scene_meshes=None):
        self.is_origin_snapdata = scene_meshes is None
        self.iteration_finished = False
        self.width_half = region.width / 2.0
        self.height_half = region.height / 2.0
        self.width = region.width
        self.height = region.height
        rv3d = context.space_data.region_3d
        self.perspective_matrix = rv3d.perspective_matrix
        self.view_location = rv3d.view_matrix.inverted().translation
        self.to_process_selected = []
        self.to_process_scene = []
        self.to_process_vcount = {}
        self.obstructed = []
        self.processed = set()
        self.selected_ids = {}
        self.world_space = []
        self.region_2d = []
        self.object_id = []
        self.verts_data = {}
        self.objects_point_data = {}
        self.origins_map = {}
        self.snap_origins = quicksnap_utils.get_addon_settings().snap_objects_origin
        self.object_mode = context.active_object.mode == 'OBJECT'

        # Initialize kdtrees-target points nparray with correct size
        max_vertex_count = self.get_max_vertex_count(context, selected_meshes, scene_meshes)
        self.kd = mathutils.kdtree.KDTree(max_vertex_count)
        self.kd_obstructed = mathutils.kdtree.KDTree(max_vertex_count)
        print(f"max vertex count={max_vertex_count}")
        self.kd_np = mathutils.kdtree.KDTree(max_vertex_count)
        self.kd_obstructed_np = mathutils.kdtree.KDTree(max_vertex_count)
        self.world_space_np = np.empty((max_vertex_count, 3), dtype=np.float64)
        self.region_2d_np = np.empty((max_vertex_count, 2), dtype=np.float64)
        self.object_id_np = np.empty((max_vertex_count), dtype=np.int32)
        self.added_points_np = 0

        if not self.is_origin_snapdata:
            # If this snapdata contain target points, it can snap on scene and selection objects.
            self.scene_meshes = scene_meshes.copy()
            self.scene_meshes.extend(selected_meshes.copy())
            self.kd_origins = mathutils.kdtree.KDTree(len(self.scene_meshes))
            logger.info(f"self.kd_origins scene meshes: {len(self.scene_meshes)}")
        else:
            # If this snapdata contain source points, it can only snap on selection objects.
            self.scene_meshes = selected_meshes.copy()
            self.kd_origins = mathutils.kdtree.KDTree(len(selected_meshes))
            logger.info(f"self.kd_origins selection: {len(selected_meshes)}")

        # Add all objects origins to points
        self.add_scene_roots(context, selected_meshes, scene_meshes)

        self.meshes_selection = selected_meshes
        depsgraph = context.evaluated_depsgraph_get()

        # Add initial objects for target destination.
        if not self.is_origin_snapdata:
            # If Snapdata contains target points and we are in edit mode, add all selected meshes to
            # target objects lists (for snapping to unselected verts).
            if not self.object_mode:
                for selected_mesh in selected_meshes:
                    self.add_mesh_target(context, selected_mesh, is_selected=True)

            # Add meshes that do not have polygons. (cannot be found via ray-cast)
            for object_name in scene_meshes:
                obj = bpy.data.objects[object_name]
                if object_name not in selected_meshes and (
                        obj.type == 'CURVE' or (len(obj.data.vertices) > 0 and len(obj.data.polygons) == 0)):
                    self.add_mesh_target(context, object_name, depsgraph=depsgraph)

        # Add all objects for the snap origin (selected objects only).
        elif self.is_origin_snapdata:
            for selected_mesh in selected_meshes:
                self.add_object_source(context, selected_mesh)

        # if origin snapdata, start processing points immediately
        if self.is_origin_snapdata:
            self.process_iteration(context)
            # self.process_iteration(context, max_run_duration=0.5)
            # self.process_iteration(context,max_run_duration=5)

    def add_mesh_target(self, context, object_name, is_selected=False, depsgraph=None, set_first_priority=False):
        """
        Prepare object to be processes for the target SnapData.
        Adds object to the "To Process" list.
        If object is already in the list, eventually set to first in the priority list, for objects under the mouse.
        Store object verts/points into the verts_data dict
        """
        if object_name in self.processed:  # Skip already processed objects.
            return
        if is_selected:  # Process selected objects first.
            # Prioritize object if is in the list but not first in list.
            if object_name in self.to_process_selected:
                if self.to_process_selected.index(object_name) > 0:
                    logger.info(f"Addmesh:{object_name} - PRIORITIZE SELECTED")
                    self.to_process_selected.remove(object_name)
                    self.to_process_selected.insert(0, object_name)

            # Add object in the list if it is not already
            else:
                obj = bpy.data.objects[object_name]
                self.objects_point_data[object_name] = ObjectPointData(obj,
                                                                       self.scene_meshes.index(object_name),
                                                                       self.perspective_matrix,
                                                                       width=self.width,
                                                                       height=self.height,
                                                                       width_half=self.width_half,
                                                                       height_half=self.height_half,
                                                                       view_location=self.view_location,
                                                                       check_select=True,
                                                                       filter_selected=False)
                print(f"Adding to target verts data selected:{object_name}")
                if obj.type == 'MESH':
                    self.verts_data[object_name] = [(vert.index, vert.co.copy(), vert.select, 0, 0) for vert in
                                                    obj.data.vertices]

                elif obj.type == 'CURVE':
                    self.verts_data[object_name] = quicksnap_utils.flatten([[(index, point.co.copy(),
                                                                              point.select_control_point, spline_index,
                                                                              1) for index, point in
                                                                             enumerate(spline.bezier_points)] for
                                                                            spline_index, spline in
                                                                            enumerate(obj.data.splines)])
                    self.verts_data[object_name].extend(quicksnap_utils.flatten([[(index, Vector(
                        (point.co[0], point.co[1], point.co[2])), point.select, spline_index, 0) for index, point in
                                                                                  enumerate(spline.points)] for
                                                                                 spline_index, spline in
                                                                                 enumerate(obj.data.splines)]))
                self.to_process_selected.insert(0, object_name)
                self.to_process_vcount[object_name] = 0
        else:
            # Prioritize object if is in the list but not first in list.
            if object_name in self.to_process_scene:
                if self.to_process_scene.index(object_name) > 0 and set_first_priority:
                    logger.info(f"Addmesh:{object_name} - PRIORITIZE SCENE")
                    self.to_process_scene.remove(object_name)
                    self.to_process_scene.insert(0, object_name)

            # Add object in the list if it is not already
            else:
                logger.info(f"Addmesh:{object_name} -  FIRST ADD Scene")
                obj = bpy.data.objects[object_name].evaluated_get(depsgraph)
                self.objects_point_data[object_name] = ObjectPointData(obj,
                                                                       self.scene_meshes.index(object_name),
                                                                       self.perspective_matrix,
                                                                       width=self.width,
                                                                       height=self.height,
                                                                       width_half=self.width_half,
                                                                       height_half=self.height_half,
                                                                       view_location=self.view_location)
                print(f"Adding to target verts data scene:{object_name}")
                if obj.type == 'MESH':
                    self.verts_data[object_name] = [(vert.index, vert.co.copy(), vert.select, 0, 0) for vert in
                                                    obj.data.vertices]
                elif obj.type == 'CURVE':
                    self.verts_data[object_name] = quicksnap_utils.flatten([[(index, point.co.copy(),
                                                                              point.select_control_point, spline_index,
                                                                              1) for index, point in
                                                                             enumerate(spline.bezier_points)] for
                                                                            spline_index, spline in
                                                                            enumerate(obj.data.splines)])
                    self.verts_data[object_name].extend(quicksnap_utils.flatten([[(index, Vector(
                        (point.co[0], point.co[1], point.co[2])), point.select, spline_index, 0) for index, point in
                                                                                  enumerate(spline.points)] for
                                                                                 spline_index, spline in
                                                                                 enumerate(obj.data.splines)]))
                self.to_process_vcount[object_name] = 0
                self.to_process_scene.append(object_name)

    def add_scene_roots(self, context, selected_meshes, scene_meshes=None):
        """
        Add the origin of all objects to the points.
        scene_meshes is None when processing the origin snapdata.
        """
        insert_start_index = len(self.region_2d)

        # Source SnapData: Add origin only when we are in object mode.
        if scene_meshes is None:
            if bpy.context.active_object.mode == 'OBJECT':
                for object_name in selected_meshes:
                    self.add_object_root(context, object_name)

        # Target SnapData: Add selection origins only when we are not in object mode.
        # and add all non-selected objects origins, as well as cursor location.
        else:
            if bpy.context.active_object.mode != 'OBJECT':
                add_roots = scene_meshes
                add_roots.extend(selected_meshes)
                add_roots = set(add_roots)
            else:
                add_roots = [object_name for object_name in scene_meshes if object_name not in selected_meshes]
            # logger.info(f"add_scene_roots: {len(add_roots)}")
            for object_name in add_roots:
                self.add_object_root(context, object_name)

            # Add cursor location
            self.add_vertex(context, bpy.context.scene.cursor.location, mathutils.Matrix.Identity(4), object_index=-1)

        # If we only snap to origins when in "Snap to origin mode", do not add the origins to the normal points kdtrees
        if self.snap_origins == "ALWAYS":
            self.balance_tree(insert_start_index)  # prevents adding origin points to normal points kdtrees.
            self.kd_origins.balance()
        else:
            self.balance_tree()
            self.kd_origins.balance()

    def add_object_root(self, context, object_name):
        """
        Add single object origin to points list and to origins kdtree
        """
        # logger.debug(f"Add object root: {object_name}")
        if not self.add_vertex(context, Vector((0, 0, 0)), bpy.data.objects[object_name].matrix_world,
                               self.scene_meshes.index(object_name)):
            return
        insert_index = len(self.region_2d) - 1
        # logger.info(f"add_object_root: {object_name}")
        self.origins_map[insert_index] = object_name
        self.kd_origins.insert(Vector((self.region_2d[insert_index][0], self.region_2d[insert_index][1], 0)),
                               insert_index)

    def add_object_source(self, context, object_name):
        """
        Prepare object to be processes for the source SnapData.
        Adds object to the "To Process" list.
        If object is already in the list, eventually set to first in the priority list, for objects under the mouse.
        Store object verts/points into the verts_data dict
        """
        obj = bpy.data.objects[object_name]
        current_mode = quicksnap_utils.set_object_mode_if_needed()
        self.objects_point_data[object_name] = ObjectPointData(obj,
                                                               self.scene_meshes.index(object_name),
                                                               self.perspective_matrix,
                                                               width=self.width,
                                                               height=self.height,
                                                               width_half=self.width_half,
                                                               height_half=self.height_half,
                                                               view_location=self.view_location,
                                                               check_select=not self.object_mode,
                                                               filter_selected=True)
        print(f"Adding to source verts data:{object_name}")
        if obj.type == 'MESH':
            self.verts_data[object_name] = [(vert.index, vert.co.copy(), vert.select, 0, 0) for vert in
                                            obj.data.vertices]

        elif obj.type == 'CURVE':
            self.verts_data[object_name] = quicksnap_utils.flatten([[(
                index, point.co.copy(), point.select_control_point,
                spline_index, 1) for index, point in
                enumerate(spline.bezier_points)] for
                spline_index, spline in
                enumerate(obj.data.splines)])
            self.verts_data[object_name].extend(quicksnap_utils.flatten([[(index, Vector(
                (point.co[0], point.co[1], point.co[2])), point.select, spline_index, 0) for index, point in
                                                                          enumerate(spline.points)] for
                                                                         spline_index, spline in
                                                                         enumerate(obj.data.splines)]))

        quicksnap_utils.revert_mode(current_mode)
        self.selected_ids[object_name] = []
        self.to_process_selected.insert(0, object_name)
        self.to_process_vcount[object_name] = 0

    def add_vertex(self, context, vertex_co, world_space_matrix, object_index):
        """
        Process single vertex: Calculate and store world position, screen coordinate, and check of point is obstructed
        Returns True if the point is in camera frustum.
        """
        ws = world_space_matrix @ vertex_co
        ws_2 = Vector((ws[0], ws[1], ws[2], 1))
        view_space_projection = self.perspective_matrix @ ws_2
        if view_space_projection.w <= 0:  # Skip behind camera
            return False
        coord_2d = quicksnap_utils.transform_viewspace_coord2d(view_space_projection, self.width_half, self.height_half)

        # Skip out of view
        if coord_2d.x <= 0 or coord_2d.y <= 0 or coord_2d.x >= self.width or coord_2d.y >= self.height:
            return False

        # Point/Vert is in camera frustum, store world/view position.
        self.world_space.append(ws)
        self.region_2d.append((coord_2d[0], coord_2d[1], 0))
        self.object_id.append(object_index)

        # Check if point is obstructed using a ray-cast from the camera to the point.
        point_to_cam_vector = self.view_location - ws
        direction_to_point = (ws - self.view_location).normalized()
        distance_point_to_cam = point_to_cam_vector.length
        # print(f"Raycast - direction={direction_to_point}  - distance={distance_point_to_cam}")
        # (hit, location, _, _, _, _) = bpy.context.scene.ray_cast(context.evaluated_depsgraph_get(),
        #                                                          origin=self.view_location,
        #                                                          direction=direction_to_point,
        #                                                          distance=distance_point_to_cam)
        hit=False
        self.obstructed.append(False)
        return True
        if not hit:
            self.obstructed.append(False)
        else:
            # If the ray-cast hit, check how far the hit is to the point,
            # if it is close enough it is treated as non-obstructed.
            self.obstructed.append((location - ws).length >= 0.001 * distance_point_to_cam)
        return True

    def process_mesh_batch(self, context, object_name, is_selected, world_space_matrix, start_point_index,
                           object_points_count, batch_size=1000):
        """
        Process vertices/points that have been stored in the verts_data dictionary.
        This function process verts from {start_point_index} for a maximum of {batch_size} elements,
         until it reaches {object_points_count}

        Returns the last processed point index
        """
        object_index = self.scene_meshes.index(object_name)
        verts_data = self.verts_data[object_name]
        end_vertex_index = min(start_point_index + batch_size, object_points_count - 1)
        # logger.debug(f"====START==== process_mesh_batch from {start_vertex_index} to {end_vertex_index} "
        #              f"--Start len(self.region_2d):{len(self.region_2d)} - is_selected={is_selected} "
        #              f"- vertex count={len(verts_data)}")

        # For origin snapdata, only process selected verts in Edit mode, otherwise process all verts.
        if self.is_origin_snapdata:
            # logger.debug("Process source batch")
            if self.object_mode:
                for vertex in range(start_point_index, end_vertex_index + 1):
                    (index, co, selected, spline_index, bezier) = verts_data[vertex]
                    self.add_vertex(context, co, world_space_matrix, object_index)
                    self.selected_ids[object_name].append((index, co, spline_index, bezier))
            else:
                for vertex in range(start_point_index, end_vertex_index + 1):
                    (index, co, selected, spline_index, bezier) = verts_data[vertex]
                    if not selected:  # skip_unselected vertice
                        continue
                    self.add_vertex(context, co, world_space_matrix, object_index)
                    self.selected_ids[object_name].append((index, co, spline_index, bezier))

        # For target snapdata, only process unselected verts in Edit mode, otherwise process all verts.
        else:
            if is_selected:  # If we were in object mode, we can add unselected vertices to the target vertices.
                # logger.debug(f"Process target batch - is selected")
                for vertex in range(start_point_index, end_vertex_index + 1):
                    (index, co, selected, spline_index, bezier) = verts_data[vertex]
                    if selected:  # skip_selected vertice
                        continue
                    self.add_vertex(context, co, world_space_matrix, object_index)
            else:
                # logger.debug(f"Process target batch - not selected")
                for vertex in range(start_point_index, end_vertex_index + 1):
                    (index, co, selected, spline_index, bezier) = verts_data[vertex]
                    self.add_vertex(context, co, world_space_matrix, object_index)
        # logger.debug(f"====END==== process_mesh_batch from {start_vertex_index} to {end_vertex_index} --End len(self.region_2d):{len(self.region_2d)}")
        return end_vertex_index

    def process_mesh_batch_v2(self, context, object_name, kdtree_insert, kdtree_obstructed_insert, batch_size=1000):

        object_points_data = self.objects_point_data[object_name]
        end_vertex_index = min(object_points_data.processed_point_count + batch_size, object_points_data.count - 1)
        points = object_points_data.get_points_data(context, self.view_location,kdtree_insert, kdtree_obstructed_insert,self.added_points_np, batch_size)
        points_count=len(points[0])
        # print(f"already added points:{self.added_points_np}")
        # print(f"max point count:{len(self.world_space_np)}")
        # print(f"Added POINTS count:{points_count}")
        # print(f"Added object id count:{len(points_data[2])}")
        end_id = self.added_points_np+points_count
        # print(f"end_id:{end_id}")
        # self.world_space_np[self.added_points_np:end_id] = points_data[0]
        # self.region_2d_np[self.added_points_np:end_id] = points_data[1]
        # self.object_id_np[self.added_points_np:end_id] = points_data[2]
        self.added_points_np = end_id
        # for point in points_data[3]:
        #     if point[1]:
        #         print("add point to obstructed")
        #     else:
        #         print("add point to visible")
        # print(f"Finished? {object_points_data.count == object_points_data.processed_point_count}")
        return object_points_data.completed

    def balance_tree(self, start_index=None):
        """
        Adds stored points from start_index to the last added points into the kdtrees, then balance the trees
        If is not set, only balance the trees.
        """
        # logger.debug(f"balance_tree - Source:{self.is_source}")
        if start_index is not None:
            insert = self.kd.insert
            insert_obstructed = self.kd_obstructed.insert
            # logger.debug(f"Inserting from {start_index} to {len(self.region_2d)-1}. Then balance tree.")
            for i in range(start_index, len(self.region_2d)):
                # logger.debug(f"Inserting {i}")
                if self.obstructed[i]:
                    insert_obstructed(self.region_2d[i], i)
                else:
                    insert(self.region_2d[i], i)
        self.kd.balance()
        self.kd_obstructed.balance()

    def process_iteration(self, context, max_run_duration=50):
        """
        To be called every frame. Process verts/points per batch until the function has run for {max_run_duration}
        """
        if not self or self.iteration_finished:
            return False
        start_time = time.perf_counter()
        elapsed_time = 0
        current_tree_index = len(self.region_2d)
        # Process selected objects first
        kdtree_insert = self.kd_np.insert
        kdtree_obstructed_insert = self.kd_obstructed_np.insert
        if (self.is_origin_snapdata or not self.object_mode) and len(self.to_process_selected) > 0:
            logger.debug(f"Process selection - is_origin_snapdata={self.is_origin_snapdata}")
            for object_name in self.to_process_selected.copy():
                obj = bpy.data.objects[object_name]
                world_space_matrix = obj.matrix_world
                vertex_count = len(self.verts_data[object_name])
                current_vertex_index = self.to_process_vcount[object_name]
                # logger.debug(f"process_iteration selected: {object_name} - Current vertex index:{current_vertex_index} - vertex count:{vertex_count}")
                start_time_batch = time.perf_counter()
                counter = 0
                while not self.objects_point_data[object_name].completed:
                    self.process_mesh_batch_v2(context, object_name, kdtree_insert, kdtree_obstructed_insert)
                    counter += 1
                self.kd_np.balance()
                self.kd_obstructed_np.balance()
                print(f'batch process time v2={"{:10.4f}".format(time.perf_counter() - start_time_batch)} - Loop={counter}')
                start_time_batch = time.perf_counter()
                counter = 0
                while current_vertex_index < vertex_count - 1:
                    current_vertex_index = self.process_mesh_batch(context, object_name, True, world_space_matrix,
                                                                   current_vertex_index, vertex_count)
                    counter += 1
                    if current_vertex_index >= vertex_count - 1:
                        print(f"process_iteration selected:{object_name} - ALL VERTS ADDED - Current={current_vertex_index}")
                        del self.verts_data[object_name]
                        self.to_process_selected.remove(object_name)
                        del self.to_process_vcount[object_name]
                        self.processed.add(object_name)
                        self.balance_tree(current_tree_index)
                        current_tree_index = len(self.region_2d)
                        break
                    elapsed_time = (time.perf_counter() - start_time)
                    if elapsed_time > max_run_duration:
                        self.to_process_vcount[object_name] = current_vertex_index + 1
                        self.balance_tree(current_tree_index)
                        return True
                print(f'batch process time ={"{:10.4f}".format(time.perf_counter()-start_time_batch)} - Loop={counter}')
                if elapsed_time > max_run_duration:
                    self.balance_tree(current_tree_index)
                    return True

        if self.is_origin_snapdata:
            # If origin snapdata, ignore scene objects
            if len(self.to_process_selected) == 0:
                logger.debug("Process iteration source - finished")
                self.iteration_finished = True
                return False
            # logger.debug(f"Process iteration. Not processing scene={self.to_process_scene}")
            return False

        # Process scene objects
        if len(self.to_process_scene) > 0:
            logger.debug(f"Process Scene - is_origin_snapdata={self.is_origin_snapdata}")
            # logger.debug(f"Process iteration. To_Process={self.to_process_scene}")
            for selected_object in self.meshes_selection:
                bpy.data.objects[selected_object].hide_set(True)
            for object_name in self.to_process_scene.copy():
                obj = bpy.data.objects[object_name]
                world_space_matrix = obj.matrix_world
                print(f"process_mesh_batch - object:{object_name} - has verts_data:{object_name in self.verts_data}")
                if object_name not in self.verts_data:
                    continue
                vertex_count = len(self.verts_data[object_name])
                current_vertex_index = self.to_process_vcount[object_name]
                # logger.debug(f"process_iteration unselected: {object_name} - Current vertex index:{current_vertex_index} - vertex count:{vertex_count}")
                start_time_batch = time.perf_counter()
                while not self.objects_point_data[object_name].completed:
                    self.process_mesh_batch_v2(context, object_name, kdtree_insert, kdtree_obstructed_insert)
                print(f'batch process time v2={"{:10.4f}".format(time.perf_counter() - start_time_batch)}')
                start_time_batch = time.perf_counter()
                while current_vertex_index < vertex_count - 1:
                    current_vertex_index = self.process_mesh_batch(context, object_name, False, world_space_matrix,
                                                                   current_vertex_index, vertex_count)
                    if current_vertex_index >= vertex_count - 1:
                        # logger.debug(f"process_iteration unselected:{object_name} - ALL VERTS ADDED - Current={current_vertex_index} - total kdtree verts={len(self.world_space)}")
                        del self.verts_data[object_name]
                        self.to_process_scene.remove(object_name)
                        del self.to_process_vcount[object_name]
                        self.processed.add(object_name)
                        self.balance_tree(current_tree_index)
                        current_tree_index = len(self.region_2d)
                        break
                    elapsed_time = (time.perf_counter() - start_time)
                    if elapsed_time > max_run_duration:
                        for selected_object in self.meshes_selection:
                            bpy.data.objects[selected_object].hide_set(False)
                        self.to_process_vcount[object_name] = current_vertex_index + 1
                        self.balance_tree(current_tree_index)
                        return True
                print(f'batch process time ={"{:10.4f}".format(time.perf_counter()-start_time_batch)}')
                # logger.debug(f"All vertex done, there is time left")
                if elapsed_time > max_run_duration:
                    for selected_object in self.meshes_selection:
                        bpy.data.objects[selected_object].hide_set(False)
                    self.balance_tree(current_tree_index)
                    return True
            for selected_object in self.meshes_selection:
                bpy.data.objects[selected_object].hide_set(False)
                bpy.data.objects[selected_object].select_set(True)
        return False

    def find_closest(self, mouse_coord_screen_flat, search_obstructed=True, search_origins_only=False):
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
                close_points.append((origin, index, dist, dist))
                break

        else:
            # Search non obstructed points
            (co, index, dist) = self.kd.find(mouse_coord_screen_flat)
            if dist is not None and dist <= 40:
                origin = self.world_space[index]
                close_points.append((origin, index, dist, dist))

            # Search obstructed points if needed
            if search_obstructed:
                (co, index, dist) = self.kd_obstructed.find(mouse_coord_screen_flat)
                if dist is not None and dist <= 20:
                    origin = self.world_space[index]
                    close_points.append((origin, index, dist * 2, dist))

        # sort possible closest points if more than one point
        if len(close_points) == 1:
            closest_point_data = (
                close_points[0][1], close_points[0][3], self.scene_meshes[self.object_id[close_points[0][1]]],
                close_points[0][1] in self.origins_map)
        elif len(close_points) > 1:
            # If multiple points, sort by distance to mouse
            closest = sorted(close_points, key=lambda point: point[2])[0]
            closest_point_data = (closest[1], closest[3], self.scene_meshes[self.object_id[close_points[0][1]]],
                                  close_points[0][1] in self.origins_map)
        return closest_point_data

    def get_max_vertex_count(self, context, selected_meshes, scene_meshes):
        """
        Returns the maximum count of visible verts/points/origins in the scene
        """
        # logger.debug(f"get_max_vertex_count - source={self.is_source}")
        if self.is_origin_snapdata:
            max_vertex_count = len(selected_meshes)
            for obj_name in selected_meshes:
                obj = bpy.data.objects[obj_name]
                if obj.type == 'MESH':
                    max_vertex_count += len(obj.data.vertices)
                elif obj.type == 'CURVE':
                    max_vertex_count += sum(
                        [(len(spline.points) + len(spline.bezier_points)) for spline in obj.data.splines])
        else:
            if bpy.context.active_object.mode == 'OBJECT':
                # Gather vert count from scene stats
                stats_string = context.scene.statistics(context.view_layer)
                # logger.debug(f"stats_string: {stats_string} ")
                max_vertex_count = int(
                    [val for val in stats_string.split('|') if 'Verts' in val][0].split(':')[1].replace('.',
                                                                                                        '').replace(',',
                                                                                                                    ''))
            else:
                # Scene stats not available, parse whole scene.
                # Slow, need to find faster way of getting scene vertex count.
                max_vertex_count = 0
                depsgraph = context.evaluated_depsgraph_get()
                for obj_name in scene_meshes:
                    obj = bpy.data.objects[obj_name]
                    if obj.type == 'MESH':
                        max_vertex_count += len(obj.evaluated_get(depsgraph).data.vertices)
                    elif obj.type == 'CURVE':
                        max_vertex_count += sum(
                            [(len(spline.points) + len(spline.bezier_points)) for spline in obj.data.splines])

        # logger.debug(f"Max vertex count: {max_vertex_count} - source={self.is_source}")
        return max_vertex_count


def print_vector_array(vector_array):
    for index, vector in enumerate(vector_array):
        if index == 0:
            print(f"[{print_vector_simple(vector)}")
        else:
            print(print_vector_simple(vector))


def print_vector_simple(vector):
    vector_data = [x for x in vector]
    return vector_data
    # print(f"[{vector[0],vector[1],vector[2]}]")
