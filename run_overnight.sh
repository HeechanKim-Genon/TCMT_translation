#!/bin/bash
# 야간 일괄 실행 — 100개 / 1000개 두 규모를 순차로 돌린다.
#
# 설계 변경 (2026-08-03)
#   · 문단당 용어를 8개 → 3개로 줄이고, 문단 수를 대폭 늘렸다.
#     예전 설정(문단 9개)은 표본이 너무 작아 문단 1개가 어긋나면 수치가 흔들렸다.
#   · 용어당 문단 등장 횟수를 균등하게 배분한다 (build_dataset.py)
#   · 응답 교차 탐지·재호출을 켠 상태로 돌린다 (tcmt_common.pmap_verified)
#
# 두 규모를 동시에 돌리지 않는다. 같은 서빙을 쓰므로 동시 실행이 겹치면
# 응답 교차가 늘어난다 (교차의 직접 원인으로 의심되는 조건).

set -u
cd "$(dirname "$0")"

export GENOS_BASE="https://genos.genon.ai/api/gateway/rep/serving"
export GLM_SERVING=1000
export GLM_MODEL="z-ai/glm-5.2"
export GLM_KEY="${GLM_KEY:?GLM_KEY 를 넘겨야 한다}"
export QWEN_SERVING=752
export QWEN_MODEL="model"
export QWEN_KEY="${QWEN_KEY:?QWEN_KEY 를 넘겨야 한다}"
export TCMT_WORKERS="${TCMT_WORKERS:-24}"

LOG=logs
mkdir -p "$LOG"

step () {   # step <로그이름> <명령...>
  local name=$1; shift
  echo "=== [$(date '+%H:%M:%S')] $name 시작"
  if "$@" > "$LOG/$name.log" 2>&1; then
    echo "=== [$(date '+%H:%M:%S')] $name 완료"
  else
    echo "!!! [$(date '+%H:%M:%S')] $name 실패 (exit $?) — $LOG/$name.log 확인"
  fi
}

scale () {  # scale <이름> <용어수> <문단수>
  local tag=$1 terms=$2 paras=$3
  export TCMT_DATA="dataset_$tag"
  export TCMT_OUT="results_$tag"
  echo
  echo "###################  규모 $tag  (용어 $terms · 문단 $paras · 문단당 3용어)"
  step "${tag}_0_build" python3 build_dataset.py \
       --terms "$terms" --paras "$paras" --per-para 3 --words 170 --attempts 6
  step "${tag}_a_word"  python3 run_a_word.py --batch 50
  step "${tag}_b_sent"  python3 run_b_sentence.py
  step "${tag}_c_para"  python3 run_c_paragraph.py --include-single
}

echo "야간 실행 시작 $(date '+%Y-%m-%d %H:%M:%S')  workers=$TCMT_WORKERS"

# 용어 100개 → 문단 100개면 용어당 3회 등장
scale 100 100 100
# 용어 1000개 → 문단 334개면 용어당 1회 등장 (3용어 × 334 = 1002 슬롯)
scale 1000 1000 334

echo
echo "야간 실행 종료 $(date '+%Y-%m-%d %H:%M:%S')"
