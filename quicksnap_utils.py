import bpy,mathutils,logging
from mathutils import Vector
from enum import Enum

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name__)

class State(Enum):
    IDLE = 1
    SOURCE_PICKED = 2
    DESTINATION_PICKED = 3

def transform_worldspace_viewspace(world_space_coord,perspective_matrix):
    return perspective_matrix @ Vector((world_space_coord[0],world_space_coord[1],world_space_coord[2],1.0))
def transform_viewspace_coord2d(view_space_coord,width_half,height_half):
    return Vector((width_half + width_half * (view_space_coord.x / view_space_coord.w),
            height_half + height_half * (view_space_coord.y / view_space_coord.w),
            ))
def transform_worldspace_coord2d(world_space_coord,region,region3d):
    return transform_viewspace_coord2d(transform_worldspace_viewspace(world_space_coord,region3d.perspective_matrix),region.width / 2.0,region.height / 2.0)


def get_selection_meshes():            
    return [obj for obj in  bpy.context.selected_objects if obj.visible_get() and (obj.type == 'MESH' or obj.type == 'CURVE')]
    
def get_scene_meshes(exclude_selection=False):
    if exclude_selection:
        objects=[obj.name for obj in bpy.data.objects if obj not in bpy.context.selected_objects and obj.visible_get() and (obj.type == 'MESH' or obj.type == 'CURVE')]
    else:
        objects=[obj.name for obj in bpy.data.objects if  obj.visible_get() and (obj.type == 'MESH' or obj.type == 'CURVE')]
    return objects

def include_children(objects,recursive_call=False):
    result=[]
    if type(objects) is list or type(objects) is set:
        if not recursive_call:
            objects=keep_only_parents(objects)
        for object in objects:
            result.extend(include_children(object,recursive_call=True))
    else:
        object=objects
        result.append(object)
        for child in object.children:
            result.extend(include_children(child,recursive_call=True))
    return result

def keep_only_parents(objects):
    objects=set(objects)
    return set([obj for obj in objects if not has_parent(obj,objects)])

def has_parent(object,parent_list):
    parent=object.parent
    if parent==None:
        return False
    if parent in parent_list:
        return True
    return has_parent(parent,parent_list)

def set_object_mode_if_needed():
    # logger.info("entering object mode if needed")
    mode= f'{bpy.context.active_object.mode}'
    if mode=='EDIT':
        # logger.info('Going to Object Mode')
        bpy.ops.object.mode_set(mode='OBJECT')
    return mode
def revert_mode(previous_mode):
    if bpy.context.active_object.mode!= previous_mode:
        bpy.ops.object.mode_set(mode=previous_mode)
        
def translate_object_worldspace(object,translation):
    object.matrix_world= translation@object.matrix_world

def translate_vertice_worldspace(object,bmesh,vertexids,translation):
    world_matrix=object.matrix_world
    world_matrix_inverted=world_matrix.copy().inverted()
    for index in vertexids:
        bmesh.verts[index].co=world_matrix_inverted@translation@world_matrix@bmesh.verts[index].co.copy()
    bmesh.to_mesh(object.data)


def dump(object):
    logger.info(f"\n\n=============== Dump({object}) ===============")
    for attr in dir(object):
        if hasattr(object,attr):
            logger.info(f'{attr} : {getattr(object,attr)}')
    logger.info(f"=============== END Dump({object}) ===============\n\n")

def get_addon_settings():
    addon = bpy.context.preferences.addons.get(__name_addon__)
    if addon:
        return addon.preferences
    return None


def get_axis_target(origin, target, snapping, object=None):
    if len(snapping)==0:
        return target
    if object==None:
        world_matrix=mathutils.Matrix.Identity(4)
    else:
        world_matrix=object.matrix_world.to_quaternion()
        
    # logger.info("Object is none")
    if len(snapping)==1: #single axis snapping
        if snapping=='X':
            point2=origin+world_matrix@Vector((1,0,0))
        elif snapping=='Y':
            point2=origin+world_matrix@Vector((0,1,0))
        else:
            point2=origin+world_matrix@Vector((0,0,1))
        return mathutils.geometry.intersect_point_line(target, origin, point2)[0]
    
    if len(snapping)==2: #single axis snapping
        if snapping=='XY':
            point2=origin+world_matrix@Vector((1,0,0))
            point3=origin+world_matrix@Vector((0,1,0))
        elif snapping=='YZ':
            point2=origin+world_matrix@Vector((0,1,0))
            point3=origin+world_matrix@Vector((0,0,1))
        else:
            point2=origin+world_matrix@Vector((1,0,0))
            point3=origin+world_matrix@Vector((0,0,1))
        
        normal=mathutils.geometry.normal(origin,point2,point3)
        if(not normal.dot(origin-target)>0): #flip normal if it is pointing the wrong direction
            normal=-1*normal
        newtarget= mathutils.geometry.intersect_ray_tri(origin,point2,point3,normal,target, False)
        return target


