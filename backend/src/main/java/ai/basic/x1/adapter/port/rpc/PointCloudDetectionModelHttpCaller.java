package ai.basic.x1.adapter.port.rpc;

import ai.basic.x1.adapter.dto.ApiResult;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudDetectionReqDTO;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudDetectionRespDTO;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudSequenceReqDTO;
import ai.basic.x1.adapter.port.rpc.dto.PointCloudSequenceRespDTO;
import ai.basic.x1.usecase.exception.UsecaseException;
import cn.hutool.core.date.StopWatch;
import cn.hutool.core.lang.TypeReference;
import cn.hutool.http.*;
import cn.hutool.json.JSONUtil;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * @author andy
 */
@Component
@Slf4j
public class PointCloudDetectionModelHttpCaller {

    /**
     * Explicit timeout for the sequence (detection+tracking) call. A 50-frame
     * chunk takes ~25s at the measured ~0.5s/frame; hutool's ~10s default is far
     * too short, so we allow 120s of headroom (S0.2 / D2).
     */
    private static final int SEQUENCE_TIMEOUT_MS = 120000;


    public ApiResult<List<PointCloudDetectionRespDTO>> callPreLabelModel(PointCloudDetectionReqDTO preModelReqDTO, String url) {
        try {
            StopWatch stopWatch = new StopWatch();
            stopWatch.start();
            String requestBody = JSONUtil.toJsonStr(preModelReqDTO);
            HttpRequest httpRequest = HttpUtil.createPost(url)
                    .body(requestBody, ContentType.JSON.getValue());
            HttpResponse httpResponse = httpRequest.execute();
            stopWatch.stop();
            log.info(String.format("call preLabelModelService took: %dms,req:%s ,resp:%s", stopWatch.getLastTaskTimeMillis(), requestBody, httpResponse.body()));
            if (httpResponse.getStatus() == HttpStatus.HTTP_OK) {
                ApiResult<List<PointCloudDetectionRespDTO>> apiResult = JSONUtil.toBean(httpResponse.body(), new TypeReference<>() {
                }, false);
                return apiResult;
            } else {
                throw new UsecaseException("preLabelModel run error!");
            }
        } catch (Throwable throwable) {
            log.error("call pre-model service error.", throwable);
            throw new UsecaseException("preLabelModel run error!");
        }
    }

    /**
     * Call the detection-driven sequence endpoint ({@code /pointCloud/sequence})
     * for one chunk of frames. Uses an explicit {@link #SEQUENCE_TIMEOUT_MS}
     * timeout because a multi-frame chunk far exceeds hutool's ~10s default.
     *
     * @param sequenceReqDTO the chunk request (frames + seedObjects)
     * @param url            the sequence endpoint url (serving container, nginx-bypassed)
     */
    public ApiResult<PointCloudSequenceRespDTO> callSequenceModel(PointCloudSequenceReqDTO sequenceReqDTO, String url) {
        try {
            StopWatch stopWatch = new StopWatch();
            stopWatch.start();
            String requestBody = JSONUtil.toJsonStr(sequenceReqDTO);
            HttpRequest httpRequest = HttpUtil.createPost(url)
                    .timeout(SEQUENCE_TIMEOUT_MS)
                    .body(requestBody, ContentType.JSON.getValue());
            HttpResponse httpResponse = httpRequest.execute();
            stopWatch.stop();
            log.info(String.format("call sequenceModelService took: %dms,url:%s ,frameCount:%d ,respStatus:%d",
                    stopWatch.getLastTaskTimeMillis(), url,
                    sequenceReqDTO.getFrames() == null ? 0 : sequenceReqDTO.getFrames().size(),
                    httpResponse.getStatus()));
            if (httpResponse.getStatus() == HttpStatus.HTTP_OK) {
                ApiResult<PointCloudSequenceRespDTO> apiResult = JSONUtil.toBean(httpResponse.body(), new TypeReference<>() {
                }, false);
                return apiResult;
            } else {
                throw new UsecaseException("sequenceModel run error!");
            }
        } catch (Throwable throwable) {
            log.error("call sequence-model service error.", throwable);
            throw new UsecaseException("sequenceModel run error!");
        }
    }
}
