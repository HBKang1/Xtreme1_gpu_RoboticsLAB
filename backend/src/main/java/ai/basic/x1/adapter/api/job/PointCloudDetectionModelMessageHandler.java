package ai.basic.x1.adapter.api.job;

import ai.basic.x1.adapter.api.job.converter.ModelResultConverter;
import ai.basic.x1.adapter.api.job.converter.PointCloudDetectionModelReqConverter;
import ai.basic.x1.adapter.dto.ApiResult;
import ai.basic.x1.adapter.port.dao.mybatis.model.DataAnnotationObject;
import ai.basic.x1.adapter.port.dao.mybatis.model.ModelClass;
import ai.basic.x1.adapter.port.dao.mybatis.model.ModelDatasetResult;
import ai.basic.x1.adapter.port.dao.mybatis.model.ModelRunRecord;
import ai.basic.x1.adapter.port.rpc.PointCloudDetectionModelHttpCaller;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudDetectionMetricsReqDTO;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudDetectionObject;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudDetectionRespDTO;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudSequenceRespDTO;
import ai.basic.x1.entity.*;
import ai.basic.x1.entity.enums.DataAnnotationObjectSourceTypeEnum;
import ai.basic.x1.entity.enums.ModelCodeEnum;
import ai.basic.x1.usecase.DataInfoUseCase;
import ai.basic.x1.usecase.ModelUseCase;
import ai.basic.x1.usecase.exception.UsecaseCode;
import ai.basic.x1.util.Constants;
import ai.basic.x1.util.DefaultConverter;
import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.ObjectUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * @author andy
 */
@Slf4j
public class PointCloudDetectionModelMessageHandler extends AbstractModelMessageHandler<List<PointCloudDetectionRespDTO>> {

    @Autowired
    private PointCloudDetectionModelHttpCaller preLabelModelHttpCaller;

    @Autowired
    private ModelUseCase modelUseCase;

    @Autowired
    private DataInfoUseCase dataInfoUseCase;

    @Autowired
    private DataAnnotationObjectModelWriter dataAnnotationObjectModelWriter;

    @Value("${pointCloud.resultEvaluate.url}")
    private String resultEvaluateUrl;

    private static final Integer SEQUENCE_RETRY_COUNT = 3;


    @Override
    public ModelTaskInfoBO modelRun(ModelMessageBO modelMessageBO) {
        ApiResult<List<PointCloudDetectionRespDTO>> apiResult = getRetryAbleApiResult(modelMessageBO);
        Map<String, ModelClass> modelClassMap = modelUseCase.getModelClassMapByModelId(modelMessageBO.getModelId());
        PointCloudDetectionObjectBO preLabelModelObjectBO = ModelResultConverter.preModelResultConverter(apiResult,
                JSONUtil.toBean(modelMessageBO.getResultFilterParam(), PointCloudDetectionParamBO.class), modelClassMap);
        return preLabelModelObjectBO;
    }

    @Override
    ApiResult<List<PointCloudDetectionRespDTO>> callRemoteService(ModelMessageBO modelMessageBO) {
        ApiResult<List<PointCloudDetectionRespDTO>> listApiResult = preLabelModelHttpCaller.callPreLabelModel(PointCloudDetectionModelReqConverter.buildRequestParam(modelMessageBO), modelMessageBO.getUrl());
        return listApiResult;
    }

    @Override
    public void syncModelAnnotationResult(ModelTaskInfoBO modelTaskInfo, ModelMessageBO modelMessage) {
        var modelResult = (PointCloudDetectionObjectBO) modelTaskInfo;
        if (CollUtil.isNotEmpty(modelResult.getObjects())) {
            var lambdaQueryWrapper = Wrappers.lambdaQuery(ModelRunRecord.class);
            lambdaQueryWrapper.eq(ModelRunRecord::getModelSerialNo,modelMessage.getModelSerialNo());
            lambdaQueryWrapper.last("limit 1");
            var modelRunRecord = modelRunRecordDAO.getOne(lambdaQueryWrapper);
            var dataAnnotationObjectBOList = new ArrayList<DataAnnotationObjectBO>(modelResult.getObjects().size());
            modelResult.getObjects().forEach(o -> {
                var dataAnnotationObjectBO = DataAnnotationObjectBO.builder()
                        .datasetId(modelMessage.getDatasetId()).dataId(modelResult.getDataId()).classAttributes(JSONUtil.parseObj(o))
                        .sourceType(DataAnnotationObjectSourceTypeEnum.MODEL).sourceId(modelRunRecord.getId()).build();
                dataAnnotationObjectBOList.add(dataAnnotationObjectBO);
            });
            dataAnnotationObjectDAO.saveBatch(DefaultConverter.convert(dataAnnotationObjectBOList, DataAnnotationObject.class));
        }
    }


