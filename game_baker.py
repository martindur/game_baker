# Copyright (C) Martin Durhuus
# martindurhuus@gmail.com

# License: http://www.gnu.org/licenses/gpl.html GPL version 3 or higher

# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####
bl_info = {
    "name": "Game Baker 1.02",
    "author": "Martin Durhuus",
    "version": (1, 0, 0),
    "blender": (2, 78, 0),
    "location": "3d view",
    "description": "Streamlined and optimized baking with Cycles.",
    "category": "Render",
}

import bpy
import os
import colorsys
import random
from bpy.props import (
        StringProperty,
        BoolProperty,
        FloatProperty,
        IntProperty,
        EnumProperty,
        CollectionProperty,
        )

BAKE = False
BAKEIMG = None
LASTIMG = None
BAKELIST = []
BAKING = False

AO_QUALITY_SAMPLES = {
    'LOW': 32,
    'MID': 128,
    'HIGH': 512,
    'VHIGH': 1024
}

DIF_QUALITY_SAMPLES = {
    'LOW': 32,
    'MID': 128,
    'HIGH': 512,
    'VHIGH': 1024
}

POSSIBLE_GRAYSCALE_MAPS = [
    'AO',
    'CURVE',
    'ID',
    'POS'
]


##############################
########### Oven #############
##############################
def set_temperature(context, samples, integrator):
    """Sets the appropriate sampling, depending on quality/time desired by user."""
    cycles = context.scene.cycles
    cycles.progressive = integrator
    cycles.use_square_samples = False
    context.scene.render.bake.use_clear = True

    if cycles.device == 'GPU':
        context.scene.render.tile_y = 256
        context.scene.render.tile_x = 256
    else:
        context.scene.render.tile_y = 64
        context.scene.render.tile_x = 64

    if integrator == 'PATH':
        cycles.samples = samples
    elif integrator == 'BRANCHED_PATH':
        cycles.aa_samples = 1
        cycles.ao_samples = samples
        cycles.diffuse_samples = 1
        cycles.glossy_samples = 1
        cycles.transmission_samples = 1
        cycles.mesh_light_samples = 1
        cycles.subsurface_samples = 1
        cycles.volume_samples = 1

def enable_color_bake_settings():
    scn = bpy.context.scene
    bake_settings = bpy.data.scenes[scn.name].render.bake
    bake_settings.use_pass_color = True
    bake_settings.use_pass_direct = False
    bake_settings.use_pass_indirect = False

def enable_normal_bake_settings(engine):
    scn = bpy.context.scene
    bake_settings = bpy.data.scenes[scn.name].render.bake

    if engine == 'UNITY':
        bake_settings.normal_r = 'POS_X'
        bake_settings.normal_g = 'POS_Y'
        bake_settings.normal_b = 'POS_Z'
    elif engine == 'UNREAL':
        bake_settings.normal_r = 'POS_X'
        bake_settings.normal_g = 'NEG_Y'
        bake_settings.normal_b = 'POS_Z'

def bake(context, recipe, bake_image):
    if recipe == 'NORMAL':
        bake_normal(context, bake_image)
    elif recipe == 'DIFFUSE':
        bake_diffuse(context, bake_image)
    elif recipe == 'AO':
        bake_ao(context, bake_image)
    elif recipe == 'CURVE':
        bake_curvature(context, bake_image)
    elif recipe == 'POS':
        bake_position(context, bake_image)
    elif recipe == 'ID':
        bake_id(context, bake_image)
    return bake_image

def register_bake_settings():
    """Registers bake settings"""
    scn = bpy.types.Scene
    scn.bake_map = EnumProperty(
        items=[('AO', 'Ambient Occlusion', ''),
                ('NORMAL', 'Normal', ''),
                ('DIFFUSE', 'Diffuse', ''),
                ('CURVE', 'Curvature', ''),
                ('POS', 'Position', ''),
                ('ID', 'ID', '')],
        name="Bake Type")
    scn.engine_type = EnumProperty(
        items=[('UNITY', 'Unity (+Y)', ''),
                ('UNREAL', 'Unreal (-Y)', '')],
        name="Engine")
    scn.ao_quality = EnumProperty(
        items=[('LOW', 'Low', ''),
                ('MID', 'Mid', ''),
                ('HIGH', 'High', ''),
                ('VHIGH', 'Very High', '')],
        name="Quality")
    scn.dif_quality = EnumProperty(
        items=[('LOW', 'Low', ''),
                ('MID', 'Mid', ''),
                ('HIGH', 'High', ''),
                ('VHIGH', 'Very High', '')],
        name="Quality")
    scn.bake_id_type = EnumProperty(
        items=[('MAT', 'Material', ''),
               ('VCOL', 'Vertex Colors', '')],
        name="Based on")
    scn.bake_id_color = BoolProperty(
        default=True,
        name="RGB"
    )
    scn.bake_pos_x = BoolProperty(
        default=False,
        name='X'
    )
    scn.bake_pos_y = BoolProperty(
        default=False,
        name='Y'
    )
    scn.bake_pos_z = BoolProperty(
        default=False,
        name='Z'
    )
    scn.cage_distance = FloatProperty(
        name="Distance",
        default=2,
    )
    scn.overwrite_bakes = BoolProperty(
        name="Overwrite Bakes",
        default=False,
        description="Overwrite the existing image with the new bake."
    )
    scn.export_dir = StringProperty(
        default="",
        subtype='FILE_PATH'
    )

