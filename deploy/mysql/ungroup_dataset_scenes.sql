-- group_dataset_into_scene.sql 되돌리기.
-- 해당 데이터셋의 이미지를 다시 낱장(SINGLE_DATA, parent_id=0)으로 풀고 씬 행을 지운다.
-- data_annotation_object 는 data_id 로 묶여 있어 영향받지 않는다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/ungroup_dataset_scenes.sql
--
-- 주의: 씬 단위로 진행 중인 어노테이션 기록(data_annotation_record / data_edit)이
-- 있으면 먼저 정리할 것. 씬을 지우면 그 기록이 가리키는 sceneId 가 사라진다.

SET @dsid = 113;

START TRANSACTION;

UPDATE `data` SET `parent_id` = 0
 WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA';

DELETE FROM `data`
 WHERE `dataset_id` = @dsid AND `type` = 'SCENE';

COMMIT;

SELECT `type`, `parent_id`, COUNT(*) AS cnt FROM `data`
 WHERE `dataset_id` = @dsid GROUP BY `type`, `parent_id`;
