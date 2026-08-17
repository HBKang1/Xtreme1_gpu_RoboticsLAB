-- Zenix_Snow_Day_05 (dataset_id=74) 에서 아직 GT 가 없는 프레임에 남아 있는 모델 예측을
-- 정식 GT(DATA_FLOW) 로 승격한다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/promote_model_results_to_gt_ds74.sql
--
-- 배경
--   익스포트는 프레임마다 data/<이름>.json 은 항상 쓰지만 result/<이름>.json 은 선택한
--   소스에 객체가 있을 때만 쓴다(ExportUseCase.writeFile). GT 만 뽑으면 GT 가 없는
--   154 프레임은 result 파일이 안 생겨 "프레임이 누락된" 것처럼 보인다.
--   이 프레임들의 박스는 map_model_class_to_ontology_ds74.sql 로 classId 가 채워진 뒤
--   툴에서 모델 결과로 표시되지 않아(useTags: isModel = !classId && modelClass)
--   GT 와 시각적으로 구분되지 않았다.
--
-- 형식 맞추기
--   모델 결과는 RECTANGLE + 2점(좌상단/우하단)이고 GT 는 BOUNDING_BOX + 4점 +
--   rotation/area 다. 그대로 두면 익스포트 json 이 나머지 1,341 프레임과 달라지므로
--   기존 GT 행과 같은 모양으로 변환한다.
--   modelClass / modelConfidence 는 남긴다. DataResultObjectExportBO 가 지원하는
--   필드이고, 사람이 그린 박스가 아니라 승격된 예측이라는 출처가 남는다.
--
-- 되돌리려면 demote_gt_to_model_results_ds74.sql 실행.

SET @dsid = 74;

START TRANSACTION;

-- 되돌릴 수 있도록 대상 행 백업
DROP TABLE IF EXISTS `bak_ds74_promoted_to_gt`;
CREATE TABLE `bak_ds74_promoted_to_gt` AS
SELECT `id`, `source_type`, `source_id`, `class_id`, `class_attributes`
  FROM `data_annotation_object`
 WHERE `dataset_id` = @dsid AND `source_type` = 'MODEL';

SELECT COUNT(*) AS will_promote,
       COUNT(DISTINCT `data_id`) AS frames
  FROM `bak_ds74_promoted_to_gt` b
  JOIN `data_annotation_object` o ON o.`id` = b.`id`;

UPDATE `data_annotation_object`
   SET `source_type` = 'DATA_FLOW',
       `source_id`   = -1,
       `class_attributes` = JSON_SET(
           `class_attributes`,
           '$.type',       'BOUNDING_BOX',
           '$.sourceType', 'DATA_FLOW',
           '$.sourceId',   '-1',
           '$.backId',     `id`,
           '$.contour.rotation', 0,
           '$.contour.area', ROUND(
               (CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[1].x') AS DECIMAL(12,2))
              - CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[0].x') AS DECIMAL(12,2)))
             * (CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[1].y') AS DECIMAL(12,2))
              - CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[0].y') AS DECIMAL(12,2)))
           ),
           -- 좌상단/우하단 2점 -> 시계방향 4점 (기존 GT 와 같은 순서)
           '$.contour.points', JSON_ARRAY(
               JSON_OBJECT('x', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[0].x') AS DECIMAL(12,2)),
                           'y', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[0].y') AS DECIMAL(12,2))),
               JSON_OBJECT('x', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[1].x') AS DECIMAL(12,2)),
                           'y', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[0].y') AS DECIMAL(12,2))),
               JSON_OBJECT('x', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[1].x') AS DECIMAL(12,2)),
                           'y', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[1].y') AS DECIMAL(12,2))),
               JSON_OBJECT('x', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[0].x') AS DECIMAL(12,2)),
                           'y', CAST(JSON_EXTRACT(`class_attributes`, '$.contour.points[1].y') AS DECIMAL(12,2)))
           )
       )
 WHERE `dataset_id` = @dsid
   AND `source_type` = 'MODEL'
   AND JSON_LENGTH(JSON_EXTRACT(`class_attributes`, '$.contour.points')) = 2;

COMMIT;

-- ── 결과 확인 ──
SELECT `source_type`, `source_id`, COUNT(*) AS objects, COUNT(DISTINCT `data_id`) AS frames
  FROM `data_annotation_object` WHERE `dataset_id` = 74
 GROUP BY `source_type`, `source_id`;

-- 이제 전 프레임에 GT 가 있어야 한다 (frames_with_gt = total_frames)
SELECT (SELECT COUNT(*) FROM `data` WHERE `dataset_id` = 74 AND `type` = 'SINGLE_DATA') AS total_frames,
       (SELECT COUNT(DISTINCT `data_id`) FROM `data_annotation_object`
         WHERE `dataset_id` = 74 AND `source_type` = 'DATA_FLOW') AS frames_with_gt;
