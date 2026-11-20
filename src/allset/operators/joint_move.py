# SPDX-License-Identifier: GPL-3.0-or-later
"""Let the Move tool translate a connected joint on a skinned skeleton in Pose mode."""

import bpy

from .. import compat, live_refs, switch
from . import joint_selection


def _movable_joints(context):
    arm = context.active_object
    if (context.mode != 'POSE' or not switch.is_on() or arm is None or not arm.is_editable
            or not arm.data.is_editable or arm.data.users - arm.data.use_fake_user != 1
            or len(context.objects_in_mode) != 1 or arm.pose.use_auto_ik or arm.pose.use_mirror_x
            or arm.data.pose_position != 'POSE'):
        return []
    names = []
    for pb in context.selected_pose_bones or ():
        if (not pb.bone.use_connect or not pb.bone.use_deform or pb.custom_shape is not None
                or all(pb.lock_location) or pb.is_in_ik_chain or pb.constraints or pb.location.length_squared > 0):
            continue
        if not any(parent.select for parent in pb.parent_recursive):
            names.append(pb.name)
    if not names or not joint_selection.is_skinned(arm):
        return []
    # Connected bones can have dormant location channels. Don't enable translation
    # on a joint that would jump or start playing an old track.
    ad = arm.animation_data
    if ad is None:
        return names
    if ad.nla_tracks:
        return []
    paths = {fc.data_path for fc in (*compat.id_fcurves(arm), *ad.drivers)}
    return [name for name in names if arm.pose.bones[name].path_from_id("location") not in paths]


def _set_connected(context, arm, names, connected):
    before = {pb.name for pb in arm.pose.bones if pb.select}
    active = arm.data.bones.active
    active_name = active.name if active is not None else None
    with context.temp_override(selected_editable_objects=[arm]):
        if bpy.ops.object.mode_set(mode='EDIT') != {'FINISHED'}:
            return False
        try:
            for name in names:
                arm.data.edit_bones[name].use_connect = connected
        finally:
            bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        pb.select = pb.name in before
    arm.data.bones.active = arm.data.bones.get(active_name) if active_name is not None else None
    context.view_layer.update()
    return True


def prepare(context):
    """Release the rest-tail attachment for the duration of a Move gesture."""
    names = _movable_joints(context)
    if not names:
        return
    arm = context.active_object
    if not _set_connected(context, arm, names, False):
        return
    window = live_refs.pointer(context.window)

    def settle():
        win = live_refs.window(window)
        if any(op.bl_idname.startswith("TRANSFORM_OT_") for op in live_refs.running_modals(win)):
            return 0.01
        try:
            with bpy.context.temp_override(window=win):
                ctx = bpy.context
                if ctx.active_object == arm and arm.mode == 'POSE':
                    # Blender restores the pose channels on cancel. Restore the
                    # connectivity too for joints with no translation of their own.
                    unchanged = [name for name in names if not arm.pose.bones[name].location.length_squared]
                    if unchanged:
                        _set_connected(ctx, arm, unchanged, True)
        except (ReferenceError, RuntimeError):
            pass
        return None

    # The gizmo invokes Blender's translate after this handler passes through.
    # Its undo step also captures the connectivity change.
    bpy.app.timers.register(settle, first_interval=0.01)


class ALLSET_OT_joint_move_prepare(bpy.types.Operator):
    """Allow the current Move drag to translate a skinned joint in Pose Mode"""
    bl_idname = "allset.joint_move_prepare"
    bl_label = "Prepare Pose Joint Move"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' and joint_selection.move_tool_active(context)

    def invoke(self, context, _event):
        from . import manip
        if context.gizmo_group is not None and not manip.from_xform_gizmo(context):
            return {'PASS_THROUGH'}
        prepare(context)
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_joint_move_prepare,)