    @Override
    public void assembleCalculateMetricsData(List<ModelDatasetResult> modelDatasetResults, List<DataAnnotationObject> dataAnnotationObjectList,
                                             String groundTruthFilePath, String modelRunFilePath) {
        if (CollUtil.isEmpty(modelDatasetResults)) {
            return;
        }
        var dataAnnotationObjectMap = dataAnnotationObjectList.stream().collect(Collectors.groupingBy(DataAnnotationObject::getDataId));
        modelDatasetResults.forEach(modelDatasetResult -> {
            var isSuccess = modelDatasetResult.getIsSuccess();
            if (!isSuccess) {
                return;
            }
            var modelResult = modelDatasetResult.getModelResult();
            var dataId = modelDatasetResult.getDataId();
            var dataAnnotationObjects = dataAnnotationObjectMap.get(modelDatasetResult.getDataId());
            var groundTruthObjects = new ArrayList<PointCloudDetectionObject>();
            if (CollUtil.isEmpty(dataAnnotationObjects)) {
                return;
            }
            dataAnnotationObjects.forEach(dataAnnotationObject -> {
                var pointCloudDetectionObject = new PointCloudDetectionObject();
                var objectBO = DefaultConverter.convert(dataAnnotationObject.getClassAttributes().get("contour"), ObjectBO.class);
                assembleObject(objectBO, pointCloudDetectionObject);
                groundTruthObjects.add(pointCloudDetectionObject);
            });
            var modelRunObjects = new ArrayList<PointCloudDetectionObject>();
            var pointCloudDetectionObjectBO = DefaultConverter.convert(modelResult, PointCloudDetectionObjectBO.class);
            // Tracking scene rows carry no per-frame objects in model_result
            // (D4: per-dataId confidence metrics are skipped for tracking).
            if (ObjectUtil.isNull(pointCloudDetectionObjectBO) || CollUtil.isEmpty(pointCloudDetectionObjectBO.getObjects())) {
                return;
            }
            pointCloudDetectionObjectBO.getObjects().forEach(objectBO -> {
                var pointCloudDetectionObject = new PointCloudDetectionObject();
                var confidence = objectBO.getConfidence();
                assembleObject(objectBO, pointCloudDetectionObject);
                pointCloudDetectionObject.setConfidence(confidence);
                pointCloudDetectionObject.setLabel(objectBO.getModelClass());
                modelRunObjects.add(pointCloudDetectionObject);
            });
            var groundTruthObject = PointCloudDetectionMetricsReqDTO.builder().id(dataId).objects(groundTruthObjects).build();
            var modelRunObject = PointCloudDetectionMetricsReqDTO.builder().id(dataId).objects(modelRunObjects).build();
            FileUtil.appendUtf8String(StrUtil.removeAllLineBreaks(JSONUtil.toJsonStr(groundTruthObject)), groundTruthFilePath);
            FileUtil.appendUtf8String("\n", groundTruthFilePath);
            FileUtil.appendUtf8String(StrUtil.removeAllLineBreaks(JSONUtil.toJsonStr(modelRunObject)), modelRunFilePath);
            FileUtil.appendUtf8String("\n", modelRunFilePath);
        });


    }

    private void assembleObject(ObjectBO objectBO, PointCloudDetectionObject pointCloudDetectionObject) {
        var size3D = objectBO.getSize3D();
        var center3D = objectBO.getCenter3D();
        var rotation3D = objectBO.getRotation3D();
        pointCloudDetectionObject.setX(center3D.getX());
        pointCloudDetectionObject.setY(center3D.getY());
        pointCloudDetectionObject.setZ(center3D.getY());
        pointCloudDetectionObject.setDx(size3D.getX());
        pointCloudDetectionObject.setDy(size3D.getY());
        pointCloudDetectionObject.setDz(size3D.getZ());
        pointCloudDetectionObject.setRotX(rotation3D.getX());
        pointCloudDetectionObject.setRotY(rotation3D.getY());
        pointCloudDetectionObject.setRotZ(rotation3D.getZ());
    }

    @Override
    public String getResultEvaluateUrl() {
        return resultEvaluateUrl;
    }

    @Override
    public ModelCodeEnum getModelCodeEnum() {
        return ModelCodeEnum.LIDAR_DETECTION;
    }

