-- Zenix_Snow_Day_05 (dataset_id=74) 의 모델 예측 중 modelClass 가 데이터셋 온톨로지
-- 클래스 이름과 같은 것을, 그 온톨로지 클래스로 지정한다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/map_model_class_to_ontology_ds74.sql
--
-- 왜 필요한가
--   모델 실행 결과는 modelClass("Vehicle") 만 갖고 classId 가 비어 있다. image-tool 은
--   class_attributes.classId 로 클래스를 해석하고(result-request.convertObject2Annotate →
--   editor.getClassType), 비어 있으면 __Model__##<modelClass> 라는 가짜 그룹으로 묶어
--   보여준다. 그래서 클래스 지정이 안 되는 것처럼 보인다.
--   Editor.classMap 은 이름과 id 양쪽으로 키가 걸려 있어 classId 에 id 문자열을 넣으면 된다.
--
-- 규칙: 이름이 정확히 같을 때만 교체한다(대소문자 구분).
--       온톨로지에 없는 modelClass(Cyclist 6개)는 건드리지 않는다.
--       source_type 은 MODEL 그대로 두어 기존 GT(DATA_FLOW 1,494개)와 섞이지 않게 한다.
--
-- 되돌리려면 unmap_model_class_ds74.sql 실행.

SET @dsid = 74;

START TRANSACTION;

-- 되돌릴 수 있도록 대상 행 백업
DROP TABLE IF EXISTS `bak_ds74_model_class_map`;
CREATE TABLE `bak_ds74_model_class_map` AS
SELECT `id`, `class_id`, `class_attributes`
  FROM `data_annotation_object`
 WHERE `dataset_id` = @dsid
   AND `source_type` = 'MODEL'
   AND `class_id` IS NULL
   AND JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.modelClass')) IN
       (SELECT `name` FROM `dataset_class` WHERE `dataset_id` = @dsid);

SELECT COUNT(*) AS will_update FROM `bak_ds74_model_class_map`;

-- modelClass 이름이 같은 dataset_class 로 지정.
--   class_id          : 백엔드 통계/필터/내보내기가 쓰는 컬럼
--   classId           : image-tool 이 실제로 읽는 값. DATA_FLOW 행과 동일하게 문자열로 저장
--   meta.classType/색 : 툴이 classConfig 에서 다시 채우지만 기존 GT 행과 모양을 맞춰 둔다
UPDATE `data_annotation_object` o
  JOIN `dataset_class` c
    ON c.`dataset_id` = o.`dataset_id`
   AND c.`name` = JSON_UNQUOTE(JSON_EXTRACT(o.`class_attributes`, '$.modelClass'))
   SET o.`class_id` = c.`id`,
       o.`class_attributes` = JSON_SET(
           o.`class_attributes`,
           '$.classId', CAST(c.`id` AS CHAR),
           '$.meta', JSON_OBJECT('color', c.`color`, 'classType', c.`name`)
       )
 WHERE o.`dataset_id` = @dsid
   AND o.`source_type` = 'MODEL'
   AND o.`class_id` IS NULL;

COMMIT;

-- ── 결과 확인 ──
SELECT JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.modelClass')) AS model_class,
       `class_id`,
       JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.classId')) AS attr_class_id,
       COUNT(*) AS objects
  FROM `data_annotation_object`
 WHERE `dataset_id` = 74 AND `source_type` = 'MODEL'
 GROUP BY model_class, `class_id`, attr_class_id
 ORDER BY objects DESC;

-- 기존 GT 가 그대로인지
SELECT `source_type`, `source_id`, COUNT(*) AS objects, SUM(`class_id` IS NULL) AS null_class
  FROM `data_annotation_object` WHERE `dataset_id` = 74
 GROUP BY `source_type`, `source_id`;
