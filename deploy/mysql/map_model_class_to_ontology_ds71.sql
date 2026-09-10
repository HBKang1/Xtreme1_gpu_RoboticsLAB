-- Zenix_Snow_Day_02 (dataset_id=71) 의 모델 예측을 온톨로지 클래스로 지정한다.
--
--   Car, Truck, Bus -> Vehicle(130)
--   Person          -> Pedestrian(129)
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/map_model_class_to_ontology_ds71.sql
--
-- 왜 필요한가
--   모델 실행 결과는 modelClass("Car") 만 갖고 classId 가 비어 있다. image-tool 은
--   class_attributes.classId 로 클래스를 해석하고(result-request.convertObject2Annotate →
--   editor.getClassType), 비어 있으면 __Model__##<modelClass> 라는 가짜 그룹으로 묶어
--   보여준다. 그래서 툴에서 COCO 클래스 이름대로 갈라져 보인다.
--   Editor.classMap 은 이름과 id 양쪽으로 키가 걸려 있어 classId 에 id 문자열을 넣으면 된다.
--
-- ds74 스크립트와 다른 점
--   ds74 는 modelClass 이름이 온톨로지 클래스와 정확히 같을 때만 바꿨다. 여기서는
--   COCO 클래스 이름과 온톨로지 이름이 달라서(Car/Truck/Bus -> Vehicle) 매핑을 명시한다.
--
-- source_type 은 MODEL 그대로 둔다. 검수 전이라 기존 GT(DATA_FLOW 4개)와 섞이면 안 되고,
-- 검수가 끝나면 promote_model_results_to_gt_ds74.sql 과 같은 방식으로 승격하면 된다.
-- 그래서 geometry 도 RECTANGLE 그대로 두고 변환하지 않는다.
--
-- 매핑을 나눠서 여러 번 돌려도 되도록 만들었다. 백업 테이블은 지우지 않고 덧붙이며
-- (INSERT IGNORE), UPDATE 는 class_id IS NULL 인 행만 건드리므로 이미 지정된 행은 넘어간다.
--
-- 되돌리려면 unmap_model_class_ds71.sql 실행.

SET @dsid = 71;

-- modelClass -> 온톨로지 클래스 이름 매핑.
-- MySQL 5.7 의 다중 테이블 UPDATE 는 파생 테이블 조인이 불안정해서 실제 테이블로 만든다.
-- 서버 기본 charset 이 latin1 이라 컬럼마다 명시한다. 비교 상대의 collation 을 맞추지 않으면
-- "Illegal mix of collations" 로 죽는다.
--   model_class : JSON_UNQUOTE 결과가 utf8mb4_bin 이므로 대소문자를 구분해 비교한다
--   class_name  : dataset_class.name 과 같은 utf8mb4_general_ci
DROP TABLE IF EXISTS `tmp_ds71_class_map`;
CREATE TABLE `tmp_ds71_class_map` (
  `model_class` VARCHAR(64)  CHARACTER SET utf8mb4 COLLATE utf8mb4_bin        NOT NULL PRIMARY KEY,
  `class_name`  VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL
) DEFAULT CHARSET=utf8mb4;
INSERT INTO `tmp_ds71_class_map` (`model_class`, `class_name`) VALUES
  ('Car',    'Vehicle'),
  ('Truck',  'Vehicle'),
  ('Bus',    'Vehicle'),
  ('Person', 'Pedestrian');

-- 매핑에 있는 이름이 실제 온톨로지에 다 있는지 먼저 본다. 없으면 그 행은 그냥 안 바뀐다.
SELECT m.`model_class`, m.`class_name`, c.`id` AS class_id
  FROM `tmp_ds71_class_map` m
  LEFT JOIN `dataset_class` c ON c.`dataset_id` = @dsid AND c.`name` = m.`class_name`
 ORDER BY m.`model_class`;

-- 되돌릴 수 있도록 대상 행 백업. 앞서 돌린 매핑의 백업을 덮어쓰지 않도록 덧붙인다.
CREATE TABLE IF NOT EXISTS `bak_ds71_model_class_map` (
  `id`               BIGINT(20) NOT NULL PRIMARY KEY,
  `class_id`         BIGINT(20) DEFAULT NULL,
  `class_attributes` JSON       DEFAULT NULL
);

START TRANSACTION;

INSERT IGNORE INTO `bak_ds71_model_class_map` (`id`, `class_id`, `class_attributes`)
SELECT `id`, `class_id`, `class_attributes`
  FROM `data_annotation_object`
 WHERE `dataset_id` = @dsid
   AND `source_type` = 'MODEL'
   AND `class_id` IS NULL
   AND JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.modelClass')) IN
       (SELECT `model_class` FROM `tmp_ds71_class_map`);

-- 매핑된 dataset_class 로 지정.
--   class_id          : 백엔드 통계/필터/내보내기가 쓰는 컬럼
--   classId           : image-tool 이 실제로 읽는 값. DATA_FLOW 행과 동일하게 문자열로 저장
--   meta.classType/색 : 툴이 classConfig 에서 다시 채우지만 기존 GT 행과 모양을 맞춰 둔다
UPDATE `data_annotation_object` o
  JOIN `tmp_ds71_class_map` m
    ON m.`model_class` = JSON_UNQUOTE(JSON_EXTRACT(o.`class_attributes`, '$.modelClass'))
  JOIN `dataset_class` c
    ON c.`dataset_id` = o.`dataset_id`
   AND c.`name` = m.`class_name`
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

DROP TABLE `tmp_ds71_class_map`;

-- ── 결과 확인 ──
SELECT `source_type`,
       JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.modelClass')) AS model_class,
       `class_id`,
       JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.classId')) AS attr_class_id,
       JSON_UNQUOTE(JSON_EXTRACT(`class_attributes`, '$.meta.classType')) AS meta_class_type,
       COUNT(*) AS objects
  FROM `data_annotation_object`
 WHERE `dataset_id` = 71
 GROUP BY 1, 2, 3, 4, 5
 ORDER BY objects DESC;

SELECT COUNT(*) AS backed_up FROM `bak_ds71_model_class_map`;
