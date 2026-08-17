package ai.basic.x1.adapter.api.job;

import ai.basic.x1.adapter.api.job.converter.ModelCocoRequestConverter;
import ai.basic.x1.adapter.api.job.converter.ModelCocoResponseConverter;
import ai.basic.x1.adapter.dto.ApiResult;
import ai.basic.x1.adapter.dto.PreModelParamDTO;
import ai.basic.x1.adapter.port.dao.mybatis.model.DataAnnotationObject;
import ai.basic.x1.adapter.port.dao.mybatis.model.ModelDatasetResult;
import ai.basic.x1.adapter.port.dao.mybatis.model.ModelRunRecord;
import ai.basic.x1.adapter.port.rpc.ImageDetectionModelHttpCaller;
import ai.basic.x1.adapter.port.rpc.dto.ImageDetectionMetricsReqDTO;
import ai.basic.x1.adapter.port.rpc.dto.ImageDetectionObject;
import ai.basic.x1.adapter.port.rpc.dto.ImageDetectionRespDTO;
import ai.basic.x1.entity.*;
import ai.basic.x1.entity.enums.DataAnnotationObjectSourceTypeEnum;
import ai.basic.x1.entity.enums.ModelCodeEnum;
import ai.basic.x1.usecase.ModelUseCase;
import ai.basic.x1.usecase.exception.UsecaseCode;
import ai.basic.x1.usecase.exception.UsecaseException;
import ai.basic.x1.util.DefaultConverter;
import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

/**
 * @author Zhujh
 */
@Slf4j
public class ImageDetectionModelHandler extends AbstractModelMessageHandler<ImageDetectionRespDTO> {

    @Autowired
    private ImageDetectionModelHttpCaller modelHttpCaller;

    @Autowired
    private ModelUseCase modelUseCase;

    @Value("${image.resultEvaluate.url}")
    private String resultEvaluateUrl;

    @Override
    public ModelTaskInfoBO modelRun(ModelMessageBO message) {
        log.info("start model run. dataId: {}, modelSerialNo: {}", message.getDataId(),
                message.getModelSerialNo());
        var apiResult = getRetryAbleApiResult(message);
        var systemModelClassMap = modelUseCase.getModelClassMapByModelId(message.getModelId());
        var filterCondition = JSONUtil.toBean(message.getResultFilterParam(),
                PreModelParamDTO.class);
        return ModelCocoResponseConverter.convert(apiResult, systemModelClassMap, filterCondition);
    }

    @Override
    ApiResult<ImageDetectionRespDTO> callRemoteService(ModelMessageBO message) {
        try {
            var apiResult = modelHttpCaller
                    .callPredImageModel(ModelCocoRequestConverter.convert(message), message.getUrl());

            if (CollUtil.isNotEmpty(apiResult.getData())) {
                return new ApiResult<>(apiResult.getCode(), apiResult.getMessage(),
                        apiResult.getData().get(0));
            }
            return new ApiResult<>(apiResult.getCode(), apiResult.getMessage());
        } catch (Exception e) {
            log.error("call image error",e);
            throw new UsecaseException(UsecaseCode.UNKNOWN, e.getMessage());
        }
    }