    /**
     * Per-scene detection+tracking run. Splits the scene's ordered frames into
     * chunks, calls the sequence endpoint sequentially carrying trackStates
     * forward for cross-chunk trackId continuity, maps the call-local
     * trackingId to a global trackId/trackName, and persists each frame to
     * data_annotation_object (source_type=MODEL) via an idempotent
     * delete-then-insert.
     *
     * <p>Self-finalize is MANDATORY (S0.3): on permanent serving failure the
     * scene is marked failed and progress advanced, and this method returns true
     * so the message is acked and the run finalizes (SUCCESS_WITH_ERROR) instead
     * of hanging RUNNING forever.
     */
    @Override
    protected boolean handleSceneModelRun(ModelMessageBO modelMessageBO) {
        var sceneId = modelMessageBO.getSceneId();
        try {
            var modelRunRecord = getModelRunRecord(modelMessageBO.getModelSerialNo());
            if (ObjectUtil.isNull(modelRunRecord)) {
                log.error("tracking scene {}: model run record not found for serialNo {}",
                        sceneId, modelMessageBO.getModelSerialNo());
                finalizeSceneFailure(modelMessageBO, "model run record not found");
                return true;
            }
            var sourceId = modelRunRecord.getId();
            var modelClassMap = modelUseCase.getModelClassMapByModelId(modelMessageBO.getModelId());

            // ordered frame DataInfoBOs (preserve the message's frame order)
            var orderedFrames = fetchOrderedFrames(modelMessageBO.getSceneDataIds());
            if (CollUtil.isEmpty(orderedFrames)) {
                log.warn("tracking scene {}: no frames resolved, finalizing success (empty)", sceneId);
                finalizeSceneSuccess(modelMessageBO);
                return true;
            }

            var sequenceUrl = buildSequenceUrl(modelMessageBO.getUrl());

            List<PointCloudSequenceRespDTO.TrackState> seedTrackStates = null;
            for (var chunk : CollUtil.split(orderedFrames, Constants.TRACKING_CHUNK_SIZE)) {
                var apiResult = getRetrySequenceApiResult(chunk, seedTrackStates, sequenceUrl);
                if (apiResult == null || apiResult.getCode() != UsecaseCode.OK || ObjectUtil.isNull(apiResult.getData())) {
                    var msg = apiResult == null ? "sequence service is busy" : apiResult.getMessage();
                    log.error("tracking scene {}: chunk failed permanently: {}", sceneId, msg);
                    finalizeSceneFailure(modelMessageBO, StrUtil.isEmpty(msg) ? "sequence run error" : msg);
                    return true;
                }
                persistChunk(apiResult.getData(), modelRunRecord, sceneId, sourceId, modelClassMap);
                seedTrackStates = apiResult.getData().getTrackStates();
            }
            finalizeSceneSuccess(modelMessageBO);
            return true;
        } catch (Exception e) {
            // never let a scene failure escape as false/exception (S0.3 / R7)
            log.error("tracking scene {} unexpected error, self-finalizing as failure", sceneId, e);
            try {
                finalizeSceneFailure(modelMessageBO, "tracking scene error");
            } catch (Exception inner) {
                log.error("tracking scene {} finalize failure also failed", sceneId, inner);
            }
            return true;
        }
    }

    private ModelRunRecord getModelRunRecord(Long modelSerialNo) {
        var lambdaQueryWrapper = Wrappers.lambdaQuery(ModelRunRecord.class);
        lambdaQueryWrapper.eq(ModelRunRecord::getModelSerialNo, modelSerialNo);
        lambdaQueryWrapper.last("limit 1");
        return modelRunRecordDAO.getOne(lambdaQueryWrapper);
    }

    /**
     * Resolve full DataInfoBOs (with point cloud content) for the ordered scene
     * dataIds, preserving the supplied order.
     */
    private List<DataInfoBO> fetchOrderedFrames(List<Long> orderedDataIds) {
        if (CollUtil.isEmpty(orderedDataIds)) {
            return new ArrayList<>(0);
        }
        var dataInfoList = dataInfoUseCase.listByIds(orderedDataIds, true);
        var byId = dataInfoList.stream().collect(Collectors.toMap(DataInfoBO::getId, d -> d, (a, b) -> a));
        var ordered = new ArrayList<DataInfoBO>(orderedDataIds.size());
        orderedDataIds.forEach(id -> {
            var d = byId.get(id);
            if (ObjectUtil.isNotNull(d)) {
                ordered.add(d);
            }
        });
        return ordered;
    }

