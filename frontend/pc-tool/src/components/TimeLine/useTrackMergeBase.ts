import { ref } from 'vue';

/**
 * Module-scope singleton ref: persists the merge-base trackId across
 * trackLine re-renders and object selection changes.
 * Shared by all trackLine instances in the same app.
 */
const mergeBaseTrackId = ref('');

export function useTrackMergeBase() {
    return { mergeBaseTrackId };
}