def get_target_nosnap(origin, camera_position, camera_vector, snapping, object=None):
    camera_point_b=camera_position+camera_vector
    if len(snapping)==0:       
        point_b = camera_position+camera_vector
        return mathutils.geometry.intersect_line_plane(camera_position,camera_point_b,origin,camera_vector*-1)
    if object==None:
        world_matrix=mathutils.Matrix.Identity(4)
    else:
        world_matrix=object.matrix_world.to_quaternion()
        
    if len(snapping)==1: #single axis snapping
        logger.info("snapping 1")
        if snapping=='X':
            point2=origin+world_matrix@Vector((1,0,0))
        elif snapping=='Y':
            point2=origin+world_matrix@Vector((0,1,0))
        else:
            point2=origin+world_matrix@Vector((0,0,1))
        return mathutils.geometry.intersect_line_line(camera_position,camera_point_b, origin, point2)[1]
    
    if len(snapping)==2: #single axis snapping
        if snapping=='XY':
            point2=origin+world_matrix@Vector((1000,0,0))
            point3=origin+world_matrix@Vector((0,1000,0))
        elif snapping=='YZ':
            point2=origin+world_matrix@Vector((0,1000,0))
            point3=origin+world_matrix@Vector((0,0,1000))
        else:
            point2=origin+world_matrix@Vector((1000,0,0))
            point3=origin+world_matrix@Vector((0,0,1000))
    
        normal=mathutils.geometry.normal(origin,point2,point3)
        newtarget= mathutils.geometry.intersect_line_plane(camera_position,camera_point_b,origin,normal, False)
        return newtarget

def display_keymap(kmi,layout):
    layout.emboss='NORMAL'
    if kmi is None:
        return
    map_type = kmi.map_type

    row=layout.row()
    row.prop(kmi, "active", text="", emboss=False)
    row.alignment='EXPAND'
    label_container=row.row().row()
    label_container.alignment='LEFT'
    label_container.emboss='NONE'
    label_container.enabled=False
    label_container.operator(kmi.idname,text=kmi.name)

    split = row.split()
    row = split.row()
    row.alignment='RIGHT'
    insert_prop_with_width(kmi, "map_type",row,text="",size=5)
    if map_type == 'KEYBOARD':
        insert_prop_with_width(kmi, "type",row,text="",size=8, full_event=True)
    elif map_type == 'MOUSE':
        insert_prop_with_width(kmi, "type",row,text="",size=8, full_event=True)
    elif map_type == 'NDOF':
        insert_prop_with_width(kmi, "type",row,text="",size=8, full_event=True)
    elif map_type == 'TWEAK':
        subrow = row.row()
        insert_prop_with_width(kmi, "type",subrow,text="",size=4)
        insert_prop_with_width(kmi, "value",subrow,text="",size=4)
    elif map_type == 'TIMER':
        insert_prop_with_width(kmi, "type",row,text="",size=8)
    else:
        insert_prop_with_width(kmi, "type",row,text="",size=8)

def insert_prop_with_width(propertyContainer,propertyname,layout,align='CENTER',text=None,icon='NONE',expand=False,slider=False,icon_only=False,toggle=False,size=5,enabled=True, full_event=False):
    propcontainer=layout.row()
    propcontainer.alignment=align
    propcontainer.ui_units_x=size
    if not enabled:
        propcontainer.enabled=False
    propcontainer.prop(propertyContainer,propertyname,icon=icon,toggle=toggle,text=text,expand=expand,slider=slider,icon_only=icon_only,full_event=full_event)

def insert_ui_hotkey(container,key,description,control=False,shift=False):
    line=container.row(align=True)
    container_description = line.split(factor=0.39)
    row = container_description.row(align=True)
    row.alignment='RIGHT'
    if control:
        row.label(text="",icon="EVENT_CTRL")
    if shift:
        row.label(text="",icon="EVENT_SHIFT")
    row.label(text="",icon=key)
    container_description.label(text=description)

def flatten(l):
    return [item for sublist in l for item in sublist]


def translate_curvepoints_worldspace(obj, backup_data, translation):
    curvedata=obj.data
    for (curveindex,index,co,bezier,left,right) in backup_data:
        if bezier:
            curvedata.splines[curveindex].bezier_points[index].co=translation@co.copy()
            curvedata.splines[curveindex].bezier_points[index].handle_left=translation@left.copy()
            curvedata.splines[curveindex].bezier_points[index].handle_right=translation@right.copy()
        else:
            original_point=Vector((co[0],co[1],co[2]))
            target_position=translation@original_point
            curvedata.splines[curveindex].points[index].co=(target_position[0],target_position[1],target_position[2],0)
    pass