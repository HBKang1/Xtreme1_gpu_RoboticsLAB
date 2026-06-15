import { IObject, IFrame, IModelResult } from '../type';
import { AnnotateObject, Box, Rect, Box2D, ITransform, Object2D } from 'pc-render';
import Editor from '../Editor';
import { Event as EditorEvent } from 'pc-editor';
// import * as api from '../api';
import * as utils from '../utils';
import { Const, ICmdName, IFilter, IUserData, SourceType } from '../type';
import Event from '../config/event';
import * as THREE from 'three';

interface ITransform2DBox {
    positions2?: Record<number, THREE.Vector2>;
    positions1?: Record<number, THREE.Vector2>;
}

interface ITransform2DRect {
    center?: THREE.Vector2;
    size?: THREE.Vector2;
}

export type IAnnotateTransform = ITransform2DBox | ITransform2DRect | ITransform;

export default class DataManager {
    editor: Editor;
    // object
    dataMap: Map<string, AnnotateObject[]> = new Map();
    hasMap: Map<string, Map<string, AnnotateObject>> = new Map();
    constructor(editor: Editor) {
        this.editor = editor;
        this.initEvent();
    }

    hasObject(uuid: string, frame?: IFrame): boolean {
        frame = frame || this.editor.getCurrentFrame();
        let frameMap = this.hasMap.get(frame.id);
        return !!frameMap && frameMap.has(uuid);
    }

    setHasMap(uuid: string, object: AnnotateObject, frame?: IFrame) {
        frame = frame || this.editor.getCurrentFrame();
        let frameMap = this.hasMap.get(frame.id);
        if (!frameMap) frameMap = new Map();
        frameMap.set(uuid, object);
    }

    removeHasMap(uuid: string, frame?: IFrame) {
        frame = frame || this.editor.getCurrentFrame();
        let frameMap = this.hasMap.get(frame.id);
        if (frameMap) frameMap.delete(uuid);
    }

    addAnnotates(
        objects: AnnotateObject[] | AnnotateObject,
        frame?: IFrame,
        reload: boolean = true,
    ) {
        if (!Array.isArray(objects)) objects = [objects];

        frame = frame || this.editor.getCurrentFrame();
        let allObjects = this.getFrameObject(frame.id) || [];

        objects.forEach((e) => {
            if (this.hasObject(e.uuid, frame)) return;
            allObjects.push(e);
            this.setHasMap(e.uuid, e, frame);
            this.editor.trackManager.updateObjectRenderInfo(e);
        });

        frame.needSave = true;
        this.setFrameObject(frame.id, allObjects);
        if (reload) this.loadDataFromManager();
        this.onAnnotatesAdd(objects, frame);
    }

    removeAnnotates(
        objects: AnnotateObject[] | AnnotateObject,
        frame?: IFrame,
        reload: boolean = true,
    ) {
        if (!Array.isArray(objects)) objects = [objects];

        frame = frame || this.editor.getCurrentFrame();
        let allObjects = this.getFrameObject(frame.id) || [];
        if (allObjects.length === 0) return;

        let removeMap = {} as Record<string, boolean>;
        let selectionMap = this.editor.pc.selectionMap;
        let selectFlag = false;
        objects.forEach((e) => {
            removeMap[e.uuid] = true;
            this.removeHasMap(e.uuid, frame);
            if (selectionMap[e.uuid]) {
                selectFlag = true;
                delete selectionMap[e.uuid];
            }
        });

        if (selectFlag) this.editor.updateSelect();

        let remainObjects = allObjects.filter((e) => !removeMap[e.uuid]);
        frame.needSave = true;
        this.setFrameObject(frame.id, remainObjects);
        if (reload) this.loadDataFromManager();
        this.onAnnotatesRemove(objects, frame);
    }