def unregister_bake_settings():
    scn = bpy.types.Scene
    del scn.bake_map
    del scn.engine_type
    del scn.ao_quality
    del scn.dif_quality
    del scn.cage_distance
    del scn.overwrite_bakes
    del scn.export_dir
    del scn.bake_id_type
    del scn.bake_id_color
    del scn.bake_pos_x
    del scn.bake_pos_y
    del scn.bake_pos_z


##############################
######## Ingredients #########
##############################
def get_img(name, width, height, floatbuffer, img_id=False, replace_id=None):
    """Returns an image type, optionally with an ID"""
    img = bpy.data.images.new(name, width, height, float_buffer=floatbuffer)
    img.use_fake_user = True
    if img_id:
        img['bake_id'] = name
    elif replace_id is not None:
        img['bake_id'] = replace_id
    return img

def replace_img(img, width, height, bake_id):
    """Replaces given image with a new one given the parameters"""
    scn = bpy.context.scene
    name = img.name
    if width == img.size[0] and height == img.size[1]:
        return img
    else:
        bpy.data.images.remove(img, do_unlink=True)
        return get_img(name, width, height, floatbuffer=True, replace_id=bake_id)

def get_mat(name):
    """Returns a material with appropriate naming and enables nodes"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat

#def set_image_quality()

def register_ingredients():
    """Registers settings for ingredients"""
    scn = bpy.types.Scene
    scn.bake_width = IntProperty(
        name="W",
        default=512,
        min=1,
        subtype='PIXEL'
    )
    scn.bake_height = IntProperty(
        name="H",
        default=512,
        min=1,
        subtype='PIXEL'
    )
    scn.image_format = EnumProperty(
        items=[('PNG', 'PNG', ''),
               ('TARGA', 'TGA', ''),
               ('TARGA_RAW', 'TGA(RAW)', ''),
               ('BMP', 'BMP', ''),
               ('TIFF', 'TIFF', ''),
               ('JPEG', 'JPG', ''),
               ('DPX', 'DPX', ''),
               ('OPEN_EXR', 'OpenEXR', '')],
        name='Format'
    )
    scn.high_poly = StringProperty(
        name="HP",
        default=''
    )
    scn.low_poly = StringProperty(
        name="LP",
        default=''
    )

def unregister_ingredients():
    """Unregisters image creation settings"""
    scn = bpy.types.Scene
    del scn.bake_width
    del scn.bake_height
    del scn.image_format
    del scn.high_poly
    del scn.low_poly


##############################
########## Recipes ###########
##############################
def bake_ao(context, img):
    samples = AO_QUALITY_SAMPLES[context.scene.ao_quality]
    set_temperature(context, samples, 'BRANCHED_PATH')
    if len(BAKELIST) > 1:
        bpy.ops.object.bake(type='AO')
    else:
        LASTIMG = 'AO'
        bpy.ops.object.bake('INVOKE_DEFAULT', type='AO')
        BAKEIMG = img

def bake_diffuse(context, img):
    samples = DIF_QUALITY_SAMPLES[context.scene.dif_quality] #Will be used for direct/indirect lighting
    cbk = context.scene.render.bake
    set_temperature(context, 1, 'PATH')
    if len(BAKELIST) > 1:
        bpy.ops.object.bake(type='DIFFUSE')
    else:
        LASTIMG = 'DIFFUSE'
        bpy.ops.object.bake('INVOKE_DEFAULT', type='DIFFUSE')
        BAKEIMG = img

def bake_normal(context, img):
    context.scene.cycles.bake_type = 'NORMAL'
    engine_type = context.scene.engine_type
    enable_normal_bake_settings(engine_type)
    set_temperature(context, 1, 'PATH')
    if len(BAKELIST) > 1:
        bpy.ops.object.bake(type='NORMAL')
    else:
        LASTIMG = 'NORMAL'
        bpy.ops.object.bake('INVOKE_DEFAULT', type='NORMAL')
        BAKEIMG = img

def apply_bake_material(ob, bake_mat=None, bake_mat_list=None):
    """Replaces materials and returns a list with the original"""
    original_mats = []
    if len(ob.material_slots) is 0:
        ob.active_material = bpy.data.materials.new('_'.join([ob.name, "HP_MAT"]))
    for idx, mat in enumerate(ob.material_slots):
        original_mats.append(mat.material)
        if bake_mat_list is None:
            mat.material = bake_mat
        else:
            mat.material = bake_mat_list[idx]
    return original_mats

def remove_bake_material(ob, original_mats):
    """Removes bake material and applies the given list of materials"""
    for idx, mat in enumerate(ob.material_slots):
        mat.material = original_mats[idx]

def bake_curvature(context, img):
    """Method for baking curvature map"""
    set_temperature(context, 1, 'PATH')
    enable_color_bake_settings()
    high_to_low = context.scene.render.bake.use_selected_to_active
    if high_to_low:
        ob = bpy.data.objects[context.scene.high_poly]
    else:
        ob = bpy.data.objects[context.scene.low_poly]

    #MATERIAL CONSTRUCTION#
    curve_mat = bpy.data.materials.new("tmp_curve_mat")
    curve_mat.use_nodes = True
    nodes = curve_mat.node_tree.nodes
    links = curve_mat.node_tree.links
    out_node = nodes[1]
    geo_node = nodes.new("ShaderNodeNewGeometry")
    img_node = nodes.new("ShaderNodeTexImage")
    img_node.color_space = 'NONE'
    links.new(geo_node.outputs[7], out_node.inputs[0])
    img_node.image = img
    nodes.active = img_node
    
    #APPLICATION; BAKE; REMOVAL#
    original_mats = apply_bake_material(ob, curve_mat)
    bpy.ops.object.bake(type='DIFFUSE')
    remove_bake_material(ob, original_mats)

    #MATERIAL DESTRUCTION#
    bpy.data.materials.remove(curve_mat, do_unlink=True)

def bake_position(context, img):
    """Method for baking position map"""
    set_temperature(context, 1, 'PATH')
    enable_color_bake_settings()
    high_to_low = context.scene.render.bake.use_selected_to_active
    x_axis = context.scene.bake_pos_x
    y_axis = context.scene.bake_pos_y
    z_axis = context.scene.bake_pos_z
    if high_to_low:
        ob = bpy.data.objects[context.scene.high_poly]
    else:
        ob = bpy.data.objects[context.scene.low_poly]
    
    #MATERIAL CONSTRUCTION#
    pos_mat = bpy.data.materials.new("tmp_pos_mat")
    pos_mat.use_nodes = True
    nodes = pos_mat.node_tree.nodes
    links = pos_mat.node_tree.links
    out_node = nodes[1]
    tex_coord_node = nodes.new("ShaderNodeTexCoord")
    #R(Left-to-right) node
    if x_axis:
        mapping_node_R = nodes.new("ShaderNodeMapping")
        min_vertex_position = abs(min_vertex(ob.data, 'x'))
        true_scale = 1/ob.dimensions.x
        mapping_node_R.scale[0] = true_scale
        mapping_node_R.translation[0] = min_vertex_position * true_scale
        gradient_node_R = nodes.new("ShaderNodeTexGradient")
        links.new(tex_coord_node.outputs[3], mapping_node_R.inputs[0])
        links.new(mapping_node_R.outputs[0], gradient_node_R.inputs[0])
    #G(Bottom-to-top) node
    if y_axis:
        mapping_node_G = nodes.new("ShaderNodeMapping")
        mapping_node_G.rotation[1] = 1.5708 #Radian rotation of 90 degrees in Y
        min_vertex_position = abs(min_vertex(ob.data, 'z'))
        true_scale = 1/ob.dimensions.z
        mapping_node_G.scale[2] = true_scale
        mapping_node_G.translation[0] = min_vertex_position * true_scale
        gradient_node_G = nodes.new("ShaderNodeTexGradient")
        links.new(tex_coord_node.outputs[3], mapping_node_G.inputs[0])
        links.new(mapping_node_G.outputs[0], gradient_node_G.inputs[0])
    #B(Back-to-front) node
    if z_axis:
        mapping_node_B = nodes.new("ShaderNodeMapping")
        mapping_node_B.rotation[2] = 1.5708 #Radian rotation of 90 degrees in Y
        min_vertex_position = abs(min_vertex(ob.data, 'y'))
        true_scale = 1/ob.dimensions.y
        mapping_node_B.scale[1] = true_scale
        mapping_node_B.translation[0] = min_vertex_position * true_scale
        gradient_node_B = nodes.new("ShaderNodeTexGradient")
        links.new(tex_coord_node.outputs[3], mapping_node_B.inputs[0])
        links.new(mapping_node_B.outputs[0], gradient_node_B.inputs[0])

    
    combine_RGB = nodes.new("ShaderNodeCombineRGB")
    img_node = nodes.new("ShaderNodeTexImage")
    img_node.image = img
    

    #LINKING#
    if x_axis and not y_axis and not z_axis:
        img_node.color_space = 'NONE'
        links.new(gradient_node_R.outputs[0], combine_RGB.inputs[0])
        links.new(gradient_node_R.outputs[0], combine_RGB.inputs[1])
        links.new(gradient_node_R.outputs[0], combine_RGB.inputs[2])
    elif y_axis and not x_axis and not z_axis:
        img_node.color_space = 'NONE'
        links.new(gradient_node_G.outputs[0], combine_RGB.inputs[0])
        links.new(gradient_node_G.outputs[0], combine_RGB.inputs[1])
        links.new(gradient_node_G.outputs[0], combine_RGB.inputs[2])
    elif z_axis and not x_axis and not y_axis:
        img_node.color_space = 'NONE'
        links.new(gradient_node_B.outputs[0], combine_RGB.inputs[0])
        links.new(gradient_node_B.outputs[0], combine_RGB.inputs[1])
        links.new(gradient_node_B.outputs[0], combine_RGB.inputs[2])
    else:
        if x_axis:
            links.new(gradient_node_R.outputs[0], combine_RGB.inputs[0])
        if y_axis:
            links.new(gradient_node_G.outputs[0], combine_RGB.inputs[1])
        if z_axis:
            links.new(gradient_node_B.outputs[0], combine_RGB.inputs[2])
    
    

    links.new(combine_RGB.outputs[0], out_node.inputs[0])

    
    nodes.active = img_node
    #APPLICATION; BAKE; REMOVAL#
    original_mats = apply_bake_material(ob, pos_mat)
    bpy.ops.object.bake(type='DIFFUSE')
    remove_bake_material(ob, original_mats)

    #MATERIAL DESTRUCTION#
    #bpy.data.materials.remove(pos_mat, do_unlink=True)

def bake_id(context, img):
    """Method for baking ID map"""
    set_temperature(context, 1, 'PATH')
    enable_color_bake_settings()
    scn = context.scene
    id_type = scn.bake_id_type
    use_rgb = scn.bake_id_color
    high_to_low = scn.render.bake.use_selected_to_active
    if high_to_low:
        ob = bpy.data.objects[scn.high_poly]
    else:
        ob = bpy.data.objects[scn.low_poly]

    if id_type == 'MAT':
        if len(ob.material_slots) is 0:
            print("No materials to create IDs")
            return None
        id_mats = []
        for slot in ob.material_slots:
            if slot.material is not None:
                id_mat = bpy.data.materials.new('id')
                id_mat.use_nodes = True
                map_node = id_mat.node_tree.nodes.new("ShaderNodeTexImage")
                map_node.image = img
                if use_rgb:
                    col = colorsys.hsv_to_rgb(random.random(), 1.0, 1.0)
                else:
                    map_node.color_space = 'NONE'
                    col = colorsys.hsv_to_rgb(0.0, 0.0, random.random())
                col_node = id_mat.node_tree.nodes['Diffuse BSDF']
                col_node.inputs[0].default_value = (col[0], col[1], col[2], 1)
                id_mat.node_tree.nodes.active = map_node
                id_mats.append(id_mat)

        original_mats = apply_bake_material(ob, bake_mat_list=id_mats)
        bpy.ops.object.bake(type='DIFFUSE')
        remove_bake_material(ob, original_mats)
        for mat in id_mats:
            bpy.data.materials.remove(mat, do_unlink=True)
    elif id_type == 'VCOL':
        vcol_mat = bpy.data.materials.new('vcol')
        vcol_mat.use_nodes = True
        nodes = vcol_mat.node_tree.nodes
        links = vcol_mat.node_tree.links
        vcol_node = nodes.new("ShaderNodeAttribute")
        vcol_node.attribute_name = ob.data.vertex_colors[0].name
        out_node = nodes['Diffuse BSDF']
        rgb2bw_node = nodes.new("ShaderNodeRGBToBW")
        if use_rgb:
            links.new(vcol_node.outputs[0], out_node.inputs[0])
        else:
            links.new(vcol_node.outputs[0], rgb2bw_node.inputs[0])
            links.new(rgb2bw_node.outputs[0], out_node.inputs[0])
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = img
        nodes.active = image_node
        
        original_mats = apply_bake_material(ob, vcol_mat)
        bpy.ops.object.bake(type='DIFFUSE')
        remove_bake_material(ob, original_mats)
    else:
        return {'CANCELLED'}
    return {'FINISHED'}

def register_recipes():
    scn = bpy.types.Scene
    scn.gamebake_normal = BoolProperty(
        name="Normals",
        default = False,
        description="Enable baking for Normal map"
    )
    scn.gamebake_ao = BoolProperty(
        name="Ambient Occlusion",
        default = False,
        description="Enable baking for Ambient Occlusion map"
    )
    scn.gamebake_diffuse = BoolProperty(
        name="Albedo", #Will change to diffuse when lighting is possible
        default = False,
        description="Enable baking for albedo map"
    )
    scn.gamebake_curvature = BoolProperty(
        name="Curvature",
        default = False,
        description="Enable baking for Curvature map"
    )
    scn.gamebake_position = BoolProperty(
        name="Position",
        default=False,
        description="Enable baking for Position map"
    )
    scn.gamebake_id = BoolProperty(
        name="ID",
        default=False,
        description="Enable baking for ID map"
    )

def unregister_recipes():
    scn = bpy.types.Scene
    del scn.gamebake_diffuse
    del scn.gamebake_ao
    del scn.gamebake_curvature
    del scn.gamebake_normal
    del scn.gamebake_position
    del scn.gamebake_id

###Recipe helper functions####
def min_vertex(mesh, axis):
    """Finds the minimum positioned vertex in mesh given axis"""
    for i, vt in enumerate(mesh.vertices):
        v = eval('.'.join(['vt.co', axis]))
        if i == 0:
            min = v
        if v < min:
            min = v
    return min

##############################
######### Interface ##########
##############################
def draw_bake_menu(context, layout):
    scn = context.scene
    
    
    row = layout.row()
    draw_bake_button(context, row)
    
    row = layout.row()
    col = row.column()
    box = col.box()
    draw_overwrite_bakes(context, box)
    draw_export_settings(context, box)

    col = row.column()
    box = col.box()
    draw_image_settings(context, box)

    draw_mesh_info_panel(context, layout)
    draw_bake_types(context, layout)
    draw_bake_queue(layout)

def draw_overwrite_bakes(context, pos):
    scn = context.scene
    pos.prop(scn, 'overwrite_bakes', icon='GHOST')

def draw_bake_button(context, pos):
    scn = context.scene
    if scn.low_poly is '':
        pos.operator("gb.bake", icon='ERROR', text="Add mesh in 'MESH INFO' tab")
    elif scn.low_poly is not '':
        try:
            ob = bpy.data.objects[scn.low_poly]
            pos.operator("gb.bake", icon='TEXTURE_SHADED')
        except:
            pos.operator("gb.bake", icon='ERROR', text=' '.join([scn.low_poly, "Does not exist"]))
    elif bpy.context.active_object is not None:
        if not bpy.context.active_object.mode == 'OBJECT':
            pos.operator("gb.bake", icon='ERROR', text="You must be in object mode to bake")
        else:
            pos.operator("gb.bake", icon='TEXTURE_SHADED')
    else:
            pos.operator("gb.bake", icon='TEXTURE_SHADED')

def draw_image_settings(context, pos):
    scn = context.scene
    cbk = scn.render.bake
    pos.prop(cbk, "margin")
    pos.prop(scn, 'bake_width')
    pos.prop(scn, 'bake_height')

def draw_export_settings(context, pos):
    scn = context.scene
    if scn.export_dir is '':
        pos.operator('gb.pack_bakes', icon='PACKAGE')
    elif '//' in scn.export_dir:
        pos.operator('gb.export_bakes', text="Use absolute path", icon='ERROR')
        row = pos.row()
        row.prop(scn, 'image_format')
    else:
        pos.operator('gb.export_bakes', icon='DISK_DRIVE')
        row = pos.row()
        row.prop(scn, 'image_format')
    pos.prop(scn, 'export_dir', text="Export")


def draw_mesh_info_panel(context, pos):
    row = pos.row()
    scn = context.scene
    cbk = scn.render.bake
    use_cage = cbk.use_cage
    use_sel_to_act = cbk.use_selected_to_active
    mesh_info_panel = scn.mesh_info_panel

    row.prop(scn, 'mesh_info_panel', icon='OBJECT_DATAMODE', text='-----       MESH INFO      -----')
    if mesh_info_panel:
        row = pos.row()
        box = row.box()
        row = box.row()
        col = row.column()
        col.prop(cbk, 'use_selected_to_active', text="High to Low")
        col = row.column()
        col.prop(cbk, 'use_cage')
        if use_sel_to_act:
            row = box.row()
            col = row.column()
            col.prop_search(scn, 'high_poly', scn, 'objects')
            col = row.column()
            col.operator('gb.pick_hp')
        row = box.row()
        col = row.column()
        col.prop_search(scn, 'low_poly', scn, 'objects')
        col = row.column()
        col.operator('gb.pick_lp')
        if use_cage:
            row = box.row()
            col = row.column()
            col.prop_search(cbk, 'cage_object', scn, 'objects', text="Cage")
            col = row.column()
            col.operator('gb.pick_cage')
        row = box.row()
        col = row.column()
        col.operator("gb.generate_cage", icon='BBOX')
        col = row.column()
        col.prop(scn, 'cage_distance')

def draw_bake_types(context, pos):
    scn = context.scene
    cbk = scn.render.bake
    row = pos.row()
    row.prop(scn, 'gamebake_types', icon='POTATO', text='-----       BAKE TYPES      -----')
    if scn.gamebake_types:
        row = pos.row()
        box = row.box()
        box.prop(scn, 'gamebake_diffuse', icon='DOT')
        #if scn.gamebake_diffuse:
            #row = box.row(align=True)
            #row.prop(cbk, 'use_pass_color', toggle=True)
            #row.prop(cbk, 'use_pass_direct', toggle=True)
            #row.prop(cbk, 'use_pass_indirect', toggle=True)
        box.prop(scn, 'gamebake_ao', icon='DOT')
        if scn.gamebake_ao:
            box.prop(scn, 'ao_quality')
        box.prop(scn, 'gamebake_normal', icon='DOT')
        if scn.gamebake_normal:
            box.prop(cbk, 'normal_space')
            row = box.row()
            row.prop(scn, 'engine_type')
        box.prop(scn, 'gamebake_curvature', icon='DOT')
        box.prop(scn, 'gamebake_position', icon='DOT')
        if scn.gamebake_position:
            row = box.row(align=True)
            row.prop(scn, 'bake_pos_x', toggle=True)
            row.prop(scn, 'bake_pos_y', toggle=True)
            row.prop(scn, 'bake_pos_z', toggle=True)
        box.prop(scn, 'gamebake_id', icon='DOT')
        if scn.gamebake_id:
            row = box.row()
            col = row.column()
            col.prop(scn, 'bake_id_type')
            col = row.column()
            col.prop(scn, 'bake_id_color')

def draw_bake_queue(pos):
    global BAKEIMG
    global BAKELIST
    global LASTIMG
    if BAKEIMG is not None:
        if BAKEIMG.is_dirty:
            LASTIMG = None
    
    if BAKING or LASTIMG is not None:
        row = pos.row()
        row.label("Bake Queue:")
        row = pos.row()
        box = row.box()
        if BAKING:
            for i in range(len(BAKELIST)):
                row = box.row()
                if BAKELIST[i] == 'NORMAL':
                    ico = 'MATCAP_23'
                elif BAKELIST[i] == 'CURVE':
                    ico = 'MATCAP_10'
                elif BAKELIST[i] == 'DIFFUSE':
                    ico = 'MATCAP_02'
                elif BAKELIST[i] == 'AO':
                    ico = 'MATCAP_09'
                elif BAKELIST[i] == 'POS':
                    ico = 'MATCAP_08'
                elif BAKELIST[i] == 'ID':
                    ico = 'MATCAP_21'
                row.label(BAKELIST[i], icon=ico)
        elif LASTIMG is not None:
            row = box.row()
            if LASTIMG == 'NORMAL':
                ico = 'MATCAP_23'
            elif LASTIMG == 'DIFFUSE':
                ico = 'MATCAP_02'
            elif LASTIMG == 'AO':
                ico = 'MATCAP_09'
            row.label(LASTIMG, icon=ico)
        row = pos.row()
        row.label("Baking in progress...")

def register_interface():
    scn = bpy.types.Scene
    scn.gamebake_types = BoolProperty(
        name="Bake Types",
        default = True,
        description="Enable panel to show bake types"
    )
    scn.mesh_info_panel = BoolProperty(
        name="Mesh Info",
        default=False
    )

def unregister_interface():
    scn = bpy.types.Scene
    del scn.gamebake_types
    del scn.mesh_info_panel


##############################
########## Generic ###########
##############################
def check_pos(nodes, pos, new_node):
    if any(node.location[0] == pos for node in nodes):
        check_pos(nodes, pos-200, new_node)
    else:
        new_node.location.x = pos

def any_one(iterable):
    i = iter(iterable)
    return any(i) and not any(i)

def get_active_lowpoly():
    try:
        return bpy.data.objects[bpy.context.scene.low_poly]
    except:
        print("No low poly mesh assigned!")
        return None

def validate_selection(context):
    lp = context.scene.low_poly
    hp = context.scene.high_poly
    cage = context.scene.render.bake.cage_object
    use_cage = context.scene.render.bake.use_cage
    use_sel_to_act = context.scene.render.bake.use_selected_to_active

    if lp is '':
        return None
    elif lp is not '':
        context.scene.render.bake.use_cage = False
        context.scene.render.bake.use_selected_to_active = False
        bpy.ops.object.select_all(action='DESELECT')
        if hp is not '' and use_sel_to_act:
            context.scene.render.bake.use_selected_to_active = True
            hp = bpy.data.objects[hp]
            hp.select = True
            if cage is not '' and use_cage:
                context.scene.render.bake.use_cage = True
        lp = bpy.data.objects[lp]
        lp.select = True
        context.scene.objects.active = lp
        return {'FINISHED'}
        
class PickHighPoly(bpy.types.Operator):
    """Adds active object to HighPoly mesh selection."""
    bl_idname = "gb.pick_hp"
    bl_label = "Add Active"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        context.scene.high_poly = context.active_object.name
        return {'FINISHED'}

class PickLowPoly(bpy.types.Operator):
    """Adds active object to LowPoly mesh selection."""
    bl_idname = "gb.pick_lp"
    bl_label = "Add Active"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        context.scene.low_poly = context.active_object.name
        return {'FINISHED'}

class PickCage(bpy.types.Operator):
    """Adds active object to Cage mesh selection."""
    bl_idname = "gb.pick_cage"
    bl_label = "Add Active"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        context.scene.render.bake.cage_object = context.active_object.name
        return {'FINISHED'}

class GenerateCage(bpy.types.Operator):
    bl_idname = "gb.generate_cage"
    bl_label = "Generate Cage"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.low_poly is not ''

    def execute(self, context):
        lp = bpy.data.objects[context.scene.low_poly]
        lp.select = True
        context.scene.objects.active = lp
        bpy.ops.object.duplicate()
        cage = context.active_object

        cage.name = ''.join([lp.name, '_CAGE'])
        bpy.ops.object.modifier_add(type='SOLIDIFY')
        solidify = cage.modifiers[-1]
        solidify.use_rim_only = True
        solidify.thickness = -(context.scene.cage_distance/100)
        solidify.thickness_clamp = 2
        mdf_len = len(cage.modifiers)
        for idx, mdf in enumerate(cage.modifiers):
            if idx == mdf_len-1:
                bpy.ops.object.modifier_apply(modifier=mdf.name)
            bpy.ops.object.modifier_remove(modifier=mdf.name)
        context.scene.render.bake.cage_object = cage.name

        for i in range(len(cage.material_slots)):
            bpy.ops.object.material_slot_remove()

        cage_mat = None
        for mat in bpy.data.materials:
            try:
                if mat['cage'] == True:
                    cage_mat = mat
            except:
                pass
        if cage_mat is None:
            cage_mat = bpy.data.materials.new('CAGE_MAT')
            cage_mat.diffuse_color = (1, 0, 0)
            cage_mat['cage'] = True
        cage.active_material = cage_mat
        return {'FINISHED'}


class Bake(bpy.types.Operator):
    bl_idname = "gb.bake"
    bl_label = "Bake"
    bl_options = {'REGISTER'}

    bakelist = []
    bakemap = None
    #baking = False

    def get_map_name(self, ob, map_type):   #Check if ob['name'] is set anywhere?
        try:
            if ob['name']:
                ob_name = ob['name']
        except:
            ob_name = ob.name
        return ''.join([ob_name, '_', map_type])

    def make_image_with_id(self, context, map_name, width, height):
        bake_image = None
        for image in bpy.data.images:
            try:
                if image['bake_id'] == map_name:
                    if context.scene.overwrite_bakes:
                        bake_image = replace_img(image, width, height, map_name)
                    else:
                        image['bake_id'] = None
                        floatbuffer = True
                        if 'NORMAL' in map_name:
                            floatbuffer = False
                        bake_image = get_img(map_name, width, height, floatbuffer=floatbuffer, img_id=True)
            except:
                pass
        if bake_image is None:
            bake_image = get_img(map_name, width, height, floatbuffer=True, img_id=True)
        #bake_image.pack(as_png=True) #Compresses the results. Packing should be done by the user
        return bake_image

    def check_image_grayscale(self, context, map_type):
        if map_type == 'AO' or map_type == 'CURVE':
            return True
        elif map_type == 'POS':
            x_axis = context.scene.bake_pos_x
            y_axis = context.scene.bake_pos_y
            z_axis = context.scene.bake_pos_z
            return any_one([x_axis, y_axis, z_axis])
        elif map_type == 'ID':
            return not context.scene.bake_id_color
        else:
            return False



    def update_existing_mat_image_node(self, ob, map_type, bake_image):
        for mat in ob.material_slots:
            mat = mat.material
            mat.use_nodes = True
            img_exists = False
            coord = 0
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    if node.image == bake_image:
                        img_exists = True
                        map_node = node
                        if self.check_image_grayscale(bpy.context, map_type):
                            map_node.color_space = 'NONE'
                        else:
                            map_node.color_space = 'COLOR'
                    if node.image is None and node.label is not None:
                        mat.node_tree.nodes.remove(node)
            if not img_exists:
                map_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                check_pos(mat.node_tree.nodes, 0.0, map_node)
                if self.check_image_grayscale(bpy.context, map_type):
                    map_node.color_space = 'NONE'
                map_node.label = str(map_type)
                map_node.image = bake_image
            mat.node_tree.nodes.active = map_node

    @classmethod
    def poll(cls, context):
        if context.scene.low_poly is not '':
            ob_name = context.scene.low_poly
            try:
                ob = bpy.data.objects[ob_name]
                if ob.mode == 'OBJECT':
                    return True
                else:
                    return False
            except:
                return False
        else:
            return False

    def modal(self, context, event):
        scn = context.scene
        ob = get_active_lowpoly()
        tex_width = scn.bake_width
        tex_height = scn.bake_height
        global BAKELIST
        global BAKING
        if event.type in {'ESC'}:
            return {'CANCELLED'} 
        if not BAKING:
            return {'CANCELLED'}
        if len(BAKELIST) > 0:
            bake_image_name = self.get_map_name(ob, BAKELIST[-1])
            bake_image = self.make_image_with_id(context, bake_image_name, tex_width, tex_height)
            self.update_existing_mat_image_node(ob, BAKELIST[-1], bake_image)
            self.bakemap = bake(context, BAKELIST[-1], bake_image)
            #self.bakemap = get_map_simple(tex_width, tex_height, BAKELIST[-1])
            BAKELIST.pop()
            BAKEIMG = self.bakemap
            return {'RUNNING_MODAL'}
        else:
            BAKING = False
            return {'FINISHED'}

        
        

    def invoke(self, context, event):
        global LASTIMG
        LASTIMG = None
        scn = context.scene
        high_to_low = scn.render.bake.use_selected_to_active
        scn.render.engine = 'CYCLES'
        validated = validate_selection(context)
        if validated is None:
            self.report({'WARNING'}, "Lowpoly mesh not assigned")
            return {'CANCELLED'}
        Lowpoly = bpy.data.objects[scn.low_poly]
        if len(Lowpoly.data.uv_textures) is 0:
            self.report({'WARNING'}, "Mesh is missing a UV map")
            return {'CANCELLED'}
        if high_to_low:
            if scn.high_poly is not '':
                if not bpy.data.objects[scn.high_poly].is_visible(scn):
                    self.report({'WARNING'}, "High poly mesh not visible!")
                    return {'CANCELLED'}
        if Lowpoly.active_material is None:
            Lowpoly.active_material = get_mat(Lowpoly.name)
        global BAKING
        global BAKELIST
        BAKING = True
        self.baking = True
        bake_jobs = {
            "DIFFUSE":scn.gamebake_diffuse,
            "AO":scn.gamebake_ao,
            "NORMAL":scn.gamebake_normal,
            "CURVE":scn.gamebake_curvature,
            "POS":scn.gamebake_position,
            "ID":scn.gamebake_id
        }
        for job in bake_jobs:
            if bake_jobs[job] is True:
                BAKELIST.append(job)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class PackBakes(bpy.types.Operator):
    """Pack bakes in .blend file as PNG"""
    bl_idname = "gb.pack_bakes"
    bl_label = "Pack Bakes"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bpy.context.scene.export_dir is ''

    def execute(self, context):
        for img in bpy.data.images:
            try:
                if img['bake_id']:
                    img.pack(as_png=True)
            except:
                pass
        return {'FINISHED'}

class ExportBakes(bpy.types.Operator):
    """Export bakes to a given destination as preferred format"""
    bl_idname = "gb.export_bakes"
    bl_label = "Export Bakes"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return '//' not in bpy.context.scene.export_dir

    def execute(self, context):
        scn = context.scene
        filepath = scn.export_dir
        img_format = scn.image_format
        for img in bpy.data.images:
            try:
                img_format = scn.image_format
                if img['bake_id']:
                    #img.pack(as_png=True)
                    img.file_format = img_format
                    if img_format == 'TARGA' or img_format == 'TARGA_RAW':
                        img_format = 'TGA'
                    elif img_format == 'JPEG':
                        img_format = 'JPG'
                    elif img_format == 'OPEN_EXR':
                        img_format = 'EXR'
                    img.filepath_raw = ''.join([filepath, img.name, '.', img_format.lower()])
                    img.save()
                    #img.unpack()
            except:
                self.report({'WARNING'}, "Can't export!")
                pass
        return {'FINISHED'}

class BakeList(bpy.types.UIList):
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon_value=icon)
        elif self.layout_type in {'GRID'}:
            pass



class BakeMenu(bpy.types.Panel):
    bl_label = "Game Baker 1.02"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_category = "Baking"
    COMPAT_ENGINES = {'CYCLES'}
    
    def draw(self, context):
        layout = self.layout
        draw_bake_menu(context, layout)

classes = [
    BakeMenu,
    Bake,
    GenerateCage,
    PickHighPoly,
    PickLowPoly,
    PickCage,
    PackBakes,
    ExportBakes
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    register_bake_settings()
    register_ingredients()
    register_interface()
    register_recipes()

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    unregister_bake_settings()
    unregister_ingredients()
    unregister_interface()
    unregister_recipes()

if __name__ == '__main__':
    register()
