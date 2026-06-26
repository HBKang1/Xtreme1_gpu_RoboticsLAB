<template>
    <div class="i-toolbar-container">
        <div class="bar-left">
            <span style="display: inline-block; padding-right: 10px; min-width: 60px">{{
                editor.lang('autoLoad')
            }}</span>
            <a-tooltip placement="top">
                <template #title>{{ editor.lang('autoLoad') }}</template>
                <span @keydown.capture="(e) => e.stopPropagation()">
                    <a-switch
                        ref="autoLoadSwitch"
                        :checked="config.autoLoad"
                        @change="onAutoLoadHandle"
                        style="margin-right: 10px"
                    />
                </span>
            </a-tooltip>
            <!-- #3 ground toggle: RANSAC ground hide (view + AIBox snap only, default OFF) -->
            <a-tooltip placement="top">
                <template #title>{{ editor.lang('hideGround') }}</template>
                <span @keydown.capture="(e) => e.stopPropagation()">
                    <a-switch
                        size="small"
                        :checked="config.hideGround"
                        @change="onHideGroundHandle"
                        style="margin-right: 10px"
                    />
                </span>
            </a-tooltip>
            <div v-show="disable" class="over-not-allowed"></div>
        </div>
        <div class="bar-center">
            <div style="width: 100%; text-align: center">
                <a-tooltip v-if="canEdit()" placement="top">
                    <template #title>{{ editor.lang('copyLeft1') }}</template>
                    <a-button
                        :disabled="disable"
                        @click="() => onAction('CopyBackward')"
                        style="width: 40px"
                    >
                        <template #icon>
                            <div>
                                <StepBackwardOutlined />
                                <CopyOutlined
                                    style="
                                        margin-left: -4px;
                                        font-size: 14px;
                                        transform: rotateY(180deg);
                                    "
                                />
                            </div>
                        </template>
                    </a-button>
                </a-tooltip>

                <a-tooltip placement="top">
                    <template #title>{{
                        editor.lang('speedDown', {
                            n: state.playSpeed,
                        })
                    }}</template>
                    <a-button
                        :disabled="!canOperate()"
                        v-show="!isCheck()"
                        @click="onChangeSpeed(-1)"
                    >
                        <template #icon>
                            <i class="iconfont icon-zuo-fuzhi" />
                        </template>
                    </a-button>
                </a-tooltip>

                <a-tooltip placement="top">
                    <template #title>{{ editor.lang('replay') }}</template>
                    <a-button
                        :disabled="!canOperate()"
                        v-show="!isCheck()"
                        @click="() => onAction('Replay')"
                    >
                        <template #icon>
                            <i class="iconfont icon-chongxinbofang" />
                        </template>
                    </a-button>
                </a-tooltip>

                <a-tooltip placement="top">
                    <template #title>{{ editor.lang('pre') }}</template>
                    <a-button
                        :disabled="isPreDisabled"
                        @click="() => onAction('PreFrame')"
                        type="default"
                    >
                        <template #icon>
                            <i class="iconfont icon-shouqi" />
                        </template>
                    </a-button>
                </a-tooltip>
                <!-- @change="changeFrameIndex" -->
                <a-input-number
                    style="width: 80px"
                    :disabled="disable"
                    v-model:value="iState.frameIndex"
                    :precision="0"
                    @blur="() => changeFrameIndex('Input')"
                    @pressEnter="() => changeFrameIndex('Input')"
                    :min="1"
                    :max="total"
                    size="small"
                />
                <span class="i-span">/ {{ total }}</span>

                <a-tooltip placement="top">
                    <template #title>{{ editor.lang('next') }}</template>
                    <a-button
                        :disabled="isNextDisabled"
                        @click="() => onAction('NextFrame')"
                        type="default"
                    >
                        <template #icon>
                            <i class="iconfont icon-zhankai1" />
                        </template>
                    </a-button>
                </a-tooltip>

                <a-tooltip placement="top">
                    <template #title>{{
                        state.play
                            ? editor.lang('pause')
                            : editor.lang('play', { n: state.playSpeed })
                    }}</template>
                    <a-button
                        v-show="!isCheck()"
                        :disabled="!canOperate()"
                        @click="() => onAction(state.play ? 'Stop' : 'Play')"
                        type="default"
                    >
                        <template #icon>
                            <i class="iconfont icon-guaqi" v-if="state.play" />
                            <i class="iconfont icon-bofang" v-else />
                        </template>
                    </a-button>
                </a-tooltip>

                <a-tooltip placement="top">
                    <template #title>{{ editor.lang('speedUp', { n: state.playSpeed }) }}</template>
                    <a-button
                        :disabled="!canOperate()"
                        v-show="!isCheck()"
                        @click="onChangeSpeed(1)"
                    >
                        <template #icon>
                            <i class="iconfont icon-right-fuzhi" />
                        </template>
                    </a-button>
                </a-tooltip>

                <a-tooltip v-if="canEdit()" placement="top">
                    <template #title>{{ editor.lang('copyRight1') }}</template>
                    <a-button
                        :disabled="disable"
                        @click="() => onAction('CopyForward')"
                        style="width: 40px"
                    >
                        <template #icon>
                            <div>
                                <CopyOutlined style="margin-right: -4px; font-size: 14px" />
                                <StepForwardOutlined />
                            </div>
                        </template>
                    </a-button>
                </a-tooltip>

                <a-tooltip v-if="canEdit()" placement="top">
                    <template #title>Copy All to Next Frame (Alt+Shift+→)</template>
                    <a-button
                        :disabled="disable"
                        @click="() => onAction('CopyAllForward')"
                        style="width: 50px"
                    >
                        <template #icon>
                            <div>
                                <CopyOutlined style="margin-right: -4px; font-size: 14px" />
                                <CopyOutlined style="margin-right: -4px; font-size: 14px" />
                                <StepForwardOutlined />
                            </div>
                        </template>
                    </a-button>
                </a-tooltip>

                <!-- model tracking (prototype): propagate boxes N frames -->
                <template v-if="canEdit() && editor.state.isSeriesFrame">
                    <a-tooltip placement="top">
                        <template #title>{{ editor.lang('trackLeft1') }}</template>
                        <a-button
                            :disabled="disable"
                            @click="() => onAction('TrackBackward')"
                            style="width: 40px; margin-left: 8px"
                        >
                            <template #icon>
                                <div>
                                    <StepBackwardOutlined />
                                    <AimOutlined style="margin-left: -4px; font-size: 14px" />
                                </div>
                            </template>
                        </a-button>
                    </a-tooltip>
                    <a-tooltip placement="top">
                        <template #title>{{ editor.lang('trackRight1') }}</template>
                        <a-button
                            :disabled="disable"
                            @click="() => onAction('TrackForward')"
                            style="width: 40px"
                        >
                            <template #icon>
                                <div>
                                    <AimOutlined style="margin-right: -4px; font-size: 14px" />
                                    <StepForwardOutlined />
                                </div>
                            </template>
                        </a-button>
                    </a-tooltip>
                    <a-tooltip placement="top">
                        <template #title>{{ editor.lang('trackAllRight1') }}</template>
                        <a-button
                            :disabled="disable"
                            @click="() => onAction('TrackAllForward')"
                            style="width: 50px"
                        >
                            <template #icon>
                                <div>
                                    <AimOutlined style="margin-right: -4px; font-size: 14px" />
                                    <AimOutlined style="margin-right: -4px; font-size: 14px" />
                                    <StepForwardOutlined />
                                </div>
                            </template>
                        </a-button>
                    </a-tooltip>
                    <a-input-number
                        style="width: 44px"
                        :disabled="disable"
                        v-model:value="config.trackFrameN"
                        :precision="0"
                        :min="1"
                        :max="30"
                        size="small"
                    />
                    <a-popover placement="top" trigger="click">
                        <template #content>
                            <div style="display: flex; flex-direction: column; gap: 4px">
                                <a-checkbox v-model:checked="config.trackKeepZ">
                                    {{ editor.lang('trackKeepZ') }}
                                </a-checkbox>
                                <a-checkbox v-model:checked="config.trackKeepRotation">
                                    {{ editor.lang('trackKeepRot') }}
                                </a-checkbox>
                            </div>
                        </template>
                        <a-button :disabled="disable">
                            <template #icon><SettingOutlined /></template>
                        </a-button>
                    </a-popover>
                    <!-- offline relabel-only track association -->
                    <a-tooltip placement="top">
                        <template #title>{{ editor.lang('trackConnect') }}</template>
                        <a-button
                            :disabled="disable"
                            @click="() => onAction('TrackConnect')"
                            style="width: 40px; margin-left: 8px"
                        >
                            <template #icon><LinkOutlined /></template>
                        </a-button>
                    </a-tooltip>
                    <a-popover placement="top" trigger="click">
                        <template #content>
                            <div
                                style="
                                    display: flex;
                                    flex-direction: column;
                                    gap: 8px;
                                    min-width: 180px;
                                "
                            >
                                <a-radio-group
                                    v-model:value="config.trackAssocInputScope"
                                    size="small"
                                >
                                    <a-radio value="all">
                                        {{ editor.lang('trackConnectScopeAll') }}
                                    </a-radio>
                                    <a-radio value="model">
                                        {{ editor.lang('trackConnectScopeModel') }}
                                    </a-radio>
                                </a-radio-group>
                                <a-radio-group
                                    v-model:value="config.trackAssocRange"
                                    size="small"
                                >
                                    <a-radio value="all">
                                        {{ editor.lang('trackConnectRangeAll') }}
                                    </a-radio>
                                    <a-radio value="fromCurrent">
                                        {{ editor.lang('trackConnectRangeCurrent') }}
                                    </a-radio>
                                </a-radio-group>
                                <div style="display: flex; align-items: center; gap: 6px">
                                    <span>{{ editor.lang('trackConnectK') }}</span>
                                    <a-input-number
                                        style="width: 56px"
                                        v-model:value="config.trackAssocK"
                                        :precision="0"
                                        :min="0"
                                        :max="50"
                                        size="small"
                                    />
                                </div>
                            </div>
                        </template>
                        <a-button :disabled="disable">
                            <template #icon><SettingOutlined /></template>
                        </a-button>
                    </a-popover>
                    <!-- track merge / split (act on selected track + current frame) -->
                    <a-divider
                        type="vertical"
                        style="height: 24px; background-color: #57575c; margin: 0 6px"
                    />
                    <a-tooltip placement="top">
                        <template #title>{{ editor.lang('menuSetMergeBase') }}</template>
                        <a-button :disabled="disable" @click="onSetMergeBase" style="width: 40px">
                            <template #icon><PushpinOutlined /></template>
                        </a-button>
                    </a-tooltip>
                    <a-tooltip placement="top">
                        <template #title>{{
                            mergeBaseTrackId
                                ? editor.lang('menuMergeIntoBase')
                                : editor.lang('mergeNoBaseHint')
                        }}</template>
                        <a-button
                            :disabled="disable || !mergeBaseTrackId"
                            @click="onMergeIntoBase"
                            style="width: 40px"
                        >
                            <template #icon><MergeCellsOutlined /></template>
                        </a-button>
                    </a-tooltip>
                    <a-tooltip placement="top">
                        <template #title>{{ editor.lang('menuSplitHere') }}</template>
                        <a-button :disabled="disable" @click="onSplitHere" style="width: 40px">
                            <template #icon><SplitCellsOutlined /></template>
                        </a-button>
                    </a-tooltip>
                    <!-- #4 keyframe interpolation + #5 unify dimensions -->
                    <a-divider
                        type="vertical"
                        style="height: 24px; background-color: #57575c; margin: 0 6px"
                    />
                    <a-tooltip placement="top">
                        <template #title>{{
                            keyframeA === null || keyframeB === null
                                ? editor.lang('menuSetKeyframe')
                                : editor.lang('keyframeSetHint', { a: keyframeA + 1, b: keyframeB + 1 })
                        }}</template>
                        <a-button :disabled="disable" @click="onSetKeyframe" style="width: 40px">
                            <template #icon><BorderOutlined /></template>
                        </a-button>
                    </a-tooltip>
                    <a-tooltip placement="top">
                        <template #title>{{
                            keyframeA !== null && keyframeB !== null
                                ? editor.lang('menuInterpolate')
                                : editor.lang('interpolateNoKeyframeHint')
                        }}</template>
                        <a-button
                            :disabled="disable || keyframeA === null || keyframeB === null"
                            @click="onInterpolate"
                            style="width: 40px"
                        >
                            <template #icon><LineChartOutlined /></template>
                        </a-button>
                    </a-tooltip>
                    <a-tooltip placement="top">
                        <template #title>{{ editor.lang('menuUnifyDimensions') }}</template>
                        <a-button :disabled="disable" @click="onUnifyDimensions" style="width: 40px">
                            <template #icon><ColumnWidthOutlined /></template>
                        </a-button>
                    </a-tooltip>
                </template>
            </div>
        </div>
        <div class="bar-right" v-show="!isCheck()" v-if="canEdit()">
            <!-- object tracking -->
            <!-- <toolTipTrack v-if="isAnnotate()" :state="state" /> -->
            <!-- <div class="divide-line"> </div> -->

            <!-- <toolTipMerge v-if="!isGroup()" :state="state" @action="onTrackAction" /> -->

            <!-- <toolTipSplit v-if="!isGroup()" :state="state" @action="onTrackAction" /> -->

            <a-tooltip placement="top">
                <template #title>{{ editor.lang('delete') }}</template>
                <a-button @click="() => onTrackAction('Delete')">
                    <template #icon>
                        <i class="iconfont icon-shanchuicon" />
                    </template>
                </a-button>
            </a-tooltip>
            <div v-show="disable" class="over-not-allowed"></div>
        </div>
    </div>
