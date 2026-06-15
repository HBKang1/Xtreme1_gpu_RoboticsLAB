package ai.basic.x1.usecase;

import ai.basic.x1.adapter.api.context.RequestContextHolder;
import ai.basic.x1.adapter.port.dao.DataEditDAO;
import ai.basic.x1.adapter.port.dao.DataInfoDAO;
import ai.basic.x1.adapter.port.dao.mybatis.model.DataEdit;
import ai.basic.x1.adapter.port.dao.mybatis.model.DataInfo;
import ai.basic.x1.entity.enums.DataAnnotationStatusEnum;
import ai.basic.x1.entity.enums.DataStatusEnum;
import ai.basic.x1.usecase.exception.UsecaseCode;
import ai.basic.x1.usecase.exception.UsecaseException;
import cn.hutool.core.collection.CollectionUtil;
import cn.hutool.core.util.ObjectUtil;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.google.common.collect.Sets;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

/**
 * @author chenchao, chanYoung
 * @date 2024/4/15
 */
public class DataFlowUseCase {

    @Autowired
    private DataInfoDAO dataInfoDAO;

    @Autowired
    private DataEditUseCase dataEditUseCase;

    @Autowired
    private DataEditDAO dataEditDAO;

    @Transactional(rollbackFor = Exception.class)
    public void changeDataStatus(Long dataId, DataStatusEnum status) {
        var dataEdit = dataEditUseCase.checkLock(Sets.newHashSet(dataId));
        dataInfoDAO.updateById(DataInfo.builder().id(dataId).status(status).build());
        var sceneId = dataEdit.getSceneId();
        if (ObjectUtil.isNotNull(sceneId) && DataStatusEnum.INVALID.equals(status)) {
            dataInfoDAO.updateById(DataInfo.builder().id(sceneId).status(status).build());
        } else if (ObjectUtil.isNotNull(sceneId) && DataStatusEnum.VALID.equals(status)) {
            var lambdaQueryWrapper = Wrappers.lambdaQuery(DataInfo.class);
            lambdaQueryWrapper.eq(DataInfo::getDatasetId, dataEdit.getDatasetId());
            lambdaQueryWrapper.eq(DataInfo::getParentId, sceneId);
            lambdaQueryWrapper.eq(DataInfo::getStatus, DataStatusEnum.INVALID);
            if (dataInfoDAO.count() == 0) {
                dataInfoDAO.updateById(DataInfo.builder().id(sceneId).status(status).build());
            }
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void submit(Long itemId) {
        var dataEdit = dataEditUseCase.checkLock(Sets.newHashSet(itemId));
        DataStatusEnum status = Optional.ofNullable(dataInfoDAO.getById(itemId)).orElseThrow().getStatus();
        DataAnnotationStatusEnum annotationStatus = DataAnnotationStatusEnum.INVALID;
        if (DataStatusEnum.VALID.equals(status)) {
            annotationStatus = DataAnnotationStatusEnum.ANNOTATED;
        }
        dataInfoDAO.updateById(DataInfo.builder().id(itemId).status(status).annotationStatus(annotationStatus).build());
        var sceneId = dataEdit.getSceneId();
        if (ObjectUtil.isNotNull(sceneId)) {
            var lambdaQueryWrapper = Wrappers.lambdaQuery(DataInfo.class);
            lambdaQueryWrapper.eq(DataInfo::getDatasetId, dataEdit.getDatasetId());
            lambdaQueryWrapper.eq(DataInfo::getParentId, sceneId);
            lambdaQueryWrapper.eq(DataInfo::getStatus, DataStatusEnum.INVALID);
            if (dataInfoDAO.count(lambdaQueryWrapper) == 0) {
                dataInfoDAO.updateById(DataInfo.builder().id(sceneId).status(DataStatusEnum.VALID).annotationStatus(DataAnnotationStatusEnum.ANNOTATED).build());
                var dataInfoLambdaUpdateWrapper = Wrappers.lambdaUpdate(DataInfo.class)
                        .eq(DataInfo::getDatasetId, dataEdit.getDatasetId())
                        .eq(DataInfo::getParentId, sceneId);
                dataInfoLambdaUpdateWrapper.set(DataInfo::getAnnotationStatus, DataAnnotationStatusEnum.ANNOTATED);
                dataInfoDAO.update(dataInfoLambdaUpdateWrapper);
            } else {
                dataInfoDAO.updateById(DataInfo.builder().id(sceneId).status(DataStatusEnum.INVALID).annotationStatus(DataAnnotationStatusEnum.INVALID).build());
                var dataInfoLambdaUpdateWrapper = Wrappers.lambdaUpdate(DataInfo.class)
                        .eq(DataInfo::getDatasetId, dataEdit.getDatasetId())
                        .eq(DataInfo::getParentId, sceneId)
                        .eq(DataInfo::getStatus, DataStatusEnum.VALID);
                dataInfoLambdaUpdateWrapper.set(DataInfo::getAnnotationStatus, DataAnnotationStatusEnum.ANNOTATED);
                dataInfoDAO.update(dataInfoLambdaUpdateWrapper);

                var dataInfoLambdaUpdateWrapper2 = Wrappers.lambdaUpdate(DataInfo.class)
                        .eq(DataInfo::getDatasetId, dataEdit.getDatasetId())
                        .eq(DataInfo::getParentId, sceneId)
                        .eq(DataInfo::getStatus, DataStatusEnum.INVALID);
                dataInfoLambdaUpdateWrapper2.set(DataInfo::getAnnotationStatus, DataAnnotationStatusEnum.INVALID);
                dataInfoDAO.update(dataInfoLambdaUpdateWrapper2);
            }
        }
    }

    /**
     * Submit a single frame without rolling the whole scene up. The scene is only promoted to
     * ANNOTATED once every one of its frames has been submitted; otherwise it stays NOT_ANNOTATED.
     */
    @Transactional(rollbackFor = Exception.class)
    public void submitFrame(Long itemId) {
        var dataEdit = dataEditUseCase.checkLock(Sets.newHashSet(itemId));
        DataStatusEnum status = Optional.ofNullable(dataInfoDAO.getById(itemId)).orElseThrow().getStatus();
        DataAnnotationStatusEnum annotationStatus = DataStatusEnum.VALID.equals(status)
                ? DataAnnotationStatusEnum.ANNOTATED : DataAnnotationStatusEnum.INVALID;
        dataInfoDAO.updateById(DataInfo.builder().id(itemId).status(status).annotationStatus(annotationStatus).build());

        var sceneId = dataEdit.getSceneId();
        if (ObjectUtil.isNotNull(sceneId)) {
            var notAnnotatedCount = dataInfoDAO.count(Wrappers.lambdaQuery(DataInfo.class)
                    .eq(DataInfo::getDatasetId, dataEdit.getDatasetId())
                    .eq(DataInfo::getParentId, sceneId)
                    .eq(DataInfo::getAnnotationStatus, DataAnnotationStatusEnum.NOT_ANNOTATED));
            if (notAnnotatedCount == 0) {
                // every frame submitted: mirror the full-submit scene status rule
                var invalidCount = dataInfoDAO.count(Wrappers.lambdaQuery(DataInfo.class)
                        .eq(DataInfo::getDatasetId, dataEdit.getDatasetId())
                        .eq(DataInfo::getParentId, sceneId)
                        .eq(DataInfo::getStatus, DataStatusEnum.INVALID));
                if (invalidCount == 0) {
                    dataInfoDAO.updateById(DataInfo.builder().id(sceneId).status(DataStatusEnum.VALID).annotationStatus(DataAnnotationStatusEnum.ANNOTATED).build());
                } else {
                    dataInfoDAO.updateById(DataInfo.builder().id(sceneId).status(DataStatusEnum.INVALID).annotationStatus(DataAnnotationStatusEnum.INVALID).build());
                }
            } else {
                // some frames still pending: the scene is not fully annotated yet
                dataInfoDAO.updateById(DataInfo.builder().id(sceneId).annotationStatus(DataAnnotationStatusEnum.NOT_ANNOTATED).build());
            }
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void resetAnnotationStatus(List<Long> dataIds) {
        // only locks held by other users block the reset, so the lock holder can reset from the editor
        var currentUserId = RequestContextHolder.getContext().getUserInfo().getId();
        var lockCount = dataEditDAO.count(Wrappers.lambdaQuery(DataEdit.class)
                .ne(DataEdit::getCreatedBy, currentUserId)
                .and(wq -> wq.in(DataEdit::getDataId, dataIds).or().in(DataEdit::getSceneId, dataIds)));
        if (lockCount > 0) {
            throw new UsecaseException(UsecaseCode.DATASET_DATA_OTHERS_ANNOTATING);
        }
        var dataInfos = dataInfoDAO.listByIds(dataIds);
        if (CollectionUtil.isEmpty(dataInfos)) {
            throw new UsecaseException(UsecaseCode.DATA_NOT_FOUND);
        }
        var updateWrapper = Wrappers.lambdaUpdate(DataInfo.class)
                .nested(wq -> wq.in(DataInfo::getId, dataIds).or().in(DataInfo::getParentId, dataIds))
                .set(DataInfo::getAnnotationStatus, DataAnnotationStatusEnum.NOT_ANNOTATED);
        dataInfoDAO.update(updateWrapper);

        // a reset frame makes its parent scene no longer fully annotated
        var parentIds = dataInfos.stream().map(DataInfo::getParentId)
                .filter(parentId -> ObjectUtil.isNotNull(parentId) && parentId > 0)
                .collect(Collectors.toSet());
        if (CollectionUtil.isNotEmpty(parentIds)) {
            dataInfoDAO.update(Wrappers.lambdaUpdate(DataInfo.class)
                    .in(DataInfo::getId, parentIds)
                    .set(DataInfo::getAnnotationStatus, DataAnnotationStatusEnum.NOT_ANNOTATED));
        }
    }

}
