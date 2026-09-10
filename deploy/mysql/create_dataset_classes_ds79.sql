-- Caterpie_YOLO_Finetuniing (dataset_id=79) 에 라벨링용 온톨로지 클래스를 만든다.
--
--   docker exec -i xtreme1_gpu_roboticslab-mysql-1 \
--     mysql -uroot -pImOxO8Lz xtreme1 < deploy/mysql/create_dataset_classes_ds79.sql
--
-- 이 데이터셋은 실내 보행자 검출용이라 클래스는 Pedestrian 하나면 된다.
-- COCO 모델을 classes=["person"] 로 돌린 결과(1,493개)를 여기에 매핑해서 쓴다.
--
-- 속성(attributes)을 왜 지금 넣는가
--   class_attributes.classValues 에 저장되고 export json 에 같이 나온다. 라벨링을
--   시작한 뒤에 소급해서 채우는 건 사실상 불가능하므로 시작 전에 확정해야 한다.
--   이 배포에서 attributes 를 쓰는 건 데모 dataset_id=1 뿐이고, 실제 작업 데이터셋
--   (71/74/77/78) 은 전부 비어 있어서 가림 여부를 구분할 방법이 없는 상태다.
--
--   Occlusion  : 다른 객체가 가린 정도. 이미지 안에 있지만 덮여 있는 경우.
--                none    가시율 80% 이상
--                partial 가시율 30~80%. 보이는 영역만 타이트하게 그린다
--                heavy   가시율 30% 미만. 그리되 학습 포함 여부는 export 때 결정
--   Truncation : 화면 경계로 잘린 경우. 가려진 부분이 이미지에 아예 없다.
--                none / edge
--
--   둘을 나눈 이유: 원인이 다르면 export 시 처리도 달라야 한다. 가장자리에 걸친
--   객체는 추론 때 반드시 생기므로 학습에 넣어야 하고, 심하게 가려진 객체는 빼는
--   선택지가 있다. 하나의 속성으로 합치면 "heavy 제외" 필터에 가장자리 데이터가
--   같이 날아간다.
--
--   완전히 가려진(가시율 0%) 객체는 라벨하지 않는다. amodal 추측은 작업자마다
--   달라져서 재현이 안 된다. 그래서 Occlusion 에 'full' 옵션은 두지 않았다.
--
-- 되돌리려면 drop_dataset_classes_ds79.sql 실행.

SET @dsid = 79;
SET @cby = (SELECT MIN(`created_by`) FROM `data` WHERE `dataset_id` = @dsid);

-- 이미 클래스가 있으면 멈춘다. 중복 생성하면 매핑 대상이 갈린다.
SELECT COUNT(*) AS existing_classes FROM `dataset_class` WHERE `dataset_id` = @dsid;

START TRANSACTION;

INSERT INTO `dataset_class`
  (`dataset_id`, `name`, `color`, `tool_type`, `tool_type_options`, `attributes`,
   `created_at`, `created_by`)
SELECT @dsid, 'Pedestrian', '#7dfaf2', 'BOUNDING_BOX', JSON_OBJECT(),
       JSON_ARRAY(
         JSON_OBJECT(
           'name', 'Occlusion',
           'type', 'RADIO',
           'required', TRUE,
           'options', JSON_ARRAY(
             JSON_OBJECT('name', 'none',    'attributes', JSON_ARRAY()),
             JSON_OBJECT('name', 'partial', 'attributes', JSON_ARRAY()),
             JSON_OBJECT('name', 'heavy',   'attributes', JSON_ARRAY())
           )
         ),
         JSON_OBJECT(
           'name', 'Truncation',
           'type', 'RADIO',
           'required', TRUE,
           'options', JSON_ARRAY(
             JSON_OBJECT('name', 'none', 'attributes', JSON_ARRAY()),
             JSON_OBJECT('name', 'edge', 'attributes', JSON_ARRAY())
           )
         )
       ),
       current_timestamp, @cby
  FROM DUAL
 WHERE NOT EXISTS (SELECT 1 FROM `dataset_class`
                    WHERE `dataset_id` = @dsid AND `name` = 'Pedestrian');

COMMIT;

-- ── 결과 확인 ──
SELECT `id`, `dataset_id`, `name`, `color`, `tool_type`, JSON_PRETTY(`attributes`) AS attrs
  FROM `dataset_class` WHERE `dataset_id` = @dsid\G
