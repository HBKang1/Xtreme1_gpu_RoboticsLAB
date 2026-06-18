package ai.basic.x1.adapter.api.job;

import ai.basic.x1.adapter.port.dao.DataAnnotationObjectDAO;
import ai.basic.x1.adapter.port.dao.mybatis.model.DataAnnotationObject;
import ai.basic.x1.entity.DataAnnotationObjectBO;
import ai.basic.x1.util.DefaultConverter;
import cn.hutool.core.collection.CollUtil;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Idempotent delete-then-insert writer for MODEL-source annotation objects
 * produced by a tracking run. Lives in its own Spring bean so the per-frame
 * delete + saveBatch run inside a single transaction (S0.4: atomicity guard;
 * not for concurrency since Redis is single-delivery).
 *
 * <p>This intentionally does NOT reuse {@code syncModelAnnotationResult}, which
 * is INSERT-only (saveBatch with no delete) and would create duplicate rows on
 * any re-processing of the same (dataId, sourceId).
 *
 * @author tracking-pipeline
 */
@Slf4j
@Component
public class DataAnnotationObjectModelWriter {

    @Autowired
    private DataAnnotationObjectDAO dataAnnotationObjectDAO;

    /**
     * Replace all MODEL-source objects for one frame and one run (sourceId) with
     * the supplied list. Idempotent: re-running the same scene yields exactly one
     * set of rows per (dataId, sourceId) (AC9).
     *
     * @param dataId the frame data id
     * @param sourceId the run record id (DataAnnotationObject.sourceId)
     * @param objects the objects to persist (may be empty -> frame is cleared)
     */
    @Transactional(rollbackFor = Throwable.class)
    public void replaceFrameObjects(Long dataId, Long sourceId, List<DataAnnotationObjectBO> objects) {
        dataAnnotationObjectDAO.remove(Wrappers.lambdaQuery(DataAnnotationObject.class)
                .eq(DataAnnotationObject::getDataId, dataId)
                .eq(DataAnnotationObject::getSourceId, sourceId));
        if (CollUtil.isNotEmpty(objects)) {
            dataAnnotationObjectDAO.saveBatch(DefaultConverter.convert(objects, DataAnnotationObject.class));
        }
    }
}