    /**
     * Derive the sequence endpoint url from the model's detection url. The model
     * url points at the serving container's recognition path
     * ({@code .../pointCloud/recognition}); the sequence endpoint shares the same
     * base ({@code .../pointCloud/sequence}).
     */
    private String buildSequenceUrl(String modelUrl) {
        return StrUtil.nullToEmpty(modelUrl)
                .replace(Constants.MODEL_RECOGNITION_PATH, Constants.MODEL_SEQUENCE_PATH);
    }

    private ApiResult<PointCloudSequenceRespDTO> getRetrySequenceApiResult(List<DataInfoBO> chunk,
                                                                           List<PointCloudSequenceRespDTO.TrackState> seedTrackStates,
                                                                           String url) {
        var reqDTO = PointCloudDetectionModelReqConverter.buildSequenceRequestParam(chunk, seedTrackStates);
        ApiResult<PointCloudSequenceRespDTO> apiResult = null;
        int count = 0;
        while (count <= SEQUENCE_RETRY_COUNT && ObjectUtil.isNull(apiResult)) {
            try {
                apiResult = preLabelModelHttpCaller.callSequenceModel(reqDTO, url);
                break;
            } catch (Throwable throwable) {
                log.error("call sequence service is error", throwable);
            }
            count++;
        }
        return apiResult;
    }

    /**
     * Map a chunk's per-frame objects to global trackId/trackName and persist
     * each frame via the idempotent delete-then-insert writer.
     */
    private void persistChunk(PointCloudSequenceRespDTO chunkResult, ModelRunRecord modelRunRecord,
                              Long sceneId, Long sourceId, Map<String, ModelClass> modelClassMap) {
        if (CollUtil.isEmpty(chunkResult.getFrames())) {
            return;
        }
        var modelSerialNo = modelRunRecord.getModelSerialNo();
        chunkResult.getFrames().forEach(frame -> {
            var objectBOs = new ArrayList<DataAnnotationObjectBO>(
                    frame.getObjects() == null ? 0 : frame.getObjects().size());
            if (CollUtil.isNotEmpty(frame.getObjects())) {
                frame.getObjects().forEach(obj -> {
                    var localId = obj.getTrackingId();
                    var className = resolveClassName(obj.getLabel(), modelClassMap);
                    var trackId = String.format("m%d-s%d-%d", modelSerialNo, sceneId, localId);
                    var trackName = String.format("%s-%d", StrUtil.nullToEmpty(className), localId);
                    var classAttributes = buildClassAttributes(obj, className, trackId, trackName);
                    objectBOs.add(DataAnnotationObjectBO.builder()
                            .datasetId(modelRunRecord.getDatasetId())
                            .dataId(frame.getId())
                            .classAttributes(classAttributes)
                            .sourceType(DataAnnotationObjectSourceTypeEnum.MODEL)
                            .sourceId(sourceId)
                            .build());
                });
            }
            // delete-then-insert per frame (idempotent, AC9). Empty frames are
            // cleared so a re-run does not leave stale rows.
            dataAnnotationObjectModelWriter.replaceFrameObjects(frame.getId(), sourceId, objectBOs);
        });
    }

    private String resolveClassName(String label, Map<String, ModelClass> modelClassMap) {
        if (StrUtil.isEmpty(label)) {
            return null;
        }
        var modelClass = modelClassMap.get(label);
        return ObjectUtil.isNotNull(modelClass) ? modelClass.getName() : label;
    }

    /**
     * Build the object JSON (class_attributes) using the flat geometry builders
     * reused from the detection path (D5) and add trackId/trackName at the JSON
     * root so pc-tool reads them via class_attributes->>'$.trackId'.
     */
    private JSONObject buildClassAttributes(PointCloudSequenceRespDTO.SequenceObject obj, String className,
                                            String trackId, String trackName) {
        var detectionObject = PointCloudDetectionObject.builder()
                .label(obj.getLabel())
                .confidence(obj.getConfidence())
                .x(obj.getX()).y(obj.getY()).z(obj.getZ())
                .dx(obj.getDx()).dy(obj.getDy()).dz(obj.getDz())
                .rotX(obj.getRotX()).rotY(obj.getRotY()).rotZ(obj.getRotZ())
                .build();
        var objectBO = ObjectBO.builder()
                .type("3D_BOX")
                .confidence(obj.getConfidence())
                .modelClass(className)
                .center3D(ModelResultConverter.buildCenter3D(detectionObject))
                .rotation3D(ModelResultConverter.buildRotation3D(detectionObject))
                .size3D(ModelResultConverter.buildSize3D(detectionObject))
                .build();
        var json = JSONUtil.parseObj(objectBO);
        json.set("trackId", trackId);
        json.set("trackName", trackName);
        return json;
    }


}
