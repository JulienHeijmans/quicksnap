import bpy,mathutils,logging
from mathutils import Vector
from datetime import datetime
from . import quicksnap_utils

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name__)
class SnapData():
    def __init__(self, context,region,selected_meshes,scene_meshes=None):
        self.is_source=scene_meshes==None
        self.iteration_finished=False
        self.width_half = region.width / 2.0
        self.height_half = region.height / 2.0
        self.width = region.width
        self.height = region.height
        rv3d=context.space_data.region_3d
        self.perspective_matrix=rv3d.perspective_matrix
        self.view_location=rv3d.view_matrix.inverted().translation
        self.to_process_selected=[]
        self.to_process_scene=[]
        self.to_process_vcount={}
        self.obstructed=[]
        self.processed=set()
        self.selected_ids={}
        self.world_space=[]
        self.view_space=[]
        self.region_2d=[]
        self.object_id=[]
        self.verts_data={}
        self.origins_map={}
        self.snap_origins=quicksnap_utils.get_addon_settings().snap_objects_origin
        self.object_mode=context.active_object.mode=='OBJECT'
        max_vertex_count=self.get_max_vertex_count(context,selected_meshes,scene_meshes)

        self.kd=mathutils.kdtree.KDTree(max_vertex_count)
        self.kd_obstructed=mathutils.kdtree.KDTree(max_vertex_count)
        if scene_meshes:
            self.scene_meshes=scene_meshes.copy()
            self.scene_meshes.extend(selected_meshes.copy())
            self.kd_origins=mathutils.kdtree.KDTree(len(self.scene_meshes))
            logger.info(f"self.kd_origins scene meshes: {len(self.scene_meshes)}")
        else:
            self.scene_meshes=selected_meshes.copy()
            self.kd_origins=mathutils.kdtree.KDTree(len(selected_meshes))
            logger.info(f"self.kd_origins selection: {len(selected_meshes)}")
        self.add_scene_roots(context,selected_meshes,scene_meshes)

        self.meshes_selection=selected_meshes
        depsgraph=context.evaluated_depsgraph_get()
        if not self.is_source:
            if not self.object_mode:
                for selected_mesh in selected_meshes:
                    self.add_mesh_target(context, selected_mesh, is_selected=True)

            for object_name in scene_meshes: #Add meshes that do not have polygons. (We would never raycast against them)
                object=bpy.data.objects[object_name]
                if object.type=='CURVE' or (len(object.data.vertices)>0 and len(object.data.polygons)==0):
                    self.add_mesh_target(context, object_name,depsgraph=depsgraph)

        elif self.is_source:
            for selected_mesh in selected_meshes:
                self.add_object_source(context, selected_mesh)

        if self.is_source:
            self.process_iteration(context)
            # self.process_iteration(context,max_run_duration=5)


    def add_mesh_target(self, context, object_name, is_selected=False,depsgraph=None,set_first_priority=False):
        if object_name in self.processed:
            return
        if is_selected:
            if object_name in self.to_process_selected:
                if self.to_process_selected.index(object_name)>0:
                    logger.info(f"Addmesh:{object_name} - PRIORITIZE SELECTED")
                    self.to_process_selected.remove(object_name)
                    self.to_process_selected.insert(0,object_name)
            else:
                obj=bpy.data.objects[object_name]
                if obj.type=='MESH':
                    self.verts_data[object_name]=[(vert.index,vert.co.copy(),vert.select,0,0) for vert in obj.data.vertices]
                elif  obj.type=='CURVE':
                    self.verts_data[object_name]=quicksnap_utils.flatten([[(index,point.co.copy(),point.select_control_point,spline_index,1) for index,point in enumerate(spline.bezier_points)] for spline_index,spline in enumerate(obj.data.splines)])
                    self.verts_data[object_name].extend(quicksnap_utils.flatten([[(index,Vector((point.co[0],point.co[1],point.co[2])),point.select,spline_index,0) for index,point in enumerate(spline.points)] for spline_index,spline in enumerate(obj.data.splines)]))
                self.to_process_selected.insert(0,object_name)
                self.to_process_vcount[object_name]=0
        else:
            if object_name in self.to_process_scene:
                if self.to_process_scene.index(object_name)>0 and set_first_priority:
                    logger.info(f"Addmesh:{object_name} - PRIORITIZE SCENE")
                    self.to_process_scene.remove(object_name)
                    self.to_process_scene.insert(0,object_name)
            else:
                logger.info(f"Addmesh:{object_name} -  FIRST ADD Scene")
                obj=bpy.data.objects[object_name].evaluated_get(depsgraph)
                if obj.type=='MESH':
                    self.verts_data[object_name]=[(vert.index,vert.co.copy(),vert.select,0,0) for vert in obj.data.vertices]
                elif  obj.type=='CURVE':
                    self.verts_data[object_name]=quicksnap_utils.flatten([[(index,point.co.copy(),point.select_control_point,spline_index,1) for index,point in enumerate(spline.bezier_points)] for spline_index,spline in enumerate(obj.data.splines)])
                    self.verts_data[object_name].extend(quicksnap_utils.flatten([[(index,Vector((point.co[0],point.co[1],point.co[2])),point.select,spline_index,0) for index,point in enumerate(spline.points)] for spline_index,spline in enumerate(obj.data.splines)]))
                self.to_process_vcount[object_name]=0
                self.to_process_scene.append(object_name)

    def add_scene_roots(self,context,selected_meshes,scene_meshes=None):
        insert_start_index=len(self.region_2d)
        if scene_meshes==None:#source mesh
            if bpy.context.active_object.mode=='OBJECT':
                for object_name in selected_meshes:
                    self.add_object_root(context,object_name)
        else:
            if bpy.context.active_object.mode!='OBJECT':
                add_roots=scene_meshes
                add_roots.extend(selected_meshes)
                add_roots=set(add_roots)
            else:
                add_roots=[object_name for object_name in scene_meshes if object_name not in selected_meshes]
            logger.info(f"add_scene_roots: {len(add_roots)}")
            for object_name in add_roots:
                self.add_object_root(context,object_name)

            #Add cursor location
            self.add_vertex(context,bpy.context.scene.cursor.location,mathutils.Matrix.Identity(4),object_index=-1)



        if self.snap_origins=="ALWAYS":
            # logger.debug(f"Origins inserted... adding origins to all trees and balancing trees")
            self.balance_tree(insert_start_index)
            self.kd_origins.balance()
        else:
            self.balance_tree()
            # logger.debug(f"Origins inserted... balancing trees")
            self.kd_origins.balance()

    def add_object_root(self,context,object_name):
        # logger.debug(f"Add object root: {object_name}")
        if not self.add_vertex(context,Vector((0,0,0)),bpy.data.objects[object_name].matrix_world,self.scene_meshes.index(object_name)):
            return
        insert_index=len(self.region_2d)-1
        logger.info(f"add_object_root: {object_name}")
        self.origins_map[insert_index]=object_name
        self.kd_origins.insert(Vector((self.region_2d[insert_index][0],self.region_2d[insert_index][1],0)),insert_index)


    def add_object_source(self, context, object_name):
        obj=bpy.data.objects[object_name]
        current_mode=quicksnap_utils.set_object_mode_if_needed()
        if obj.type=='MESH':
            self.verts_data[object_name]=[(vert.index,vert.co.copy(),vert.select,0,0) for vert in obj.data.vertices]
        elif  obj.type=='CURVE':
            self.verts_data[object_name]=quicksnap_utils.flatten([[(index,point.co.copy(),point.select_control_point,spline_index,1) for index,point in enumerate(spline.bezier_points)] for spline_index,spline in enumerate(obj.data.splines)])
            self.verts_data[object_name].extend(quicksnap_utils.flatten([[(index,Vector((point.co[0],point.co[1],point.co[2])),point.select,spline_index,0) for index,point in enumerate(spline.points)] for spline_index,spline in enumerate(obj.data.splines)]))
            logger.debug(self.verts_data[object_name])

        quicksnap_utils.revert_mode(current_mode)
        self.selected_ids[object_name]=[]
        self.to_process_selected.insert(0,object_name)
        self.to_process_vcount[object_name]=0



    def add_vertex(self,context,vertex_co,world_space_matrix,object_index):
        ws=world_space_matrix@vertex_co
        ws_2=Vector((ws[0],ws[1],ws[2],1))
        view_space_projection = self.perspective_matrix @ ws_2
        if  view_space_projection.w <=0: #Skip behind camera
            return False
        coord_2d=quicksnap_utils.transform_viewspace_coord2d(view_space_projection,self.width_half,self.height_half)
        if coord_2d.x<=0 or coord_2d.y<=0 or coord_2d.x>=self.width or coord_2d.y>=self.height:  #Skip out of view
            return False
        self.world_space.append(ws)
        self.view_space.append((view_space_projection[0],view_space_projection[1],view_space_projection[2]))
        self.region_2d.append((coord_2d[0],coord_2d[1],0))
        self.object_id.append(object_index)
        point_to_cam_vector= self.view_location - ws
        direction=point_to_cam_vector.normalized()
        direction_to_point=(ws-self.view_location).normalized()
        distance_point_to_cam=point_to_cam_vector.length

        (hit,location,_,_,_,_)= bpy.context.scene.ray_cast(context.evaluated_depsgraph_get(),origin=self.view_location,direction=direction_to_point,distance=distance_point_to_cam)
        if not hit:
            self.obstructed.append(False)
        else:
            self.obstructed.append((location-ws).length>=0.001*distance_point_to_cam)
        return True


    def process_mesh_batch(self,context,object_name,is_selected,world_space_matrix,start_vertex_index,vertice_count,vertex_batch=500):
        object_index=self.scene_meshes.index(object_name)
        verts_data=self.verts_data[object_name]
        end_vertex_index=min(start_vertex_index+vertex_batch,vertice_count-1)
        # logger.debug(f"====START==== process_mesh_batch from {start_vertex_index} to {end_vertex_index} --Start len(self.region_2d):{len(self.region_2d)} - is_selected={is_selected} - vertex count={len(verts_data)}")


        if self.is_source:
            # logger.debug("Process source batch")
            if self.object_mode:
                for vertex in range(start_vertex_index,end_vertex_index+1):
                    (index,co,selected,spline_index,bezier)=verts_data[vertex]
                    self.add_vertex(context,co,world_space_matrix,object_index)
                    self.selected_ids[object_name].append((index,co,spline_index,bezier))
            else:
                for vertex in range(start_vertex_index,end_vertex_index+1):
                    (index,co,selected,spline_index,bezier)=verts_data[vertex]
                    if not selected: # skip_unselected vertice
                        continue
                    self.add_vertex(context,co,world_space_matrix,object_index)
                    self.selected_ids[object_name].append((index,co,spline_index,bezier))
        else:
            if is_selected: #If we were in object mode, we can add unselected vertice to the target vertice.    
                # logger.debug(f"Process target batch - is selected")
                for vertex in range(start_vertex_index,end_vertex_index+1):
                    (index,co,selected,spline_index,bezier)=verts_data[vertex]
                    if selected: # skip_selected vertice
                        continue
                    self.add_vertex(context,co,world_space_matrix,object_index)
            else:
                # logger.debug(f"Process target batch - not selected")
                for vertex in range(start_vertex_index,end_vertex_index+1):
                    (index,co,selected,spline_index,bezier)=verts_data[vertex]
                    self.add_vertex(context,co,world_space_matrix,object_index)
        # logger.debug(f"====END==== process_mesh_batch from {start_vertex_index} to {end_vertex_index} --End len(self.region_2d):{len(self.region_2d)}")
        return end_vertex_index

    def balance_tree(self,start_index=None):
        # logger.debug(f"balance_tree - Source:{self.is_source}")
        if start_index!=None:
            insert=self.kd.insert
            insert_obstructed=self.kd_obstructed.insert
            # logger.debug(f"Inserting from {start_index} to {len(self.region_2d)-1}. Then balance tree.")
            for i in range(start_index,len(self.region_2d)):
                # logger.debug(f"Inserting {i}")
                if self.obstructed[i]:
                    insert_obstructed(self.region_2d[i], i)
                else:
                    insert(self.region_2d[i], i)
        self.kd.balance()
        self.kd_obstructed.balance()



    def process_iteration(self,context,max_run_duration=0.003):
        if not self or self.iteration_finished: return
        start_time=datetime.now()
        elapsed_time=0
        current_tree_index=len(self.region_2d)
        # logger.debug(f"process_iteration - source={self.is_source}")
        if (self.is_source or not self.object_mode) and len(self.to_process_selected)>0:
            # logger.debug(f"Process selection - source={self.is_source}")
            for object_name in self.to_process_selected.copy():
                object=bpy.data.objects[object_name]
                world_space_matrix=object.matrix_world
                vertex_count=len(self.verts_data[object_name])
                current_vertex_index=self.to_process_vcount[object_name]
                # logger.debug(f"process_iteration selected: {object_name} - Current vertex index:{current_vertex_index} - vertex count:{vertex_count}")
                while(current_vertex_index<vertex_count-1):
                    current_vertex_index=self.process_mesh_batch(context, object_name, True, world_space_matrix, current_vertex_index, vertex_count)
                    if(current_vertex_index>=vertex_count-1):
                        # logger.debug(f"process_iteration selected:{object_name} - ALL VERTS ADDED - Current={current_vertex_index}")  
                        del self.verts_data[object_name]
                        self.to_process_selected.remove(object_name)
                        del self.to_process_vcount[object_name]
                        self.processed.add(object_name)
                        self.balance_tree(current_tree_index)
                        current_tree_index=len(self.region_2d)
                        break
                    elapsed_time=(datetime.now()-start_time).total_seconds()
                    if(elapsed_time>max_run_duration):
                        self.to_process_vcount[object_name]=current_vertex_index+1
                        self.balance_tree(current_tree_index)
                        return
                if(elapsed_time>max_run_duration):
                    self.balance_tree(current_tree_index)
                    return
        if self.is_source:
            if len(self.to_process_selected)==0:
                logger.debug("Process iteration source - finished")
                self.iteration_finished=True
                return
            # logger.debug(f"Process iteration. Not processing scene={self.to_process_scene}")
            return
        if len(self.to_process_scene)>0:
            # logger.debug(f"Process Scene - source={self.is_source}")
            # logger.debug(f"Process iteration. To_Process={self.to_process_scene}")
            for selected_object in self.meshes_selection:
                bpy.data.objects[selected_object].hide_set(True)
            for object_name in self.to_process_scene.copy():
                object=bpy.data.objects[object_name]
                world_space_matrix=object.matrix_world
                vertex_count=len(self.verts_data[object_name])
                current_vertex_index=self.to_process_vcount[object_name]
                # logger.debug(f"process_iteration unselected: {object_name} - Current vertex index:{current_vertex_index} - vertex count:{vertex_count}")

                while(current_vertex_index<vertex_count-1):
                    current_vertex_index=self.process_mesh_batch(context, object_name, False, world_space_matrix, current_vertex_index, vertex_count)
                    if(current_vertex_index>=vertex_count-1):
                        # logger.debug(f"process_iteration unselected:{object_name} - ALL VERTS ADDED - Current={current_vertex_index} - total kdtree verts={len(self.world_space)}")                       
                        del self.verts_data[object_name]
                        self.to_process_scene.remove(object_name)
                        del self.to_process_vcount[object_name]
                        self.processed.add(object_name)
                        self.balance_tree(current_tree_index)
                        current_tree_index=len(self.region_2d)
                        break
                    elapsed_time=(datetime.now()-start_time).total_seconds()
                    if(elapsed_time>max_run_duration):
                        for selected_object in self.meshes_selection:
                            bpy.data.objects[selected_object].hide_set(False)
                        self.to_process_vcount[object_name]=current_vertex_index+1
                        self.balance_tree(current_tree_index)
                        return
                # logger.debug(f"All vertex done, there is time left")
                if(elapsed_time>max_run_duration):
                    for selected_object in self.meshes_selection:
                        bpy.data.objects[selected_object].hide_set(False)
                    self.balance_tree(current_tree_index)
                    return
            for selected_object in self.meshes_selection:
                bpy.data.objects[selected_object].hide_set(False)
                bpy.data.objects[selected_object].select_set(True)
        return

    def find_closest(self,context,mouse_coord_screen_flat,view_location,search_obtructed=True,search_origins_only=False):
        '''
        returns tuple (id of the closest point,distance to closest point in pixels,target object name, bool: is the point an object origin)
        '''

        if not len(self.region_2d)>0:
            return None
        closest_point_data=None
        close_points=[]

        if search_origins_only:
            points=self.kd_origins.find_n(mouse_coord_screen_flat,1)
            for (co, index, dist) in points:
                if dist>40:
                    break
                origin=self.world_space[index]
                close_points.append((origin,index,dist,dist))
                break

        else:
            #Search non obstructed points
            (co, index, dist)=self.kd.find(mouse_coord_screen_flat)
            if dist is not None and dist<=40:
                origin=self.world_space[index]
                close_points.append((origin,index,dist,dist))

            #Search obstructed points
            if search_obtructed:
                (co, index, dist)=self.kd_obstructed.find(mouse_coord_screen_flat)
                if dist is not None and dist<=20:
                    origin=self.world_space[index]
                    close_points.append((origin,index,dist*2,dist))

        if len(close_points)==1:
            closest_point_data=(close_points[0][1], close_points[0][3],self.scene_meshes[self.object_id[close_points[0][1]]], close_points[0][1] in self.origins_map)
        elif len(close_points)>1:
            #If multiple points, sort by distance to mouse
            closest=sorted(close_points, key=lambda point: point[2])[0]
            closest_point_data=(closest[1], closest[3],self.scene_meshes[self.object_id[close_points[0][1]]], close_points[0][1] in self.origins_map)
        return  closest_point_data

    def get_max_vertex_count(self,context,selected_meshes,scene_meshes):
        # logger.debug(f"get_max_vertex_count - source={self.is_source}")
        if self.is_source:
            # max_vertex_count=sum([len(bpy.data.objects[mesh_name].data.vertices) for mesh_name in selected_meshes])
            max_vertex_count=len(selected_meshes)
            for obj_name in selected_meshes:
                obj=bpy.data.objects[obj_name]
                if obj.type=='MESH':
                    max_vertex_count+=len(obj.data.vertices)
                elif obj.type=='CURVE':
                    # for spline in obj.data.splines:
                    #     logger.debug(f"Spline - {(len(spline.points) + len(spline.bezier_points))}")
                    max_vertex_count+=sum([(len(spline.points) + len(spline.bezier_points)) for spline in obj.data.splines])
        else:
            if(bpy.context.active_object.mode=='OBJECT'):
                stats_string=context.scene.statistics(context.view_layer)
                # logger.debug(f"stats_string: {stats_string} ")
                max_vertex_count=int([val for val in stats_string.split('|') if 'Verts' in val][0].split(':')[1].replace('.','').replace(',',''))
            else: #Slow, need to find faster way of getting scene vertex count.
                stats_string=context.scene.statistics(context.view_layer)
                # logger.debug(f"stats_string: {stats_string} ")
                max_vertex_count=0
                depsgraph = context.evaluated_depsgraph_get()
                for obj_name in scene_meshes:
                    obj=bpy.data.objects[obj_name]
                    if obj.type=='MESH':
                        max_vertex_count+=len(obj.evaluated_get(depsgraph).data.vertices)
                    elif obj.type=='CURVE':
                        # for spline in obj.data.splines:
                        #     logger.debug(f"Spline - {(len(spline.points) + len(spline.bezier_points))}")
                        max_vertex_count+=sum([(len(spline.points) + len(spline.bezier_points)) for spline in obj.data.splines])
                # max_vertex_count=sum(len(bpy.data.objects[object_name].evaluated_get(depsgraph).data.vertices) for object_name in scene_meshes)

                # revert_mode(previous_mode)
        # logger.debug(f"Max vertex count: {max_vertex_count} - source={self.is_source}")
        return max_vertex_count