    @Override
    public void syncModelAnnotationResult(ModelTaskInfoBO modelTaskInfo, ModelMessageBO modelMessage) {
        var modelResult = (ImageDetectionObjectBO) modelTaskInfo;
        if (CollUtil.isNotEmpty(modelResult.getObjects())) {
            var lambdaQueryWrapper = Wrappers.lambdaQuery(ModelRunRecord.class);
            lambdaQueryWrapper.eq(ModelRunRecord::getModelSerialNo,modelMessage.getModelSerialNo());
            lambdaQueryWrapper.last("limit 1");
            var modelRunRecord = modelRunRecordDAO.getOne(lambdaQueryWrapper);
            var dataAnnotationObjectBOList = new ArrayList<DataAnnotationObjectBO>(modelResult.getObjects().size());
            var trackNo = new AtomicInteger(1);
            modelResult.getObjects().forEach(o -> {
                // ObjectBO 를 그대로 직렬화하면 points 가 최상위에 놓여 image-tool 이 읽지 못한다.
                // 툴은 obj.contour.points 를 보고(result-request.convertObject2Annotate), 비어 있으면
                // 그 객체를 조용히 버린다. 신뢰도도 modelConfidence 키에서 읽는다.
                // 포인트 클라우드 결과와 동일한 모양으로 맞춰 저장한다.
                var classAttributes = JSONUtil.createObj()
                        .set("id", IdUtil.fastSimpleUUID())
                        .set("type", o.getType())
                        .set("contour", JSONUtil.createObj().set("points", o.getPoints()))
                        .set("modelClass", o.getModelClass())
                        .set("modelConfidence", o.getConfidence())
                        .set("trackId", IdUtil.fastSimpleUUID())
                        .set("trackName", String.valueOf(trackNo.getAndIncrement()))
                        .set("sourceId", modelRunRecord.getId())
                        .set("sourceType", DataAnnotationObjectSourceTypeEnum.MODEL)
                        .set("version", 0)
                        .set("classValues", List.of());
                var dataAnnotationObjectBO = DataAnnotationObjectBO.builder()
                        .datasetId(modelMessage.getDatasetId()).dataId(modelResult.getDataId()).classAttributes(classAttributes)
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
        var dataAnnotationObjectMap = dataAnnotationObjectList.stream().filter(dataAnnotationObject -> {
            var objectBO = DefaultConverter.convert(dataAnnotationObject.getClassAttributes(), ImageDetectionObjectBO.ObjectBO.class);
            return "RECTANGLE".equalsIgnoreCase(objectBO.getType());
        }).collect(Collectors.groupingBy(DataAnnotationObject::getDataId));
        modelDatasetResults.forEach(modelDatasetResult -> {
            var isSuccess = modelDatasetResult.getIsSuccess();
            if (!isSuccess) {
                return;
            }
            var modelResult = modelDatasetResult.getModelResult();
            var dataId = modelDatasetResult.getDataId();
            var dataAnnotationObjects = dataAnnotationObjectMap.get(modelDatasetResult.getDataId());
            var groundTruthObjects = new ArrayList<ImageDetectionObject>();
            if (CollUtil.isEmpty(dataAnnotationObjects)) {
                return;
            }
            dataAnnotationObjects.forEach(dataAnnotationObject -> {
                var imageDetectionObject = new ImageDetectionObject();
                var objectBO = DefaultConverter.convert(dataAnnotationObject.getClassAttributes().get("contour"), ImageDetectionObjectBO.ObjectBO.class);
                assembleObject(objectBO, imageDetectionObject);
                groundTruthObjects.add(imageDetectionObject);
            });
            var modelRunObjects = new ArrayList<ImageDetectionObject>();
            var predImageModelObjectBO = DefaultConverter.convert(modelResult, ImageDetectionObjectBO.class);
            predImageModelObjectBO.getObjects().forEach(objectBO -> {
                var imageDetectionObject = new ImageDetectionObject();
                var confidence = objectBO.getConfidence();
                assembleObject(objectBO, imageDetectionObject);
                imageDetectionObject.setConfidence(confidence);
                modelRunObjects.add(imageDetectionObject);
            });
            var groundTruthObject = ImageDetectionMetricsReqDTO.builder().id(dataId).objects(groundTruthObjects).build();
            var modelRunObject = ImageDetectionMetricsReqDTO.builder().id(dataId).objects(modelRunObjects).build();
            FileUtil.appendUtf8String(StrUtil.removeAllLineBreaks(JSONUtil.toJsonStr(groundTruthObject)), groundTruthFilePath);
            FileUtil.appendUtf8String("\n", groundTruthFilePath);
            FileUtil.appendUtf8String(StrUtil.removeAllLineBreaks(JSONUtil.toJsonStr(modelRunObject)), modelRunFilePath);
            FileUtil.appendUtf8String("\n", modelRunFilePath);
        });
    }

    private void assembleObject(ImageDetectionObjectBO.ObjectBO objectBO, ImageDetectionObject imageDetectionObject) {
        var points = objectBO.getPoints();
        if (CollUtil.isEmpty(points)) {
            return;
        }
        var leftTopX = points.get(0).getX();
        var leftTopY = points.get(0).getY();
        var rightBottomX = points.get(1).getX();
        var rightBottomY = points.get(1).getY();
        imageDetectionObject.setLeftTopX(leftTopX);
        imageDetectionObject.setLeftTopY(leftTopY);
        imageDetectionObject.setRightBottomX(rightBottomX);
        imageDetectionObject.setRightBottomY(rightBottomY);
    }

    @Override
    public String getResultEvaluateUrl() {
        return resultEvaluateUrl;
    }


    @Override
    public ModelCodeEnum getModelCodeEnum() {
        return ModelCodeEnum.IMAGE_DETECTION;
    }


}
