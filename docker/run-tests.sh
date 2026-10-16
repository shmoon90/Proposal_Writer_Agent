#!/bin/sh
# 고정 실행 스크립트 (이미지에 포함). 읽기 전용으로 마운트된 /app 을 /tmp/work 로 복사한 뒤
# 오프라인 Maven 으로 JUnit 테스트를 실행하고 surefire 보고서를 /out/surefire 로 복사한다.
# 인자를 받지 않으며, 오케스트레이터의 run_command 가 이 스크립트만 호출한다.
set -u
rm -rf /tmp/work
mkdir -p /tmp/work /out/surefire
cp -r /app/. /tmp/work/
cd /tmp/work || exit 125
# jansi 네이티브 라이브러리(tmpfs noexec)와 색상 출력을 끈다. 저장소는 읽기 전용 /opt/m2 를 오프라인으로 쓴다.
export MAVEN_OPTS="${MAVEN_OPTS:-} -Djansi.passthrough=true -Dorg.jline.terminal.dumb=true"
mvn -o -B -Dmaven.repo.local=/opt/m2 -Dstyle.color=never -Dmaven.test.failure.ignore=false test
rc=$?
cp target/surefire-reports/TEST-*.xml /out/surefire/ 2>/dev/null
exit $rc
