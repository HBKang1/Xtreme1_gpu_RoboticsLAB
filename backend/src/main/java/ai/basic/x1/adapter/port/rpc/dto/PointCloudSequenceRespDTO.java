package ai.basic.x1.adapter.port.rpc.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * Response payload (the {@code data} field of the ApiResult envelope) returned
 * by the {@code /pointCloud/sequence} endpoint.
 *
 * @author tracking-pipeline
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PointCloudSequenceRespDTO {

    /**
     * Per-frame detected+tracked objects, in the same order as the request.
     */
    private List<FrameResult> frames;

    /**
     * Active tracks at the last processed frame -> feed as the next chunk's
     * {@code seedObjects} to keep trackIds continuous across chunks.
     */
    private List<TrackState> trackStates;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class FrameResult {
        private Long id;
        private List<SequenceObject> objects;
    }

    /**
     * Flat geometry object (mirrors the {@code /pointCloud/recognition} shape)
     * plus the per-call trackingId.
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SequenceObject {
        private Integer trackingId;
        private String label;
        private BigDecimal confidence;
        private BigDecimal x;
        private BigDecimal y;
        private BigDecimal z;
        private BigDecimal dx;
        private BigDecimal dy;
        private BigDecimal dz;
        private BigDecimal rotX;
        private BigDecimal rotY;
        private BigDecimal rotZ;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class TrackState {
        private Integer trackingId;
        private String label;
        private BigDecimal confidence;
        private BigDecimal x;
        private BigDecimal y;
        private BigDecimal z;
        private BigDecimal dx;
        private BigDecimal dy;
        private BigDecimal dz;
        private BigDecimal rotZ;
        private BigDecimal prevX;
        private BigDecimal prevY;
        private BigDecimal prevZ;
    }
}
