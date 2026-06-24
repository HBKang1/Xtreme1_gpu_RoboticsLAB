import { Box } from 'pc-render';
import { define } from '../define';
import Editor from '../../../Editor';
import { isSuspicious } from '../../../config/validation';

/**
 * #1 Confidence Review Queue — jump selection to the next suspicious box.
 *
 * "Suspicious" is the same client-side predicate used by the panel/timeline
 * (fallback 0.1 OR bad size OR overlap), evaluated from box geometry already on
 * every loaded box (see config/validation.ts) — no serving flag, no DB round-trip.
 *
 * Scan order: starting just after the current selection (or the start of the
 * current frame if nothing is selected), walk the current frame's remaining boxes,
 * then each subsequent frame, wrapping back to frame 0 and stopping at the start
 * box. The first suspicious box found becomes the selection (loading its frame
 * first if it lives in a different frame).
 *
 * Same-frame neighbors for the overlap rule come from the loaded frame's objects
 * (DataManager.getFrameObject(frameId)).
 */
export const jumpToNextSuspicious = define({
    valid(editor: Editor) {
        return editor.state.frames.length > 0;
    },
    async execute(editor: Editor) {
        const { frames, frameIndex } = editor.state;
        const frameCount = frames.length;
        if (frameCount === 0) return;

        // 3D boxes only (geometry-bearing). Filter helper per frame.
        const frameBoxes = (fIndex: number): Box[] => {
            const frame = frames[fIndex];
            if (!frame) return [];
            const objects = editor.dataManager.getFrameObject(frame.id) || [];
            return objects.filter((o) => o instanceof Box) as Box[];
        };

        // Where are we starting from? If a box is selected and it's in the current
        // frame, start scanning right after it; otherwise from the frame start.
        const selected = editor.pc.selection.find((o) => o instanceof Box) as Box | undefined;
        const curBoxes = frameBoxes(frameIndex);
        let startBoxOffset = 0;
        if (selected) {
            const idx = curBoxes.indexOf(selected);
            if (idx >= 0) startBoxOffset = idx + 1;
        }

        // Walk current frame (from startBoxOffset), then each following frame,
        // wrapping around. Total frames scanned = frameCount; the starting frame is
        // scanned twice (tail then head) to cover boxes before the selection.
        for (let step = 0; step <= frameCount; step++) {
            const fIndex = (frameIndex + step) % frameCount;
            const boxes = step === 0 ? curBoxes : frameBoxes(fIndex);
            const neighbors = boxes;

            // On the first frame, skip boxes at/before the selection. On the wrap-around
            // pass over the start frame (step === frameCount), only consider boxes up to
            // the selection so we don't loop forever past it.
            let from = step === 0 ? startBoxOffset : 0;
            let to = step === frameCount ? startBoxOffset : boxes.length;

            for (let i = from; i < to; i++) {
                const box = boxes[i];
                if (box === selected) continue;
                if (isSuspicious(box as any, neighbors as any)) {
                    if (fIndex !== frameIndex) {
                        await editor.loadFrame(fIndex);
                    }
                    editor.selectObject(box as any);
                    return;
                }
            }
        }

        editor.showMsg('success', 'No suspicious box found');
    },
});
