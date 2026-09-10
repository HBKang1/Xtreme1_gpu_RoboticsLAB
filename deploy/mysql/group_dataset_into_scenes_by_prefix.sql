-- IMAGE 데이터셋의 낱장 이미지를 이름 앞부분(시나리오)별로 여러 씬으로 묶는다.
-- group_dataset_into_scene.sql 이 전부를 씬 하나로 묶는 것과 달리, 여기서는
-- name 에서 구분자 앞을 잘라 시나리오 키로 쓰고 키마다 씬을 하나씩 만든다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/group_dataset_into_scenes_by_prefix.sql
--
-- 만들어지는 구조는 group_dataset_into_scene.sql 과 같다(UploadDataUseCase.saveScene 재현).
--   SCENE  행: type=SCENE, parent_id=0, content=NULL, 이름은 scene_ 로 시작
--   자식 행: type=SINGLE_DATA, parent_id=<scene id>
-- 씬의 order_name 은 그 씬 첫 프레임의 order_name 으로 둔다. 목록에서 씬 순서가
-- 프레임 순서와 어긋나지 않게 하기 위한 이 배포의 기존 규칙.
--
-- @sep : name 을 자를 구분자. 이 앞부분이 시나리오 키가 된다.
--        Caterpie_YOLO_Finetuniing 은 rough_152141_scan_000002 꼴이라 '_scan_' 이면
--        rough_152141 / rough_152745 / rough_154627 / st1 / st2 다섯 개로 갈린다.
--
-- 되돌리려면 ungroup_dataset_scenes.sql 에 같은 @dsid 를 넣고 실행.
-- (씬을 여러 개 만들어도 그 스크립트가 해당 데이터셋 SCENE 을 전부 지운다.)

SET @dsid = 79;
SET @sep = '_scan_';

-- 어떤 씬이 생길지 먼저 본다.
SELECT SUBSTRING_INDEX(`name`, @sep, 1) AS scenario,
       COUNT(*) AS frames,
       MIN(`order_name`) AS first_order_name
  FROM `data`
 WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA'
 GROUP BY scenario ORDER BY first_order_name;

START TRANSACTION;

SET @cby = (SELECT MIN(`created_by`) FROM `data`
             WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA');

-- 시나리오마다 씬 행을 하나씩. INSERT ... SELECT 라 커서 없이 한 번에 끝난다.
INSERT INTO `data`
  (`dataset_id`, `name`, `order_name`, `content`, `type`, `parent_id`,
   `status`, `annotation_status`, `split_type`, `is_deleted`, `del_unique_key`,
   `created_at`, `created_by`)
SELECT @dsid,
       CONCAT('scene_', SUBSTRING_INDEX(`name`, @sep, 1)),
       MIN(`order_name`),
       NULL, 'SCENE', 0,
       'VALID', 'NOT_ANNOTATED', 'NOT_SPLIT', b'0', 0,
       current_timestamp, @cby
  FROM `data`
 WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA' AND `parent_id` = 0
 GROUP BY SUBSTRING_INDEX(`name`, @sep, 1);

-- 각 프레임을 이름이 맞는 씬 밑으로. 방금 만든 SCENE 행만 대상이 되도록
-- type 으로 거른다(자식은 SINGLE_DATA 라 서로 섞이지 않는다).
UPDATE `data` d
  JOIN `data` s
    ON s.`dataset_id` = d.`dataset_id`
   AND s.`type` = 'SCENE'
   AND s.`name` = CONCAT('scene_', SUBSTRING_INDEX(d.`name`, @sep, 1))
   SET d.`parent_id` = s.`id`
 WHERE d.`dataset_id` = @dsid AND d.`type` = 'SINGLE_DATA' AND d.`parent_id` = 0;

COMMIT;

-- ── 결과 확인 ──
SELECT s.`id` AS scene_id, s.`name`, s.`order_name`,
       (SELECT COUNT(*) FROM `data` WHERE `parent_id` = s.`id`) AS frames
  FROM `data` s
 WHERE s.`dataset_id` = @dsid AND s.`type` = 'SCENE'
 ORDER BY s.`order_name`;

-- 씬에 못 들어간 낱장이 남았는지
SELECT COUNT(*) AS orphan_frames FROM `data`
 WHERE `dataset_id` = @dsid AND `type` = 'SINGLE_DATA' AND `parent_id` = 0;