</template>
<script lang="ts" setup>
    import * as _ from 'lodash';
    import { ref, computed, watch, reactive, onBeforeUnmount } from 'vue';

    import useUI from '../../hook/useUI';
    import { ITrackAction, IBottomState } from './useTimeLine';

    import {
        StepForwardOutlined,
        StepBackwardOutlined,
        CopyOutlined,
        AimOutlined,
        SettingOutlined,
        LinkOutlined,
        PushpinOutlined,
        MergeCellsOutlined,
        SplitCellsOutlined,
        BorderOutlined,
        LineChartOutlined,
        ColumnWidthOutlined,
    } from '@ant-design/icons-vue';
    import * as THREE from 'three';
    import { Box } from 'pc-render';
    import {
        isRigidClass,
        TRACK_FALLBACK_CONFIDENCE,
        IFrame,
        IUserData,
        Event as EditorEvent,
    } from 'pc-editor';
    import { useInjectEditor } from '../../state';
    import { useTrackMergeBase } from './useTrackMergeBase';
    const { mergeBaseTrackId } = useTrackMergeBase();
    const props = defineProps<{
        state: IBottomState;
    }>();
    const { canEdit, isCheck, canOperate } = useUI();
    const editor = useInjectEditor();
    const config = editor.state.config;
    const iState = reactive({
        // autoLoad: false,
        frameIndex: editor.state.frameIndex + 1,
    });
    const autoLoadSwitch = ref<HTMLElement>();
    const emit = defineEmits(['onTrackAction', 'updateTrackLine']);

    watch(
        () => editor.state.frameIndex,
        () => {
            if (iState.frameIndex !== editor.state.frameIndex + 1)
                iState.frameIndex = editor.state.frameIndex + 1;
        },
        { immediate: true },
    );

    const isPreDisabled = computed(() => {
        return editor.state.frameIndex <= 0 || disable.value;
    });
    const isNextDisabled = computed(() => {
        return editor.state.frameIndex >= editor.state.frames.length - 1 || disable.value;
    });
    const total = computed(() => {
        return editor.state.frames.length;
    });

    type IBarAction =
        | 'CopyForward'
        | 'CopyBackward'
        | 'CopyAllForward'
        | 'TrackForward'
        | 'TrackBackward'
        | 'TrackAllForward'
        | 'TrackConnect'
        | 'AutoLoad'
        | 'Replay'
        | 'PreFrame'
        | 'NextFrame'
        | 'Play'
        | 'Stop'
        | 'Check';

    function onChangeSpeed(dir: 1 | -1) {
        const state = props.state;
        const scale = dir === 1 ? 2 : 0.5;
        state.playSpeed *= scale;
        state.playSpeed = Math.max(0.5, Math.min(4, state.playSpeed));
        editor.playManager.interval = Math.round(300 / state.playSpeed);
    }
    function onTrackAction(action: ITrackAction) {
        emit('onTrackAction', action);
    }
    function onAutoLoadHandle() {
        autoLoadSwitch.value?.blur();
        onAction('AutoLoad');
    }

    // --- #3 ground toggle (view + AIBox snap reference only; saved geometry unchanged) ---
    function onHideGroundHandle(checked: boolean) {
        editor.configManager.setHideGround(checked);
    }

    // --- #4 keyframe interpolation (fill empty/fallback frames between two keyframes) ---
    const keyframeA = ref<number | null>(null);
    const keyframeB = ref<number | null>(null);
    // the track A/B were set on — guards against interpolating with keyframes from a
    // different (previously selected) track. selection (pc.selection) is a non-reactive
    // THREE array, so a Vue watch over getCurTrack() can miss changes; instead reset on
    // the editor's ANNOTATE_SELECT event, which fires on every selection change.
    const keyframeTrackId = ref<string | null>(null);

    function resetKeyframes() {
        keyframeA.value = null;
        keyframeB.value = null;
        keyframeTrackId.value = null;
    }

    function onTrackSelectionChange() {
        // drop keyframes whenever the selected track differs from where A/B were set
        if (keyframeTrackId.value && editor.getCurTrack() !== keyframeTrackId.value) {
            resetKeyframes();
        }
    }
    editor.addEventListener(EditorEvent.ANNOTATE_SELECT, onTrackSelectionChange);
    onBeforeUnmount(() => {
        editor.removeEventListener(EditorEvent.ANNOTATE_SELECT, onTrackSelectionChange);
    });

    function onSetKeyframe() {
        const trackId = editor.getCurTrack();
        if (!trackId) {
            editor.showMsg('warning', editor.lang('mergeNoSelect'));
            return;
        }
        const idx = editor.state.frameIndex;
        // first click sets A; second sets B; third restarts from A
        if (keyframeA.value === null || keyframeB.value !== null) {
            keyframeA.value = idx;
            keyframeB.value = null;
            keyframeTrackId.value = trackId;
            editor.showMsg('success', editor.lang('keyframeASet', { a: idx + 1 }));
            return;
        }
        // B must be set on the SAME track as A
        if (trackId !== keyframeTrackId.value) {
            keyframeA.value = idx;
            keyframeB.value = null;
            keyframeTrackId.value = trackId;
            editor.showMsg('success', editor.lang('keyframeASet', { a: idx + 1 }));
            return;
        }
        if (idx === keyframeA.value) {
            editor.showMsg('warning', editor.lang('keyframeSameHint'));
            return;
        }
        keyframeB.value = idx;
        // normalize so A < B
        if (keyframeA.value > keyframeB.value) {
            [keyframeA.value, keyframeB.value] = [keyframeB.value, keyframeA.value];
        }
        editor.showMsg(
            'success',
            editor.lang('keyframeBSet', { a: keyframeA.value + 1, b: keyframeB.value + 1 }),
        );
    }

    // shortest-angle yaw interpolation (R-heading): take the signed delta wrapped to
    // (-π, π] so the box never spins the long way around.
    function lerpAngle(a: number, b: number, t: number): number {
        let delta = b - a;
        delta = delta - Math.floor((delta + Math.PI) / (2 * Math.PI)) * 2 * Math.PI; // wrap to (-π, π]
        return a + delta * t;
    }

    function onInterpolate() {
        const trackId = editor.getCurTrack();
        if (!trackId) {
            editor.showMsg('warning', editor.lang('mergeNoSelect'));
            return;
        }
        const a = keyframeA.value;
        const b = keyframeB.value;
        if (a === null || b === null) {
            editor.showMsg('warning', editor.lang('interpolateNoKeyframeHint'));
            return;
        }
        // FIX 2 guard: never interpolate with keyframes set on a different track
        if (keyframeTrackId.value && keyframeTrackId.value !== trackId) {
            resetKeyframes();
            editor.showMsg('warning', editor.lang('interpolateTrackMismatch'));
            return;
        }

        const { frames } = editor.state;
        const trackListMap = editor.trackManager.getTrackObjectMap(trackId);
        const trackList = trackListMap[trackId] || [];

        const boxA = (trackList[a] || []).find((o) => o instanceof Box) as Box | undefined;
        const boxB = (trackList[b] || []).find((o) => o instanceof Box) as Box | undefined;
        if (!boxA || !boxB) {
            editor.showMsg('warning', editor.lang('interpolateNoEndpoint'));
            return;
        }

        // metadata shared by every interpolated box (taken from endpoint A's track)
        const baseUserData = editor.getObjectUserData(boxA);

        // existing fallback boxes → transform in place; empty frames → create a box
        // bound DIRECTLY to that frame (NOT via addModelTrackData, which re-derives the
        // track from getCurrentFrame() and throws when the user is parked on a gap frame)
        const updateObjects: Box[] = [];
        const updateTransforms: { position: THREE.Vector3; scale: THREE.Vector3; rotation: THREE.Euler }[] = [];
        const addByFrame: { objects: Box[]; frame: IFrame }[] = [];

        for (let i = a + 1; i < b; i++) {
            const t = (i - a) / (b - a);
            const position = new THREE.Vector3().lerpVectors(boxA.position, boxB.position, t);
            const scale = new THREE.Vector3().lerpVectors(boxA.scale, boxB.scale, t);
            const rotZ = lerpAngle(boxA.rotation.z, boxB.rotation.z, t);
            const rotation = new THREE.Euler(0, 0, rotZ);

            const existing = (trackList[i] || []).find((o) => o instanceof Box) as Box | undefined;
            if (existing) {
                const conf = (existing.userData as any).confidence;
                // preserve human-edited (non-fallback) boxes; only replace fallbacks
                if (conf !== TRACK_FALLBACK_CONFIDENCE) continue;
                updateObjects.push(existing);
                updateTransforms.push({ position, scale, rotation });
            } else {
                // empty frame → create a box targeting THIS frame directly
                const frame = frames[i];
                if (!frame) continue;
                const userData: IUserData = {
                    trackId: baseUserData.trackId,
                    trackName: baseUserData.trackName,
                    classType: baseUserData.classType,
                    classId: baseUserData.classId,
                    // fallback confidence so a later re-interpolation can replace it,
                    // and #1's review queue treats it as an unverified propagation
                    confidence: TRACK_FALLBACK_CONFIDENCE,
                };
                const object = editor.createAnnotate3D(position, scale, rotation, userData);
                editor.updateObjectRenderInfo(object);
                addByFrame.push({ objects: [object], frame });
            }
        }

        if (updateObjects.length === 0 && addByFrame.length === 0) {
            editor.showMsg('warning', editor.lang('interpolateNothing'));
            return;
        }

        editor.cmdManager.withGroup(() => {
            if (addByFrame.length > 0) {
                editor.cmdManager.execute('add-object', addByFrame);
            }
            if (updateObjects.length > 0) {
                editor.cmdManager.execute('update-transform-batch', {
                    objects: updateObjects,
                    transforms: updateTransforms,
                });
            }
        });

        // mark every touched frame dirty so it persists on save
        updateObjects.forEach((o) => {
            const f = (o as any).frame as IFrame | undefined;
            if (f) f.needSave = true;
        });
        addByFrame.forEach((d) => {
            d.frame.needSave = true;
        });

        editor.pc.render();
        emit('updateTrackLine');
        editor.showMsg('success', editor.lang('interpolateDone'));
    }

    // --- #5 unify dimensions (lock rigid-class track size to the component-wise median) ---
    function median(values: number[]): number {
        const sorted = [...values].sort((x, y) => x - y);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
    }

    function onUnifyDimensions() {
        const trackId = editor.getCurTrack();
        if (!trackId) {
            editor.showMsg('warning', editor.lang('mergeNoSelect'));
            return;
        }
        const trackListMap = editor.trackManager.getTrackObjectMap(trackId);
        const boxes: Box[] = [];
        (trackListMap[trackId] || []).forEach((items) => {
            (items || []).forEach((o) => {
                if (o instanceof Box) boxes.push(o);
            });
        });
        if (boxes.length === 0) {
            editor.showMsg('warning', editor.lang('mergeNoSelect'));
            return;
        }

        const className = editor.getClassType(editor.getObjectUserData(boxes[0]))?.name;
        if (!isRigidClass(className)) {
            // Pedestrian (and any non-rigid class) → no-op + warning
            editor.showMsg('warning', editor.lang('unifyNotRigid'));
            return;
        }
        if (boxes.length < 2) {
            editor.showMsg('warning', editor.lang('unifyTooShort'));
            return;
        }

        const medianSize = new THREE.Vector3(
            median(boxes.map((b) => b.scale.x)),
            median(boxes.map((b) => b.scale.y)),
            median(boxes.map((b) => b.scale.z)),
        );

        editor.cmdManager.withGroup(() => {
            editor.cmdManager.execute('update-transform-batch', {
                objects: boxes,
                transforms: { scale: medianSize } as any,
            });
        });
        boxes.forEach((o) => {
            const f = (o as any).frame as IFrame | undefined;
            if (f) f.needSave = true;
        });
        editor.pc.render();
        emit('updateTrackLine');
        editor.showMsg('success', editor.lang('unifyDone'));
    }

    // --- track merge / split (operate on the selected track + current frame) ---
    function onSetMergeBase() {
        const trackId = editor.getCurTrack();
        if (!trackId) {
            editor.showMsg('warning', editor.lang('mergeNoSelect'));
            return;
        }
        mergeBaseTrackId.value = trackId;
        editor.showMsg('success', editor.lang('successSetMergeBase'));
    }
    // the visible "Cuboid N" is the box's own userData.trackName; find it from a
    // loaded box (trackManager.trackMap metadata can hold a different trackName)
    function findTrackName(trackId: string): string {
        for (const frame of editor.state.frames) {
            const objs = editor.dataManager.getFrameObject(frame.id) || [];
            const box = objs.find(
                (o) => o instanceof Box && (o.userData as any).trackId === trackId,
            ) as Box | undefined;
            if (box) return ((box.userData as any).trackName as string) || '';
        }
        return '';
    }
    function onMergeIntoBase() {
        const trackId = editor.getCurTrack();
        const baseTrackId = mergeBaseTrackId.value;
        if (!trackId) {
            editor.showMsg('warning', editor.lang('mergeNoSelect'));
            return;
        }
        if (!baseTrackId || baseTrackId === trackId) {
            editor.showMsg('warning', editor.lang('mergeNoBaseHint'));
            return;
        }
        const { code } = editor.trackManager.canMerge(trackId, baseTrackId);
        if (code !== 'ok') {
            editor.showMsg(
                'warning',
                code === 'object_repeat'
                    ? editor.lang('warnObjectRepeat')
                    : editor.lang('warnClassTypeDiff'),
            );
            return;
        }
        try {
            // pin the base's real (displayed) trackName so merged boxes adopt it
            // instead of a stale trackMap metadata name
            const baseName = findTrackName(baseTrackId);
            if (baseName) {
                if (editor.trackManager.hasTrackObject(baseTrackId)) {
                    editor.trackManager.updateTrackData(baseTrackId, { trackName: baseName });
                } else {
                    editor.trackManager.addTrackObject(baseTrackId, {
                        trackId: baseTrackId,
                        trackName: baseName,
                    });
                }
            }
            editor.trackManager.mergeTrackObject(trackId, baseTrackId);
            mergeBaseTrackId.value = '';
            editor.showMsg('success', editor.lang('successMerge'));
        } catch (error) {
            editor.showMsg('error', editor.lang('errorMerge'));
        }
    }
    function onSplitHere() {
        const trackId = editor.getCurTrack();
        if (!trackId) {
            editor.showMsg('warning', editor.lang('mergeNoSelect'));
            return;
        }
        const start = editor.state.frameIndex;
        if (!editor.trackManager.canSplit(trackId, start)) {
            editor.showMsg('warning', editor.lang('warnEmptyObject'));
            return;
        }
        const box = editor.pc.selection.find((o) => o instanceof Box) as Box | undefined;
        const userData = box ? box.userData : ({} as any);
        try {
            editor.trackManager.splitTrackObject({
                trackId,
                start,
                userData: { classType: userData.classType, classId: userData.classId } as any,
            });
            editor.showMsg('success', editor.lang('successSplit'));
        } catch (error) {
            editor.showMsg('error', editor.lang('errorSplit'));
        }
    }
    function onAction(action: IBarAction) {
        const { frames } = editor.state;
        switch (action) {
            case 'AutoLoad':
                editor.dataResource.setLoadMode(config.autoLoad ? 'near_2' : 'all');
                editor.dataResource.load();
                break;
            case 'CopyForward':
                editor.dataManager.copyForward();
                break;

            case 'CopyBackward':
                editor.dataManager.copyBackWard();
                break;

            case 'CopyAllForward':
                editor.dataManager.copyAllForward();
                break;

            case 'TrackForward':
                editor.dataManager.trackForward();
                break;

            case 'TrackBackward':
                editor.dataManager.trackBackward();
                break;

            case 'TrackAllForward':
                editor.dataManager.trackAllForward();
                break;
            case 'TrackConnect':
                editor.dataManager.trackConnect();
                break;
            case 'Replay':
                rePlay();
                break;
            case 'PreFrame':
                iState.frameIndex = Math.max(1, Math.min(frames.length, iState.frameIndex - 1));
                changeFrameIndex('Previous');
                break;
            case 'NextFrame':
                iState.frameIndex = Math.max(1, Math.min(frames.length, iState.frameIndex + 1));
                changeFrameIndex('Next');
                break;
            case 'Play':
                play();
                break;
            case 'Stop':
                editor.playManager.stop();
                break;
            case 'Check':
                onCheck();
                break;
        }
    }

    function onCheck() {
        // editor.actionManager.execute('toggleShowCheckView');
    }

    async function rePlay() {
        if (editor.playManager.playing) {
            editor.playManager.stop();
        }
        await editor.loadFrame(props.state.playStart, false);
        play();
    }

    function play() {
        const { frames, frameIndex } = editor.state;
        const pState = props.state;
        const nextData = frames[frameIndex + 1];
        if (!nextData || nextData.loadState !== 'complete') {
            editor.showMsg('warning', editor.lang('noPlayData'));
            return;
        }

        pState.play = true;
        pState.playStart = frameIndex;
        editor.playManager.play();
    }

    const changeFrameIndex = _.debounce((method: 'Input' | 'Next' | 'Previous') => {
        const beforeIndex = editor.state.frameIndex;
        if (!iState.frameIndex) iState.frameIndex = 1;
        editor.loadFrame(iState.frameIndex - 1);
        // editor.reportManager.reportChangeFrame(method, beforeIndex + 1);
        // frameIndexChange(iState.frameIndex);
    }, 300);

    const disable = computed(() => {
        return !canOperate() || props.state.play;
    });
