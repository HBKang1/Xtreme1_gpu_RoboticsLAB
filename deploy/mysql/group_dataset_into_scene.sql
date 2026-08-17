-- IMAGE 데이터셋의 낱장 이미지 전부를 씬 하나로 묶는다.
-- 맨 위 두 변수만 바꿔서 재사용한다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/group_dataset_into_scene.sql
--
-- 업로드 시 image_0 을 감싸는 폴더 이름이 scene_ 으로 시작하면 백엔드가 알아서
-- 만들어 주는 구조를(UploadDataUseCase.saveScene) 사후에 동일하게 재현한 것.
--   SCENE  행: type=SCENE, parent_id=0, content=NULL, 이름은 scene_ 로 시작
--   자식 행: type=SINGLE_DATA, parent_id=<scene id>
-- 어노테이션 경로는 씬 id -> 자식을 order_name 순으로 펼치므로(DataInfoUseCase
-- .getDataInfoBySceneIds) 프레임 순서는 order_name 이 그대로 결정한다.
-- data_annotation_object 는 data_id 로 묶여 있어 이 작업에 영향받지 않는다.
--
-- 되돌리려면 ungroup_dataset_scenes.sql 에 같은 @dsid 를 넣고 실행.
--
-- 실행 이력:
--   dataset_id=73 Zenix_Snow_Day_04 -> scene_Zenix_Snow_Day_04 (1,240 frames)
--   dataset_id=69 Zenix_Snow_Day_00 -> scene_Zenix_Snow_Day_00 (2,603 frames)

SET @dsid = 69;
SET @sname = 'scene_Zenix_Snow_Day_00';

START TRANSACTION;

-- 이 배포의 기존 LIDAR 씬들과 같은 규칙: 씬의 order_name = 첫 프레임의 order_name.
-- 그래야 목록에서 씬이 프레임 순서와 어긋나지 않는다.
SET @oname = (SELECT MIN(`order_name`) FROM `data`
               WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA');
SET @cby = (SELECT MIN(`created_by`) FROM `data`
             WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA');

INSERT INTO `data`
  (`dataset_id`, `name`, `order_name`, `content`, `type`, `parent_id`,
   `status`, `annotation_status`, `split_type`, `is_deleted`, `del_unique_key`,
   `created_at`, `created_by`)
VALUES
  (@dsid, @sname, @oname, NULL, 'SCENE', 0,
   'VALID', 'NOT_ANNOTATED', 'NOT_SPLIT', b'0', 0,
   current_timestamp, @cby);

SET @sid = LAST_INSERT_ID();

UPDATE `data` SET `parent_id` = @sid
 WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA' AND `parent_id` = 0;

COMMIT;

SELECT s.`id` AS scene_id, s.`name`, s.`order_name`,
       (SELECT COUNT(*) FROM `data` WHERE `parent_id` = s.`id`) AS frames
  FROM `data` s WHERE s.`id` = @sid;
