package ai.basic.x1.adapter.port.rpc.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * Request body for the detection-driven sequence detection+tracking endpoint
 * ({@code /pointCloud/sequence}). Sent server-to-server (chunked) by the Java
 * backend. The serving side downloads each {@code pointCloudUrl} itself.
 *
 * @author tracking-pipeline
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class PointCloudSequenceReqDTO {

    /**
     * Ordered frames (name ASC, id ASC) of the chunk.
     */
    private List<Frame> frames;

    /**
     * Floor for newly-allocated trackingIds in this chunk. The serving side
     * must not assign a new id < startId, preventing cross-chunk id reuse when
     * a track terminates and its localId would otherwise be recycled.
     */
    private Integer startId;

    /**
     * Active tracks carried over from the previous chunk (for trackId
     * continuity). Null/empty for the first chunk of a scene.
     */
    private List<SeedObject> seedObjects;

    /**
     * keep_z / keep_rotation flags. Detection is truth -> both default false.
     */
    private Keep keep;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Frame {
        private Long id;
        private String pointCloudUrl;
    }

    /**
     * Flat geometry seed (mirrors the serving {@code trackStates} output shape)
     * so it can be fed straight back as the next chunk's seed.
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class SeedObject {
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

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Keep {
        private Boolean z;
        private Boolean rotation;
    }
}
