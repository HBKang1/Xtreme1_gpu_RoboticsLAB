import { AttrType } from 'pc-editor';
import { AnnotateType } from 'pc-render';

export interface IItem {
    id: string;
    key: string;
    name: string;
    isTrackItem: boolean;
    annotateType: '3d' | 'rect' | 'box2d' | '';
    visible: boolean;
    data: IItem[];
    isModel: boolean;
    attrLabel?: string;
    hasAnnotation?: boolean;
    invisible?: boolean;
    active: string[];
    // #1 Confidence Review Queue: model confidence + client-side suspicious predicate.
    // undefined confidence sorts last (treated as no model signal).
    confidence?: number;
    suspicious?: boolean;
    // #1: hidden by the "suspicious-only" panel filter (true => not rendered).
    filtered?: boolean;
}

export interface IClass {
    key: string;
    isModel: boolean;
    classId: string;
    classType: string;
    className: string;
    data: IItem[];
    color: string;
    // bgColor: string;
    visible: boolean;
    // #1: collapsed by the "suspicious-only" panel filter (no suspicious track inside).
    filtered?: boolean;
    // active: string[];
}

export interface IClassify {
    key: string;
    name: string;
    visible: boolean;
    data: IClass[];
    objectN: number;
    active: string[];
    activeClass: string[];
}

export interface IState {
    // activeClass: string[];
    // activeTrack: string[];
    selectMap: Record<string, true>;
    // selectId: string;
    trackId: string;
    classType: string;
    objectN: number;
    list: IClassify[];
    showAttr: boolean;
    globalTrackMap: Record<string, IItem>;
    globalClassifyMap: Record<string, IClassify>;
    globalClassMap: Record<string, IClass>;
    expandAll: boolean;
    // #1 Confidence Review Queue: panel-local "suspicious-only" filter.
    // Display state only — no persisted reviewed-state (spec: #1 stores nothing).
    showSuspiciousOnly: boolean;
    // noClassList: IInstanceList;
}

export interface IAttrItem {
    type: AttrType;
    name: string;
    options: { value: any; label: string }[];
    value: any;
}
