# 생성 앱(Spring Boot + JUnit 5) 테스트 전용 이미지. 실행 시에는 --network none 으로 네트워크가 차단되므로
# Maven 의존성과 플러그인을 빌드 시점에 /opt/m2 에 미리 내려받는다 (seed 프로젝트의 pom 은 생성 앱 pom 템플릿과 같은 의존성).
FROM maven:3.9.9-eclipse-temurin-21

COPY seed /opt/seed
RUN cd /opt/seed \
    && mvn -B -q -Dmaven.repo.local=/opt/m2 test \
    && mvn -B -q -Dmaven.repo.local=/opt/m2 dependency:go-offline \
    && rm -rf /opt/seed/target \
    && chmod -R a+rX /opt/m2

COPY run-tests.sh /usr/local/bin/run-tests
RUN chmod 755 /usr/local/bin/run-tests \
    && useradd --create-home --uid 10001 runner

USER runner
ENV HOME=/tmp \
    MAVEN_OPTS="-Xmx768m -Djava.io.tmpdir=/tmp"
WORKDIR /tmp