    setAnnotatesVisible(
        objects: AnnotateObject | AnnotateObject[],
        visible: boolean | boolean[],
        frame?: IFrame,
    ) {
        if (!Array.isArray(objects)) objects = [objects];
        frame = frame || this.editor.getCurrentFrame();

        let selectionMap = this.editor.pc.selectionMap;
        let selectFlag = false;
        let isMultiVisible = Array.isArray(visible);
        objects.forEach((object, index) => {
            let visibleNew = isMultiVisible ? visible[index] : visible;
            object.visible = visibleNew;
            if (!visibleNew && selectionMap[object.uuid]) {
                delete selectionMap[object.uuid];
                selectFlag = true;
            }
        });

        if (selectFlag) this.editor.updateSelect();

        this.onAnnotatesChange(objects, frame, { type: 'visible', visible });
    }

    setAnnotatesUserData(
        objects: AnnotateObject[] | AnnotateObject,
        datas: IUserData | IUserData[],
        frame?: IFrame,
    ) {
        if (!Array.isArray(objects)) objects = [objects];

        frame = frame || this.editor.getCurrentFrame();
        frame.needSave = true;
        objects.forEach((obj, index) => {
            // TODO
            let frame = (obj as any).frame as IFrame;
            if (frame) frame.needSave = true;

            let data = Array.isArray(datas) ? datas[index] : datas;
            const needUpdateInfo = data.hasOwnProperty('trackId');
            if (needUpdateInfo) {
                this.editor.trackManager.removeTrackCount(obj, frame);
            }
            Object.assign(obj.userData, data);
            if (needUpdateInfo) {
                this.editor.trackManager.addTrackCount(obj, frame);
            }
        });
        // this.editor.pc.setObjectUserData(objects,datas);
        this.onAnnotatesChange(objects, frame, { type: 'userData', datas });
    }

    setAnnotatesTransform(
        objects: AnnotateObject[] | AnnotateObject,
        datas: IAnnotateTransform | IAnnotateTransform[],
        frame?: IFrame,
    ) {
        if (!Array.isArray(objects)) objects = [objects];

        frame = frame || this.editor.getCurrentFrame();
        objects.forEach((obj, index) => {
            let data = Array.isArray(datas) ? datas[index] : datas;
            if (obj instanceof Box) {
                this.editor.pc.updateObjectTransform(obj, data as any);
            } else if (obj instanceof Rect) {
                this.editor.pc.update2DRect(obj, data as any);
            } else if (obj instanceof Box2D) {
                this.editor.pc.update2DBox(obj, data as any);
            }
        });

        this.onAnnotatesChange(objects, frame, { type: 'transform', datas });
    }

    initEvent() {}

    clear() {
        this.dataMap.clear();
    }

    onAnnotatesChange(
        objects: AnnotateObject[],
        frame?: IFrame,
        data?: { type?: 'userData' | 'transform' | 'visible'; [k: string]: any },
    ) {
        frame = frame || this.editor.getCurrentFrame();
        frame.needSave = true;
        this.editor.pc.render();

        if (data?.type === 'transform') {
            // ANNOTATE_TRANSFORM_CHANGE
            this.editor.dispatchEvent({
                type: Event.ANNOTATE_TRANSFORM_CHANGE,
                data: { ...data, frame, objects },
            });
        } else {
            console.log('onAnnotatesChange', { ...data, frame });
            this.editor.dispatchEvent({
                type: Event.ANNOTATE_CHANGE,
                data: { ...data, frame, objects },
            });
        }
    }

    onAnnotatesAdd(objects: AnnotateObject[], frame?: IFrame) {
        frame = frame || this.editor.getCurrentFrame();
        frame.needSave = true;
        this.editor.pc.render();
        console.log('onAnnotatesAdd', { objects, frame });
        this.editor.trackManager.addTrackCount(objects, frame);
        this.editor.dispatchEvent({ type: Event.ANNOTATE_ADD, data: { objects, frame } });
    }

    onAnnotatesRemove(objects: AnnotateObject[], frame?: IFrame) {
        frame = frame || this.editor.getCurrentFrame();
        frame.needSave = true;
        this.editor.pc.render();
        console.log('onAnnotatesRemove', { objects, frame });
        this.editor.trackManager.removeTrackCount(objects, frame);
        this.editor.dispatchEvent({ type: Event.ANNOTATE_REMOVE, data: { objects, frame } });
    }

    setFrameObject(frameId: string, objects: AnnotateObject[]) {
        let frame = this.editor.getFrame(frameId);
        objects.forEach((e) => {
            (e as any).frame = frame;
        });
        this.dataMap.set(frameId, objects);
    }

