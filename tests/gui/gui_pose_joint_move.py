"""Move a connected skinned joint with the real viewport manipulator in Pose Mode."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, tap, view3d, win  # noqa: E402


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def rig():
    return bpy.data.objects["PoseMoveRig"]


def heads():
    return [pb.head.copy() for pb in rig().pose.bones]


def rest():
    return [bone.matrix_local.copy() for bone in rig().data.bones]


def vertex():
    mesh = bpy.data.objects["PoseMoveSkin"].evaluated_get(bpy.context.evaluated_depsgraph_get())
    return mesh.data.vertices[0].co.copy()


start = {}
mouse = {}


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    joints = import_module(MODULE + ".operators.joints")
    for ob in list(bpy.data.objects):
        if ob.type in {'MESH', 'ARMATURE'}:
            bpy.data.objects.remove(ob)
    with override():
        arm = joints.new_skeleton(bpy.context)
        arm.name = "PoseMoveRig"
        parent = joints.add_joint(arm, (0, -1, 0))
        child = joints.add_joint(arm, (0, 0, 0), parent)
        tip = joints.add_joint(arm, (0, 1, 0), child)
        mesh = bpy.data.meshes.new("PoseMoveSkin")
        mesh.from_pydata([(0.1, 0.1, 0.0)], [], [])
        skin = bpy.data.objects.new(mesh.name, mesh)
        bpy.context.collection.objects.link(skin)
        skin.vertex_groups.new(name=child).add([0], 1.0, 'REPLACE')
        skin.modifiers.new("Skin", 'ARMATURE').object = arm
        joints.finish(bpy.context, arm, [parent, child, tip], top=child)
        arm.pose.bones[parent].rotation_euler.z = 0.25
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
        ts = bpy.context.scene.tool_settings
        ts.transform_pivot_point, ts.use_snap = 'ACTIVE_ELEMENT', False
        bpy.context.scene.transform_orientation_slots[0].type = 'GLOBAL'
        view = bpy.context.region_data
        view.view_rotation = Quaternion()
        view.view_location = (0, 0, 0)
        view.view_perspective = 'ORTHO'
        view.view_distance = 5
        bpy.context.view_layer.update()
        bpy.ops.ed.undo_push(message="Resting skinned chain")
    start.update(heads=heads(), rest=rest(), vertex=vertex())


@step
def s_hover():
    ob = rig()
    check("The middle joint starts connected and selected in Pose Mode",
          ob.mode == 'POSE' and ob.pose.bones[1].select and ob.data.bones[1].use_connect)
    _, region = view3d()
    centre = location_3d_to_region_2d(region, region.data, ob.pose.bones[1].head)
    prefs = bpy.context.preferences
    x = round(region.x + centre.x + 0.6 * prefs.view.gizmo_size * prefs.system.ui_scale)
    y = round(region.y + centre.y)
    mouse.update(x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_press():
    ev('LEFTMOUSE', 'PRESS', **mouse)


@step
def s_drag_start():
    ev('MOUSEMOVE', 'NOTHING', x=mouse["x"] + 12, y=mouse["y"])


@step
def s_drag():
    ev('MOUSEMOVE', 'NOTHING', x=mouse["x"] + 75, y=mouse["y"] + 40)


@step
def s_preview():
    delta = heads()[1] - start["heads"][1]
    check(f"The X handle translates the joint live along X only ({tuple(delta)})",
          delta.x > 0.1 and abs(delta.y) < 1e-5)
    check("The skin follows the moving joint", (vertex() - start["vertex"] - delta).length < 1e-5)
    ev('LEFTMOUSE', 'RELEASE', x=mouse["x"] + 75, y=mouse["y"] + 40)


@step
def s_confirmed():
    after = heads()
    delta = after[1] - start["heads"][1]
    check("The parent stays and the descendant follows in Pose Mode",
          rig().mode == 'POSE' and (after[0] - start["heads"][0]).length < 1e-5
          and (after[2] - start["heads"][2] - delta).length < 1e-5
          and rig().pose.bones[1].parent == rig().pose.bones[0])
    check("The pose move preserves the rest matrices", rest() == start["rest"])
    joints = import_module(MODULE + ".ui.maya_joints")
    chain = list(joints.skeleton(rig(), bpy.context.scene).values())
    segment = joints.bone_lines(chain[0], chain[1])
    expected_apex = after[1] - (after[1] - after[0]).normalized() * chain[1].radius
    check("The parent segment extends to the new joint position",
          len(segment) == 16 and (segment[3] - expected_apex).length < 1e-5)
    start["moved"] = after[1]
    with override():
        bpy.ops.ed.undo()


@step
def s_undone():
    check("One undo restores the pose and the connected joint",
          rig().mode == 'POSE' and rig().data.bones[1].use_connect and heads() == start["heads"])
    with override():
        bpy.ops.ed.redo()


@step
def s_redone():
    check("Redo restores the joint move",
          (heads()[1] - start["moved"]).length < 1e-5 and not rig().data.bones[1].use_connect)
    with override():
        bpy.ops.ed.undo()
    ev('MOUSEMOVE', 'NOTHING', x=mouse["x"] + 170, y=mouse["y"] + 70)


@step
def s_middle_press():
    ev('MIDDLEMOUSE', 'PRESS')


@step
def s_middle_drag():
    ev('MOUSEMOVE', 'NOTHING', x=mouse["x"] + 225, y=mouse["y"] + 80)


@step
def s_cancel():
    check("A middle drag translates the connected joint", (heads()[1] - start["heads"][1]).length > 0.1)
    tap('ESC')
    ev('MIDDLEMOUSE', 'RELEASE')


@step
def s_cancelled():
    check("Escape restores the pose, skin and joint connection",
          heads() == start["heads"] and vertex() == start["vertex"] and rig().data.bones[1].use_connect)
    import_module(MODULE + ".preferences").get().keymap_set = 'BLENDER'


step(s_hover)
step(s_press)
step(s_drag_start)
step(s_drag)


@step
def s_blender_keys():
    check("The Move handle translates the joint with the Blender keymap",
          rig().mode == 'POSE' and (heads()[1] - start["heads"][1]).x > 0.1)
    ev('LEFTMOUSE', 'RELEASE', x=mouse["x"] + 75, y=mouse["y"] + 40)


run()
