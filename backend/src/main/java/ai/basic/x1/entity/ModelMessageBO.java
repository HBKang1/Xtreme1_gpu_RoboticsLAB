package ai.basic.x1.entity;

import ai.basic.x1.entity.enums.ModelCodeEnum;
import cn.hutool.json.JSONObject;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.experimental.SuperBuilder;

import java.util.List;

/**
 * @author fyb
 */
@Data
@SuperBuilder
@NoArgsConstructor
@AllArgsConstructor
public class ModelMessageBO {

    private ModelCodeEnum modelCode;

    private Long datasetId;

    private Long dataId;

    private Long modelId;

    private String modelVersion;

    private Long modelSerialNo;

    private Long createdBy;

    private JSONObject resultFilterParam;

    private String modelRunParam;

    private DataInfoBO dataInfo;

    private String url;

    /**
     * Scene (sequence) id for a tracking run. Null for the regular per-frame
     * detection run. When set, this message represents one whole scene and the
     * handler dispatches the detection+tracking sequence call for it.
     */
    private Long sceneId;

    /**
     * Ordered (name ASC, id ASC) frame dataIds belonging to {@link #sceneId}.
     * The frame point cloud urls are fetched in the handler via DB lookup so the
     * message stays small.
     */
    private List<Long> sceneDataIds;

}
