import bpy,mathutils,bmesh,logging
from . import quicksnap_utils
from .quicksnap_utils import State
from .quicksnap_snapdata import  SnapData
from . import  quicksnap_render
from bpy_extras import view3d_utils
from mathutils import Vector

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name__)
addon_keymaps = []

mouse_pointer_offsets = [
    Vector((-40,-40)),
    Vector((-40,0)),
    Vector((-40,40)),
    Vector((0,40)),
    Vector((40,40)),
    Vector((40,0)),
    Vector((40,-40)),
    Vector((0,-40))
    ]

def check_close_objects(context,region,depsgraph, mouse_position):
    mouse_position=Vector(mouse_position)
    points=[mouse_position]
    points.extend([mouse_position+point for point in mouse_pointer_offsets])
    hit_objects=[]
    # logger.info(f"check_close_objects: {points}")
    for point in points:
        view_position = view3d_utils.region_2d_to_origin_3d(region, context.space_data.region_3d, point)
        mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, point)
        (hit,_,_,_,object,*_)=context.scene.ray_cast(depsgraph,origin=view_position,direction=mouse_vector)
        if hit:
            hit_objects.append(object)
    # logger.info(f"hit_objects: {hit_objects}")
    return hit_objects


class QuickVertexSnapOperator(bpy.types.Operator):
    bl_idname = "object.quick_vertex_snap"
    bl_label = "Quick Vertex Snap"
    bl_options = {'INTERNAL','UNDO'}    
    
    contraint_x : bpy.props.BoolProperty(default=False)
    
    def initialize(self,context):
        
        context.area.header_text_set(f"QuickSnap: Pick a vertex/point from the selection to start move-snapping")
        self.snapping=""
        self.snapping_local=False
        self.settings=get_addon_settings()
        selection_meshes=quicksnap_utils.get_selection_meshes()
        if not selection_meshes or len(selection_meshes)==0:
            return False
        self.selection_meshes=[obj.name for obj in selection_meshes]
        self.processed_meshes=self.selection_meshes.copy()
        self.current_state=State.IDLE
        self.closest_source_id=-1
        self.closest_target_id=-1
        self.closest_actionnable=False
        self.distance=0
        self.target=None
        self.target2d=None
        self.camera_moved=False
        self.target_object=""
        self.target_object_is_root=False
        self.target_object_show_wire_backup=False
        self.target_object_show_name_backup=False
        self.target_object_show_texture_space_backup=False
        self.object_mode=bpy.context.active_object.mode=='OBJECT'
        self.snap_to_origins=False
        region=None
        for region_item in context.area.regions:
            if region_item.type=='WINDOW':
                region=region_item
                
        if not region:
            return False
        
        self.vertex_source_data_v2=SnapData(context,region,self.selection_meshes)
        self.vertex_target_data_v2=SnapData(context,region,self.selection_meshes,quicksnap_utils.get_scene_meshes(True))
        
        self.view_direction=context.space_data.region_3d.view_rotation @ mathutils.Vector((0, 0, -1))
        self.closest_target_object=""
        
        region3d=context.space_data.region_3d
        self.view_location=region3d.view_matrix.inverted().translation
        self.perspective_matrix=context.space_data.region_3d.perspective_matrix
        self.perspective_matrix_inverse=self.perspective_matrix.inverted()
        #backup object/vertex data        
        self.backup_data(context)        
        self.update(context)
        return True
    
    def backup_data(self,context):
        self.backup_object_positions={}
        if self.object_mode:
            selection=quicksnap_utils.keep_only_parents([bpy.data.objects[obj_name] for obj_name in  self.selection_meshes])
            for object in selection:
                self.backup_object_positions[object.name]=object.matrix_world.copy()
        else:
            self.backup_vertice_positions={}
            self.bmeshs={}
            for object_name in self.vertex_source_data_v2.selected_ids:                
                object=bpy.data.objects[object_name]
                if object.type=="MESH":
                    self.bmeshs[object_name]=bmesh.new()
                    self.bmeshs[object_name].from_mesh(object.data)
                    self.backup_vertice_positions[object_name]=[(index,co,0,0,0,0) for (index,co,_,_) in self.vertex_source_data_v2.selected_ids[object_name]]
                elif object.type=="CURVE":
                    self.backup_vertice_positions[object_name]=[]
                    for (index,co,spline_index,bezier) in self.vertex_source_data_v2.selected_ids[object_name]:
                        if bezier==1:
                            point=object.data.splines[spline_index].bezier_points[index]
                            logger.info(f"Backup point: {point.co} - handles: {point.handle_left} - {point.handle_right}")
                            self.backup_vertice_positions[object_name].append((spline_index,index,co.copy(),bezier,point.handle_left.copy(),point.handle_right.copy()))
                        else:
                            point=object.data.splines[spline_index].points[index]
                            self.backup_vertice_positions[object_name].append((spline_index,index,co.copy(),bezier,0,0))
    
    def set_target_object(self, target_object="", is_root=False):
        if(self.target_object==target_object):
            if self.target_object_is_root != is_root:
                bpy.data.objects[self.target_object].show_texture_space=is_root or self.target_object_show_texture_space_backup
                bpy.data.objects[self.target_object].show_name=is_root or self.target_object_show_name_backup
                self.target_object_is_root=is_root
            return
        if self.target_object!="":
            bpy.data.objects[self.target_object].show_wire=self.target_object_show_wire_backup
            bpy.data.objects[self.target_object].show_texture_space=self.target_object_show_texture_space_backup
            bpy.data.objects[self.target_object].show_name=self.target_object_show_name_backup
        if target_object!="":
            self.target_object_show_wire_backup=bpy.data.objects[target_object].show_wire 
            self.target_object_show_name_backup=bpy.data.objects[target_object].show_name
            self.target_object_show_texture_space_backup=bpy.data.objects[target_object].show_texture_space
            bpy.data.objects[target_object].show_wire= self.settings.display_target_wireframe
            if is_root:
                bpy.data.objects[target_object].show_texture_space=True
                bpy.data.objects[target_object].show_name=True
        self.target_object=target_object
        self.target_object_is_root=is_root
    
    def revert_data(self,context,apply=False):
        if self.object_mode:
            for object_name in self.backup_object_positions:
                bpy.data.objects[object_name].matrix_world=self.backup_object_positions[object_name].copy()
        else:
            object_mode_backup=quicksnap_utils.set_object_mode_if_needed()
            for object_name in self.backup_vertice_positions:
                object=bpy.data.objects[object_name]
                if object.type=="MESH":
                    if hasattr(self.bmeshs[object_name].verts, "ensure_lookup_table"):
                        self.bmeshs[object_name].verts.ensure_lookup_table()
                    for (index,co,_,_,_,_) in self.backup_vertice_positions[object_name]:
                        self.bmeshs[object_name].verts[index].co=co
                    if apply:
                        self.bmeshs[object_name].to_mesh(bpy.data.objects[object_name].data)
                elif object.type=="CURVE" and apply:  
                    data=object.data
                    for (curveindex,index,co,bezier,left,right) in self.backup_vertice_positions[object_name]:
                        if bezier==1:
                            data.splines[curveindex].bezier_points[index].co=co
                            data.splines[curveindex].bezier_points[index].handle_left=left
                            data.splines[curveindex].bezier_points[index].handle_right=right                            
                        else:
                            data.splines[curveindex].points[index].co=Vector((co[0],co[1],co[2],data.splines[curveindex].points[index].co[3]))

            quicksnap_utils.revert_mode(object_mode_backup)

    
    def update(self,context):
        # logger.info(f"==UPDATE==")        
        region=None
        for area_region in context.area.regions:
            if area_region.type=='WINDOW':
                region=area_region
        view_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, self.mouse_position)
        #The 3D location in this direction
        view_position = view3d_utils.region_2d_to_origin_3d(region, context.space_data.region_3d, self.mouse_position)
        mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, self.mouse_position)
        mouse_coord_world_space = view3d_utils.region_2d_to_location_3d(region, context.space_data.region_3d, self.mouse_position, view_vector)
        mouse_coord_screen_flat=Vector((self.mouse_position[0],self.mouse_position[1],0))
        
        search_obstructed=context.space_data.shading.show_xray or not self.settings.filter_search_obstructed
        depsgraph=context.evaluated_depsgraph_get()
        if self.current_state==State.IDLE:
            (direct_hit,_,_,_,direct_hit_object,_)=context.scene.ray_cast(context.evaluated_depsgraph_get(),origin=view_position,direction=mouse_vector)
            if(direct_hit and direct_hit_object.name in self.selection_meshes):
                self.vertex_source_data_v2.add_mesh_target(context, direct_hit_object.name,depsgraph=depsgraph,is_selected=True,set_first_priority=True) #bring direct hit to the top of the to_process stack if needed.
            closest=self.vertex_source_data_v2.find_closest(context,mouse_coord_screen_flat, self.view_location,search_obtructed=search_obstructed,search_origins_only=self.snap_to_origins)
            if closest!=None:
                (self.closest_source_id, self.distance, target_name,is_root)=closest
                self.set_target_object(target_name,is_root)
                if self.distance<=15:
                    self.closest_actionnable=True
                    bpy.context.window.cursor_set("SCROLL_XY")
                else:
                    self.closest_actionnable=False
                    bpy.context.window.cursor_set("CROSSHAIR")
            else:
                self.closest_source_id = -1
                self.set_target_object("")
                self.distance = -1
                self.closest_actionnable=False
                bpy.context.window.cursor_set("CROSSHAIR")    
        elif self.current_state==State.SOURCE_PICKED:
            
            
            if self.snap_to_origins:
                closest=self.vertex_target_data_v2.find_closest(context,mouse_coord_screen_flat, self.view_location,search_origins_only=True)
                if closest!=None:
                    (self.closest_target_id, self.distance, target_object_name,is_root)=closest
                    self.set_target_object(target_object_name,is_root)
                else:
                    self.closest_target_id = -1
                    self.distance = -1
                    self.set_target_object("")
            
            else:
                for object in self.selection_meshes:
                    bpy.data.objects[object].hide_set(True)
                (direct_hit,_,_,_,direct_hit_object,_)=context.scene.ray_cast(context.evaluated_depsgraph_get(),origin=view_position,direction=mouse_vector)
                if(direct_hit):
                    self.vertex_target_data_v2.add_mesh_target(context, direct_hit_object.name,depsgraph=depsgraph,set_first_priority=True) #bring direct hit to the top of the to_process stack if needed.
                for object in self.vertex_target_data_v2.processed:
                    bpy.data.objects[object].hide_set(True)
    
                #add close objects to the to_process list
                close_objects=check_close_objects(context,region,context.evaluated_depsgraph_get(),mouse_position=self.mouse_position) 
                for object in self.vertex_target_data_v2.processed: #unhiding processed objects, for obstruction check
                    bpy.data.objects[object].hide_set(False)
                for object in close_objects:
                    self.vertex_target_data_v2.add_mesh_target(context, object.name,depsgraph=depsgraph)
    
                for object in self.selection_meshes:
                    bpy.data.objects[object].hide_set(False)
                for object in self.selection_meshes: #re-select selection
                    bpy.data.objects[object].select_set(True)            
                
                #Find closest targets
                closest=self.vertex_target_data_v2.find_closest(context,mouse_coord_screen_flat, self.view_location,search_obtructed=search_obstructed)
                if closest!=None:
                    (self.closest_target_id, self.distance, target_object_name,is_root)=closest
                    self.set_target_object(target_object_name,is_root)
                else:
                    self.closest_target_id = -1
                    self.distance = -1
                    self.set_target_object("")
                # pass
            
        axis_msg=""
        snapping_msg=f"Use (Shift+)X/Y/Z to constraint to the world/local axis or plane. Use O to snap to object origins. Right Mouse Button/ESC to cancel the operation. "
        if self.snap_to_origins:
            snapping_msg="Snapping to origins only. "
        if len(self.snapping)>0:
            if not self.snap_to_origins:
                snapping_msg=""
            if len(self.snapping)==1:
                snapping_msg=f"{snapping_msg}Constrained on {self.snapping} axis"
            if len(self.snapping)==2:
                snapping_msg=f"{snapping_msg}Constrained on {self.snapping} plane"
            if self.snapping_local:
                axis_msg=("(Local)")
            else:
                axis_msg=("(World)")
        if self.current_state==State.IDLE:
            context.area.header_text_set(f"QuickSnap: Pick the source vertex/point. {snapping_msg}{axis_msg}")
        elif  self.current_state==State.SOURCE_PICKED:
            context.area.header_text_set(f"QuickSnap: Move the mouse over the target vertex/point. {snapping_msg}{axis_msg}")
            
    def apply(self,context):
        self.target=None
        self.target2d=None
        if self.current_state==State.SOURCE_PICKED:
            region=None
            header=None
            
            for area_region in context.area.regions:
                if area_region.type=='WINDOW':
                    region=area_region
                    
            self.revert_data(context)
            origin=self.vertex_source_data_v2.world_space[self.closest_source_id]
            if len(self.snapping)==0 or not self.snapping_local: # no local object constraint
                if self.closest_target_id>=0:
                    self.target=self.vertex_target_data_v2.world_space[self.closest_target_id]
                    self.target=quicksnap_utils.get_axis_target(origin,self.target,self.snapping)
                else:
                    camera_position=    view3d_utils.region_2d_to_origin_3d(region, context.space_data.region_3d, self.mouse_position)
                    camera_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, self.mouse_position)
                    #The 3D location in this direction
                    self.target=quicksnap_utils.get_target_nosnap(origin, camera_position, camera_vector, self.snapping)
                    
                translation=mathutils.Matrix.Translation(Vector(self.target)-Vector(origin))
                    
                if self.object_mode:
                     for  obj_name in self.backup_object_positions:
                         quicksnap_utils.translate_object_worldspace(bpy.data.objects[obj_name],translation)
                else:
                    # logger.info("apply no snapping")
                    object_mode_backup=quicksnap_utils.set_object_mode_if_needed()
                    for object_name in self.backup_vertice_positions:
                        obj=bpy.data.objects[object_name]
                        if obj.type=="MESH":
                            vertexids=[vert[0] for vert in self.backup_vertice_positions[object_name]]
                            quicksnap_utils.translate_vertice_worldspace(obj,self.bmeshs[object_name],vertexids,translation)
                        elif obj.type=="CURVE":
                            logger.info(f"Apply - backupdata={self.backup_vertice_positions[object_name][0]}")
                            quicksnap_utils.translate_curvepoints_worldspace(obj,self.backup_vertice_positions[object_name],translation)
                    quicksnap_utils.revert_mode(object_mode_backup)                
            else:
                translations=[]
                if self.closest_target_id>=0:
                    base_target=self.vertex_target_data_v2.world_space[self.closest_target_id]
                    for object_name in self.selection_meshes:
                        self.target=quicksnap_utils.get_axis_target(origin,base_target,self.snapping,bpy.data.objects[object_name])
                        
                        translations.append(mathutils.Matrix.Translation(Vector(self.target)-Vector(origin)))
                else:
                    camera_position=    view3d_utils.region_2d_to_origin_3d(region, context.space_data.region_3d, self.mouse_position)
                    camera_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, self.mouse_position)
                    #The 3D location in this direction
                    for object_name in self.selection_meshes:
                        self.target=quicksnap_utils.get_target_nosnap(origin, camera_position, camera_vector, self.snapping, bpy.data.objects[object_name])                        
                        translations.append(mathutils.Matrix.Translation(self.target-Vector(origin)))

                

                if self.object_mode:
                    for  object_name,translation in zip(self.selection_meshes,translations):
                        quicksnap_utils.translate_object_worldspace(bpy.data.objects[object_name],translation)
                else:
                    object_mode_backup=quicksnap_utils.set_object_mode_if_needed()
                    for object_name,translation in zip(self.backup_vertice_positions,translations):
                        vertexids=[vert[0] for vert in self.backup_vertice_positions[object_name]]
                        quicksnap_utils.translate_vertice_worldspace(bpy.data.objects[object_name],self.bmeshs[object_name],vertexids,translation)
                    quicksnap_utils.revert_mode(object_mode_backup)

            self.target2d=quicksnap_utils.transform_worldspace_coord2d(self.target,region,context.space_data.region_3d)




    def __init__(self):
        pass
        # logger.info("Start")

    def __del__(self):   
        pass
        # logger.info("End")
        
    def refresh_vertex_data(self,context,event):
        # logger.info("refresh data")
        region3d=context.space_data.region_3d
        self.view_location=region3d.view_matrix.inverted().translation
        self.perspective_matrix=context.space_data.region_3d.perspective_matrix
        self.perspective_matrix_inverse=self.perspective_matrix.inverted()

        region=None
        for region_item in context.area.regions:
            if region_item.type=='WINDOW':
                region=region_item

        self.vertex_source_data_v2.__init__(context,region,self.selection_meshes)
        self.vertex_target_data_v2.is_enabled=False
        self.vertex_target_data_v2.__init__(context,region,self.selection_meshes,quicksnap_utils.get_scene_meshes(True))
        

    def modal(self, context, event):
        if self.current_state==State.IDLE:
            self.vertex_source_data_v2.process_iteration(context)
            if self.vertex_source_data_v2.iteration_finished:
                self.vertex_target_data_v2.process_iteration(context)
        else:
            self.vertex_target_data_v2.process_iteration(context)
        context.area.tag_redraw()
        self.handle_snap_hotkey(context,event)
        
        # allow navigation
        if event.type in {'MIDDLEMOUSE','WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self.camera_moved=True
            return {'PASS_THROUGH'}
        
        if event.type == 'MOUSEMOVE':  # Apply
            if self.camera_moved:
                self.refresh_vertex_data(context,event)
                self.camera_moved=False
            self.update_mouse_position(context,event)
            self.update(context)
            self.apply(context)
            
        elif event.type == 'LEFTMOUSE':  # Confirm
            if self.current_state==State.IDLE and self.closest_source_id>=0 and self.closest_actionnable:
                self.current_state=State.SOURCE_PICKED
                self.set_target_object("")
            else:  
                self.terminate(context)
                return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:  # Cancel            
            self.terminate(context,revert=True)
            return {'CANCELLED'}       
        
        return {'RUNNING_MODAL'}

    def handle_snap_hotkey(self,context,event):
        # logger.info(f"Event: {event.type}")
        if event.is_repeat or event.value!='PRESS':
            return
        event_type=event.type
        if event_type=='X':
            if event.shift:
                new_snapping='YZ'
            else:
                new_snapping='X'
            if self.snapping==new_snapping:
                if self.snapping_local==False and len(self.selection_meshes)==1:
                    self.snapping_local = not self.snapping_local
                else:
                    self.snapping_local=False
                    self.snapping=""
            else:
                self.snapping=new_snapping
            self.update(context)
            self.apply(context)
        elif event_type=='Y':
            if event.shift:
                new_snapping='XZ'
            else:
                new_snapping='Y'
            if self.snapping==new_snapping:
                if self.snapping_local==False and len(self.selection_meshes)==1:
                    self.snapping_local = not self.snapping_local
                else:
                    self.snapping_local=False
                    self.snapping=""
            else:
                self.snapping=new_snapping
            self.update(context)
            self.apply(context)
        elif event_type=='Z':
            if event.shift:
                new_snapping='XY'
            else:
                new_snapping='Z'
            if self.snapping==new_snapping:
                if self.snapping_local==False and len(self.selection_meshes)==1:
                    self.snapping_local = not self.snapping_local
                else:
                    self.snapping_local=False
                    self.snapping=""
            else:
                self.snapping=new_snapping
            self.update(context)
            self.apply(context)
        elif event_type=='O':
            self.snap_to_origins=not self.snap_to_origins
            self.update(context)
            self.apply(context)
            
    def terminate(self,context,revert=False):
        # logger.info("terminate")
        if revert:
            self.revert_data(context,apply=True)
            
        self.set_target_object("")
        context.area.header_text_set(None)
        context.window.cursor_set("DEFAULT")
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        self.vertex_target_data_v2.is_enabled=False
        # if self.vertex_target_data_v2.ready:
        #     utils.run_asyn_sync(self.vertex_target_data_v2.end())
        # bpy.types.SpaceView3D.draw_handler_remove(self._handle_view, 'WINDOW')
        del self
        
    def update_mouse_position(self,context,event):
        self.mouse_position=(event.mouse_x-context.area.x, event.mouse_y-context.area.y)
        
    def invoke(self, context, event):
        if context.area==None:
            return {'CANCELLED'}
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}
            
        context.window.cursor_set("DEFAULT")
        self.update_mouse_position(context,event)
        
        if not self.initialize(context):
            return {'CANCELLED'}

        args = (self, context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(quicksnap_render.draw_callback_2D, args, 'WINDOW', 'POST_PIXEL')
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(quicksnap_render.draw_callback_3D, args, 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}




def get_addon_settings():
    addon = bpy.context.preferences.addons.get(__name_addon__)
    if addon:
        return addon.preferences
    return None

class QuickVertexSnapPreference(bpy.types.AddonPreferences):
    bl_idname = __name_addon__

    draw_rubberband : bpy.props.BoolProperty(name="Draw Rubber Band",default=True)
    # filter_search_obstructed : bpy.props.BoolProperty(name="Ignore non visible vertices when xRay is disabled",default=True)
    filter_search_obstructed : bpy.props.BoolProperty(name="Only snap from/to non visible points when in xRay",default=False)
    snap_objects_origin : bpy.props.EnumProperty(
        name="Snap from/to objects origins",
        items=[
            ("ALWAYS", "Always ON", "", 0),
            ("KEY", "Only when holding \"O\" key", "", 1)
        ],
        default="ALWAYS",)
    display_target_wireframe : bpy.props.BoolProperty(name="Display target object wireframe",default=True)
    def draw(self, context):
        layout = self.layout
        col=layout.column(align=True)
        col.use_property_split = True
        col.prop(self,"filter_search_obstructed")
        col.prop(self,"snap_objects_origin")
        col.prop(self,"draw_rubberband")
        col.prop(self,"display_target_wireframe")

        box_content=layout.box()
        header = box_content.row(align=True)
        header.label(text="Keymap",icon='EVENT_A')
        col=box_content.column(align=True)
        col.use_property_split = False
        global addon_keymaps
        key_config = bpy.context.window_manager.keyconfigs.addon
        categories=set([cat for (cat, key) in addon_keymaps])
        id_names=[key.idname for (cat, key) in addon_keymaps]
        for cat in categories:
            active_cat=key_config.keymaps.find(cat.name,space_type=cat.space_type,region_type=cat.region_type).active()
            for active_key in active_cat.keymap_items:
                if active_key.idname in id_names:
                    quicksnap_utils.display_keymap(active_key,col)
        col.separator()
        col.label(text="Modifier hotkeys:")
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_X',"Constraint to X Axis")
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_X',"Constraint to X Plane",shift=True)
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_Y',"Constraint to Y Axis")
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_Y',"Constraint to Y Plane",shift=True)
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_Z',"Constraint to Z Axis")
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_Z',"Constraint to Z Plane",shift=True)
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_O',"Snap to objects origins only")
        quicksnap_utils.insert_ui_hotkey(col,'EVENT_ESC',"Cancel Snap")
        quicksnap_utils.insert_ui_hotkey(col,'MOUSE_RMB',"Cancel Snap")
                    
# class MYADDONNAME_TOOL_mytool(bpy.types.WorkSpaceTool):
#     bl_idname = "myaddonname.mytool"
#     bl_space_type='VIEW_3D'
#     bl_context_mode='OBJECT'
#     bl_label = "My tool"
#     bl_icon = "ops.transform.vertex_random"
#     operator="object.quick_vertex_snap"

blender_classes = [
    QuickVertexSnapOperator,
    QuickVertexSnapPreference
    
]


def register():
    for blender_class in blender_classes:
        bpy.utils.register_class(blender_class)
    # bpy.utils.register_tool(MYADDONNAME_TOOL_mytool,separator=True)
    window_manager = bpy.context.window_manager
    key_config = window_manager.keyconfigs.addon
    if key_config:
        export_category = key_config.keymaps.new('3D View', space_type='VIEW_3D', region_type='WINDOW', modal=False)
        export_key = export_category.keymap_items.new("object.quick_vertex_snap", type='V', value='PRESS',shift=True,ctrl=True)
        addon_keymaps.append((export_category, export_key))





def unregister():
    for (cat, key) in addon_keymaps:
        cat.keymap_items.remove(key)
    addon_keymaps.clear()
    for blender_class in blender_classes:
        bpy.utils.unregister_class(blender_class)