</script>
<style lang="less">
    .i-toolbar-container {
        display: flex;
        position: relative;
        align-items: center;
        // ponytail: wrap onto a second row instead of clipping when there are many buttons
        flex-wrap: wrap;
        row-gap: 2px;
        overflow: visible;
        min-height: 32px;
        background-color: #1e1f22;
        flex-direction: row;

        .iconfont {
            font-size: 14px;
        }

        .bar-left {
            display: flex;
            position: relative;
            align-items: center;
            flex-wrap: wrap;
            height: auto;
        }

        .bar-right {
            display: flex;
            position: relative;
            align-items: center;
            flex-wrap: wrap;
            height: auto;
        }

        .bar-center {
            display: flex;
            position: relative;
            align-items: center;
            height: 100%;
            flex: 1;
        }

        &::-webkit-scrollbar {
            // display: none;
            position: absolute;
            height: 2px;
        }

        .i-margin-right {
            margin-right: 1px;
        }

        .ant-input-number-handler-wrap {
            display: none;
        }

        .ant-input-number {
            margin-left: 2px;
        }

        .ant-input-number-input {
            background-color: white;
            text-align: center;
            color: black;
        }

        .empty-space {
            display: inline-block;
            width: 80px;
            height: 20px;
        }

        .divide-line {
            display: inline-block;
            margin: 0 10px;
            width: 1px;
            height: 20px;
            border-left: 1px solid white;
        }

        .ant-btn {
            border: none;
        }

        .i-span {
            display: inline-block;
            user-select: none;
            margin: 0 4px;
        }

        .item {
            display: inline-block;
            margin-left: 10px;
            cursor: pointer;

            &.icon {
                margin-right: 5px;
                margin-left: 8px;
            }
        }
    }

    .frame-setting {
        width: 220px;

        .wrap {
            margin-top: 10px;
            padding-right: 4px;
            padding-left: 6px;
        }

        .title {
            font-size: 14px;
            text-align: center;
            line-height: 32px;
        }

        .title1 {
            font-size: 12px;
            text-align: left;
            // padding-bottom: 8px;
            line-height: 32px;
        }

        .title2 {
            display: flex;
            font-size: 12px;
            color: white;
            line-height: 32px;

            .ant-input-number-input {
                text-align: center;
            }

            > label {
                display: inline-block;
                padding: 0 8px 0 0;
                min-width: 70px;
                text-align: left;
                line-height: 32px;
            }
        }
    }
</style>
