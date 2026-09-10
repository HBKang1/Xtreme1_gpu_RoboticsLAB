# 카메라 캘리브레이션 교체 기록

## 배경

이 배포에는 서로 다른 캘리브레이션 두 벌이 있다.

| | testbed_st1~st4 (ds63~66) | rough_152141/152745/154627 (ds111~113) |
|---|---|---|
| fx / fy | 642.04 / 641.02 | 653.5392 / 654.7457 |
| cx / cy | 653.09 / 355.49 | 654.4230 / 358.5458 |
| distortion K | -0.0548, 0.0638, -0.0203 | -0.0493, 0.0665, -0.0212 |
| distortion P | -0.0, 0.0015 | 0.0006, 0.0022 |
| 외부 t (m) | (-0.0198, +0.0755, +0.0273) | (-0.0122, +0.1117, -0.0455) |

그룹 안에서는 프레임까지 전부 바이트 동일. 촬영 세션이 두 번이었고 사이에
재캘리브레이션이 있었다는 뜻이다(testbed 는 20260724 녹화, rough 는 20260820 업로드).

두 캘리 차이는 회전 1.905°, 이동 8.16 cm, 초점거리 약 2%. 같은 3D 점을 투영하면
거리와 거의 무관하게 22~39 px 어긋난다(회전 성분이 지배적이라 멀어져도 안 줄어든다).

## 한 일 (2026-08-20)

testbed 쪽이 더 정확하다는 판단에 따라 ds111~113 의 camera_config 1,182개를
testbed_st 값으로 교체했다.

- 원본 백업: MinIO `xtreme1/_calib_backup/20260820_rough_original/ds{111,112,113}/`
- 대표 원본: `rough_original_camera_config.json` (722 bytes)
- 적용한 값: `testbed_st_camera_config.json` (711 bytes)
- DB 메타 동기화: `../mysql/sync_calib_file_size_ds111_113.sql`

## 되돌리기

    bash deploy/calib/restore_rough_calib.sh

그 다음 file.size 를 722 로 되돌린다(스크립트 주석 참고).

## 주의

교체가 옳은지는 아직 검증되지 않았다. 라이다 점군을 이미지에 투영해 정합을
눈으로 확인해야 확정할 수 있다. 어긋나 보이면 위 복원 절차로 되돌릴 것.

## 6-DoF pose를 `camera_external`로 변환하는 규칙

Xtreme1의 `camera_external`은 사용자가 말하는 `(x, y, z, roll, pitch, yaw)`를
그대로 넣는 필드가 아니다. 입력값은 **LiDAR 좌표계에서 본 camera_link의 절대
pose**이고, JSON에는 LiDAR 점을 camera optical 좌표계로 보내는 row-major 4x4
행렬을 넣는다.

- `x`, `y`, `z`: 입력은 cm, 계산 전 m로 변환
- `roll`, `pitch`, `yaw`: 입력은 degree, 계산 전 radian으로 변환
- Euler 회전 순서: `R_pose = Rz(yaw) * Ry(pitch) * Rx(roll)`
- camera_link -> optical 축 변환:

      A = [[ 0, -1,  0, 0],
           [ 0,  0, -1, 0],
           [ 1,  0,  0, 0],
           [ 0,  0,  0, 1]]

camera_link의 pose 행렬을 `C = [R_pose | t]`라 하면 최종 extrinsic은 다음과 같다.

    camera_external = A * inverse(C)

기존 `camera_external`에 입력값을 단순히 더하거나 보정행렬을 곱하면 안 된다.
특히 JSON 행렬의 translation 세 값은 optical 좌표계 값이므로 사용자가 말한
`x/y/z`와 축도 다르다.

### Caterpie_0904 적용 기록 (2026-09-10)

dataset_id 190의 DB 참조 camera_config 3,855개에 다음 절대 pose를 적용했다.

    x=5 cm, y=0 cm, z=6 cm
    roll=0 deg, pitch=3 deg, yaw=1.5 deg

변환된 `camera_external`은 모든 프레임에서 다음과 같다(intrinsic/distortion은
각 원본 파일 값을 유지).

    [ 0.0261769483, -0.9996573250,  0.0000000000, -0.0013088474,
     -0.0523180220, -0.0013699956, -0.9986295348,  0.0625336732,
      0.9982873294,  0.0261410737, -0.0523359562, -0.0467742091,
      0.0000000000,  0.0000000000,  0.0000000000,  1.0000000000 ]

- 원본 백업: MinIO
  `xtreme1/_calib_backup/20260910_caterpie_0904_before_x5_z6_pitch3_yaw1_5/`
- 적용 후 행렬을 camera_link pose로 역변환하여 `(5, 0, 6) cm`,
  `(0, 3, 1.5) deg`가 복원되는지 확인했다.
- MinIO 객체 3,855개의 해시와 DB `file.size`를 검증했다.

## Gravity-aligned 점군은 별도 처리

위 절대-pose 변환과 중력보정은 서로 다른 단계다. 점군에 변환 `G`를 적용해
`X_aligned = G * X_original`로 만들었다면 같은 영상 투영을 유지할 calibration은
다음과 같다.

    E_aligned = E_base * inverse(G)

중력보정이 회전만 포함하면 `R_aligned = R_base * transpose(R_G)`이고 extrinsic의
translation은 바뀌지 않는다. 프레임마다 서로 다른 `G_i`를 적용했다면
`E_i = E_base * inverse(G_i)`도 프레임별로 계산해야 한다.

실제 `rough_*_gravity_aligned` 데이터셋의 원본/변환 PCD를 비교한 결과 이 관계가
부동소수점 오차 범위에서 성립한다. 따라서 절대 pose를 바꾸면서 기존 gravity
보정을 보존하려면 먼저 각 프레임(또는 시퀀스)의 `G_i`를 분리한 후 새
`E_base`에 다시 합성해야 한다.