    getFrameObject(frameId: string) {
        return this.dataMap.get(frameId);
    }

    loadDataFromManager() {
        let frame = this.editor.getCurrentFrame();

        console.log('loadDataFromManager', this.editor.state.frameIndex);

        let objects = this.getFrameObject(frame.id) || [];
        let {
            config: { withoutTaskId },
        } = this.editor.state;
        // console.log(config, config.dataId, objects);

        if (this.editor.needUpdateFilter) this.setFilterFromData();

        let filterMap = this.getActiveFilter();
        // console.log('filterMap', filterMap);
        let annotate2D = [] as Object2D[];
        let annotate3D = [] as Box[];
        // let filterObjects = [] as AnnotateObject[];
        objects.forEach((e) => {
            let userData = e.userData as Required<IUserData>;

            let sourceId = userData.sourceId || withoutTaskId;
            let valid = filterMap.all || filterMap.source[sourceId];
            if (!valid) return;

            if (e instanceof Box) {
                e.parent = this.editor.pc.annotate3D;
                annotate3D.push(e);
            } else if (e instanceof Object2D) annotate2D.push(e);

            // filterObjects.push(e);
        });

        // this.editor.pc.addObject(annotate3D);
        this.editor.pc.annotate2D = annotate2D;
        this.editor.pc.annotate3D.children = annotate3D;
        this.editor.dispatchEvent({ type: Event.ANNOTATE_LOAD });
        this.editor.pc.render();
        // this.editor.updateIDCounter();
    }

    setFilterFromData() {
        let { frameIndex, frames } = this.editor.state;
        let { FILTER_ALL } = this.editor.state.config;

        // if (this.editor.playManager.playing) {
        //     this.editor.state.filterActive = [FILTER_ALL];
        //     return;
        // }

        let frame = this.editor.getCurrentFrame();
        let objects = this.getFrameObject(frame.id) || [];
        let all: IFilter = { value: FILTER_ALL, label: FILTER_ALL, type: '' };
        let project: IFilter = { label: 'Ground Truth', options: [], type: 'project' };
        let model: IFilter = { label: 'Model Runs', options: [], type: 'model' };

        let projectMap = {};
        let modelMap = {};

        objects.forEach((object) => {
            let userData = object.userData as Required<IUserData>;
            if (userData.modelRun) {
                let id = userData.modelRun || '';
                let label = userData.modelRunLabel || '';
                if (!modelMap[id]) {
                    let option = { value: id, label: label };
                    model.options?.push(option);
                    modelMap[id] = option;
                }
            } else {
                let name = userData.project || '';
                if (!projectMap[name]) {
                    let option = { value: name, label: name || 'No Project' };
                    project.options?.push(option);
                    projectMap[name] = option;
                }
            }
        });

        let filters = [all] as IFilter[];

        if ((project as any).options.length > 0) filters.push(project);
        if ((model as any).options.length > 0) filters.push(model);

        this.editor.state.filters = filters;
        if (this.editor.state.filterActive.length === 0)
            this.editor.state.filterActive = [FILTER_ALL];

        this.editor.needUpdateFilter = false;
    }

    getActiveFilter() {
        let { FILTER_ALL } = this.editor.state.config;
        let { sourceFilters } = this.editor.state;

        let filterMap = {
            all: false,
            source: {},
            // project: {},
            // model: {},
        };
        sourceFilters.forEach((filter) => {
            if (filter === FILTER_ALL) filterMap.all = true;
            else {
                filterMap.source[filter] = true;
            }
        });

        return filterMap;
    }

    getMaxId(frameId?: string) {
        let { frameIndex, frames } = this.editor.state;
        let curFrame = frames[frameIndex];

        let objects = this.getFrameObject(frameId || curFrame.id) || [];
        let maxId = 0;
        objects.forEach((e) => {
            if (!e.userData.trackName) return;
            let id = parseInt(e.userData.trackName);
            if (id > maxId) maxId = id;
        });
        return maxId;
    }

    updateFrameId(frameId?: string) {
        let { frameIndex, frames } = this.editor.state;
        let curFrame = frames[frameIndex];

        frameId = frameId || curFrame.id;
        let objects = this.getFrameObject(frameId) || [];

        let startId = this.getMaxId(frameId) + 1;
        objects.forEach((e) => {
            let userData = e.userData as IUserData;
            userData.id = userData.id || THREE.MathUtils.generateUUID();

            if (userData.trackId) return;

            userData.trackId = this.editor.createTrackId();
            userData.trackName = startId++ + '';
        });

        // if (curFrame && frameId === curFrame.id) this.editor.idCount = startId;
    }

    updateBackId(keyMap: Record<string, Record<string, string>>) {
        Object.keys(keyMap).forEach((dataId) => {
            let dataKeyMap = keyMap[dataId];
            let annotates = this.getFrameObject(dataId) || [];
            annotates.forEach((annotate) => {
                let frontId = annotate.uuid;
                let backId = dataKeyMap[frontId];
                if (!backId) return;
                (annotate.userData as IUserData).backId = backId;
                // annotate.uuid = backId;
            });
        });
    }

    async pollDataModelResult() {}

    // tracking prototype: direct serving call (no backend model-run record, no polling)
    async runModelTrack(
        curId: string,
        toIds: string[],
        direction: 'BACKWARD' | 'FORWARD',
        targetObjects: any[],
        trackIdName: Record<string, string>,
        onComplete?: () => void,
    ) {
        let editor = this.editor;
        editor.showLoading(true);
        try {
            let results = await editor.businessManager.runModelTrack({
                seedObjects: targetObjects,
                frames: toIds.map((id) => ({ id })),
                keep: {
                    z: editor.state.config.trackKeepZ,
                    rotation: editor.state.config.trackKeepRotation,
                },
            });

            // addModelTrackData resolves a new box's inherited identity from the
            // CURRENT frame's objects — drop result tracks without a seed there
            let curTrackIds = new Set<string>();
            (this.getFrameObject(curId) || []).forEach((e) => {
                if (e instanceof Box) curTrackIds.add(e.userData.trackId);
            });

            let objectsMap = {} as Record<string, IObject[]>;
            (results || []).forEach((frameResult: any) => {
                if (!frameResult || frameResult.code !== 'OK') return;
                let objects = (frameResult.objects || [])
                    .filter((e: any) => {
                        if (curTrackIds.has(e.trackingId)) return true;
                        console.warn('track result without current-frame seed:', e.trackingId);
                        return false;
                    })
                    .map((e: any) => {
                        e.trackId = e.trackingId;
                        e.trackName = trackIdName[e.trackingId] || '';
                        e.objType = '3d';
                        return e as IObject;
                    });
                if (objects.length > 0) objectsMap[frameResult.id + ''] = objects;
            });

            let appliedCount = Object.keys(objectsMap).length;
            if (appliedCount === 0) {
                editor.showMsg('error', editor.lang('track-no-data'));
                return;
            }

            editor.modelManager.addModelTrackData(objectsMap);

            if (appliedCount < toIds.length) {
                editor.showMsg(
                    'warning',
                    editor.lang('track-partial', { n: appliedCount, m: toIds.length }),
                );
            } else {
                editor.showMsg('success', editor.lang('track-ok'));
            }
            onComplete && onComplete();
        } catch (e: any) {
            editor.showMsg('error', editor.lang('track-error'));
        } finally {
            editor.showLoading(false);
        }
    }
    // offline relabel-only track association: over already-detected boxes,
    // reassign trackId/trackName so the same physical object keeps a consistent
    // id across frames. NEVER create/delete/move/resize boxes — only relabel.
    // - inputScope: 'all' (every box) | 'model' (sourceType === MODEL only)
    // - range: 'all' (whole sequence) | 'fromCurrent' (current frame -> end)
    // Multi-frame tracks (a trackId present in >=2 frames of the scanned range)
    // are anchors and never touched; association acts only on "dangling" boxes
    // (trackId present in exactly 1 frame of the range). Matching is greedy 1:1
    // per frame by BEV (x,y) center distance within a growing gate, same
    // classType only; size/heading are not used. Constant-velocity prediction
    // feeds the gate cost only (no fallback boxes are synthesized).
    trackConnect(option?: {
        inputScope?: 'all' | 'model';
        range?: 'all' | 'fromCurrent';
        k?: number;
    }) {
        let editor = this.editor;
        if (!editor.state.isSeriesFrame) return;

        let { frameIndex, frames, config } = editor.state;
        let inputScope = option?.inputScope ?? config.trackAssocInputScope ?? 'all';
        let range = option?.range ?? config.trackAssocRange ?? 'all';
        let K = Math.max(0, Math.round(option?.k ?? config.trackAssocK ?? 5));
        let baseGate = config.trackAssocGate ?? 2.0;
        // mirror app.py TRACK gate growth/ceiling: gate widens 50% per miss, capped at 4m
        const GATE_GROWTH = 0.5;
        const gateMax = Math.max(baseGate, 4.0);
        const gateFor = (miss: number) => Math.min(baseGate * (1 + GATE_GROWTH * miss), gateMax);

        let startIndex = range === 'fromCurrent' ? frameIndex : 0;
        let rangeFrames = frames.slice(startIndex);
        if (rangeFrames.length === 0) return;

        const isModel = (obj: Box) =>
            (obj.userData as IUserData).sourceType === SourceType.MODEL;
        const inScope = (obj: Box) => (inputScope === 'model' ? isModel(obj) : true);

        // per-frame box lists (only 3D boxes, visible) within the scanned range
        let frameBoxes: Box[][] = rangeFrames.map((frame) => {
            let objects = this.getFrameObject(frame.id) || [];
            return objects.filter(
                (e) => e instanceof Box && !e.userData.invisibleFlag,
            ) as Box[];
        });

        // trackId -> count of frames it appears in (within the scanned range).
        // >=2 frames => multi-frame anchor (preserve). ==1 => dangling candidate.
        let trackFrameCount: Record<string, number> = {};
        frameBoxes.forEach((boxes) => {
            let seen: Record<string, boolean> = {};
            boxes.forEach((box) => {
                let trackId = (box.userData as IUserData).trackId;
                if (!trackId || seen[trackId]) return;
                seen[trackId] = true;
                trackFrameCount[trackId] = (trackFrameCount[trackId] || 0) + 1;
            });
        });

        const isDangling = (box: Box) => {
            let trackId = (box.userData as IUserData).trackId;
            return (
                !!trackId &&
                trackFrameCount[trackId] === 1 &&
                inScope(box)
            );
        };

        interface IActiveTrack {
            trackId: string;
            trackName: string;
            classType: string;
            lastPos: THREE.Vector2; // last matched center (x,y)
            vel: THREE.Vector2; // constant-velocity estimate
            miss: number; // consecutive unmatched frames
            dead: boolean; // deactivated after >K consecutive misses
        }

        let activeTracks: IActiveTrack[] = [];
        // relabels: object -> { trackId, trackName } to apply (only where changed)
        let relabelObjects: AnnotateObject[] = [];
        let relabelData: IUserData[] = [];
        const queueRelabel = (box: Box, trackId: string, trackName: string) => {
            let userData = box.userData as IUserData;
            if (userData.trackId === trackId && userData.trackName === trackName) return;
            relabelObjects.push(box);
            relabelData.push({ trackId, trackName });
        };

        rangeFrames.forEach((frame, fi) => {
            let dangling = frameBoxes[fi].filter(isDangling);

            // advance every active track's prediction once per frame
            let predicted = activeTracks.map((t) =>
                t.lastPos.clone().add(t.vel),
            );

            if (dangling.length > 0 && activeTracks.length > 0) {
                // greedy 1:1 by BEV distance, same classType, within growing gate
                interface IPair {
                    dist: number;
                    ti: number; // active track index
                    di: number; // dangling box index
                }
                let pairs: IPair[] = [];
                activeTracks.forEach((track, ti) => {
                    let gate = gateFor(track.miss);
                    let pred = predicted[ti];
                    dangling.forEach((box, di) => {
                        if ((box.userData as IUserData).classType !== track.classType)
                            return;
                        let dist = Math.hypot(
                            pred.x - box.position.x,
                            pred.y - box.position.y,
                        );
                        if (dist <= gate) pairs.push({ dist, ti, di });
                    });
                });
                pairs.sort((a, b) => a.dist - b.dist);

                let usedTrack: Record<number, boolean> = {};
                let usedBox: Record<number, boolean> = {};
                pairs.forEach(({ ti, di }) => {
                    if (usedTrack[ti] || usedBox[di]) return;
                    usedTrack[ti] = true;
                    usedBox[di] = true;
                    let track = activeTracks[ti];
                    let box = dangling[di];
                    queueRelabel(box, track.trackId, track.trackName);
                    let newPos = new THREE.Vector2(box.position.x, box.position.y);
                    track.vel = newPos.clone().sub(track.lastPos);
                    track.lastPos = newPos;
                    track.miss = 0;
                });

                // unmatched active tracks accrue a miss; deactivate after >K misses
                activeTracks.forEach((track, ti) => {
                    if (usedTrack[ti]) return;
                    track.miss += 1;
                    track.lastPos = predicted[ti];
                    if (track.miss > K) track.dead = true;
                });

                // unmatched dangling boxes seed new tracks (own existing id)
                dangling.forEach((box, di) => {
                    if (usedBox[di]) return;
                    let userData = box.userData as IUserData;
                    activeTracks.push({
                        trackId: userData.trackId || '',
                        trackName: userData.trackName || '',
                        classType: userData.classType || '',
                        lastPos: new THREE.Vector2(box.position.x, box.position.y),
                        vel: new THREE.Vector2(0, 0),
                        miss: 0,
                        dead: false,
                    });
                });
            } else {
                // no matching possible this frame: age active tracks, seed any dangling
                activeTracks.forEach((track, ti) => {
                    track.miss += 1;
                    track.lastPos = predicted[ti];
                    if (track.miss > K) track.dead = true;
                });
                dangling.forEach((box) => {
                    let userData = box.userData as IUserData;
                    activeTracks.push({
                        trackId: userData.trackId || '',
                        trackName: userData.trackName || '',
                        classType: userData.classType || '',
                        lastPos: new THREE.Vector2(box.position.x, box.position.y),
                        vel: new THREE.Vector2(0, 0),
                        miss: 0,
                        dead: false,
                    });
                });
            }

            activeTracks = activeTracks.filter((t) => !t.dead);
        });

        if (relabelObjects.length === 0) {
            editor.showMsg('warning', editor.lang('track-connect-none'));
            return;
        }

        // mark every touched frame dirty (setAnnotatesUserData marks the owning
        // frame, but be explicit for frames whose boxes carry no .frame backref)
        let touchedFrames = new Set<IFrame>();
        relabelObjects.forEach((obj) => {
            let frame = (obj as any).frame as IFrame;
            if (frame) touchedFrames.add(frame);
        });

        editor.cmdManager.withGroup(() => {
            editor.cmdManager.execute('update-object-user-data', {
                objects: relabelObjects,
                data: relabelData,
            });
        });

        touchedFrames.forEach((frame) => (frame.needSave = true));

        editor.showMsg(
            'success',
            editor.lang('track-connect-ok', { n: relabelObjects.length }),
        );
    }
    copyForward() {
        return this.track({
            direction: 'FORWARD',
            object: 'select',
            method: 'copy',
            frameN: 1,
        });
    }
    copyBackWard() {
        return this.track({
            direction: 'BACKWARD',
            object: 'select',
            method: 'copy',
            frameN: 1,
        });
    }
    copyAllForward() {
        return this.track({
            direction: 'FORWARD',
            object: 'all',
            method: 'copy',
            frameN: 1,
        });
    }
    trackForward() {
        return this.track({
            direction: 'FORWARD',
            object: 'select',
            method: 'model',
            frameN: this.editor.state.config.trackFrameN,
        });
    }
    trackBackward() {
        return this.track({
            direction: 'BACKWARD',
            object: 'select',
            method: 'model',
            frameN: this.editor.state.config.trackFrameN,
        });
    }
    trackAllForward() {
        return this.track({
            direction: 'FORWARD',
            object: 'all',
            method: 'model',
            frameN: this.editor.state.config.trackFrameN,
        });
    }
    async track(option: {
        method: 'copy' | 'model';
        object: 'select' | 'all';
        direction: 'BACKWARD' | 'FORWARD';
        frameN: number;
    }) {
        let editor = this.editor;
        let { frameIndex, frames } = editor.state;
        let curId = frames[frameIndex].id;

        const getToDataId = function getToDataId() {
            let ids = [] as string[];
            let forward = option.direction === 'FORWARD' ? 1 : -1;
            let frameN = option.frameN;

            if (frameN > 0)
                for (let i = 1; i <= frameN; i++) {
                    let frame = frames[frameIndex + forward * i];
                    if (frame) {
                        ids.push(frame.id);
                    }
                }
            return ids;
        };
        const getObjects = function getObjects() {
            let dataId = frames[frameIndex].id;
            let objects = editor.dataManager.getFrameObject(dataId) || [];

            if (option.object === 'select') {
                objects = editor.pc.selection;
            }

            objects = objects.filter((object) => {
                return object instanceof Box && !object.userData.invisibleFlag;
            });

            return objects as Box[];
        };
        let ids = getToDataId();
        if (ids.length === 0) {
            // editor.showMsg('warning', props.state.$$('warnEmptyTarget'));
            return;
        }

        let objects = getObjects();
        if (objects.length === 0) {
            editor.showMsg('warning', editor.lang('track-no-source'));
            return;
        }

        if (option.method === 'copy') {
            utils.copyData(editor, curId, ids, objects);
            editor.showMsg('success', editor.lang('copy-ok'));
            this.gotoNext(ids[0]);
        } else {
            await this.modelTrack(ids, objects, option.direction);
        }
    }
    gotoNext(dataId: string) {
        let { frames } = this.editor.state;
        let index = frames.findIndex((e) => e.id === dataId);
        // index = Math.max(0, Math.min(editor.state.frames.length-1, index))
        if (index < 0) return;
        this.editor.loadFrame(index);
        // this.editor.dispatchEvent({ type: EditorEvent.UPDATE_TIME_LINE });
    }
    async modelTrack(
        toIds: string[],
        objects: AnnotateObject[],
        direction: 'BACKWARD' | 'FORWARD',
    ) {
        let editor = this.editor;
        let { frameIndex, frames } = editor.state;
        let dataInfo = frames[frameIndex];
        let curId = dataInfo.id;

        // previous-frame positions of the same tracks give the server an initial
        // velocity for the constant-velocity fallback (null -> stationary).
        // "previous" is relative to propagation order: when tracking BACKWARD,
        // the reference is the next frame in time
        let prevMap = {} as Record<string, Box>;
        let prevFrame = frames[frameIndex + (direction === 'BACKWARD' ? 1 : -1)];
        if (prevFrame) {
            (this.getFrameObject(prevFrame.id) || []).forEach((e) => {
                if (e instanceof Box && !e.userData.invisibleFlag) {
                    prevMap[e.userData.trackId] = e as Box;
                }
            });
        }

        let trackIdName = {} as Record<string, string>;
        let targetObjects = [] as any[];
        objects.forEach((object) => {
            if (object instanceof Box) {
                let userData = object.userData as IUserData;
                let { position, scale, rotation } = object;

                if (!userData.trackId) {
                    userData.trackId = editor.createTrackId();
                }

                trackIdName[userData.trackId] = userData.trackName || '';

                let prev = prevMap[userData.trackId];
                targetObjects.push({
                    uuid: object.uuid,
                    trackingId: userData.trackId,
                    objType: '3d',
                    modelClass: userData.modelClass || null,
                    confidence: userData.confidence || null,
                    center3D: { x: position.x, y: position.y, z: position.z },
                    rotation3D: { x: rotation.x, y: rotation.y, z: rotation.z },
                    size3D: { x: scale.x, y: scale.y, z: scale.z },
                    prevCenter3D: prev
                        ? { x: prev.position.x, y: prev.position.y, z: prev.position.z }
                        : null,
                });
            }
        });

        await this.runModelTrack(curId, toIds, direction as any, targetObjects, trackIdName, () => {
            this.gotoNext(toIds[0]);
        });
    }
}
