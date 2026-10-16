"""생성 앱 고정 파일 (RFP_JAVA app_templates 발췌, LLM 없음): pom.xml·Application·application.properties·README.
pom 의 의존성은 Docker 테스트 이미지(docker/seed/pom.xml)와 같아야 오프라인 빌드가 된다.
"""

from __future__ import annotations

from proposal_agent.development.constants import (
    APPLICATION_CLASS_PATH,
    APPLICATION_PROPERTIES_PATH,
    BASE_PACKAGE,
    FIXED_DEPENDENCIES,
    JAVA_VERSION,
    POM_PATH,
    README_PATH,
    SPRING_BOOT_VERSION,
)
from proposal_agent.models import ApiSpec, CodeModule


def pom_xml() -> str:
    deps = []
    for artifact in FIXED_DEPENDENCIES:
        scope = "\n      <scope>test</scope>" if artifact == "spring-boot-starter-test" else ""
        deps.append(
            f"    <dependency>\n      <groupId>org.springframework.boot</groupId>\n      <artifactId>{artifact}</artifactId>{scope}\n    </dependency>"
        )
    dependencies = "\n".join(deps)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{SPRING_BOOT_VERSION}</version>
    <relativePath/>
  </parent>
  <groupId>com.app</groupId>
  <artifactId>app</artifactId>
  <version>0.1.0</version>
  <name>generated-app</name>
  <properties>
    <java.version>{JAVA_VERSION}</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
{dependencies}
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""


APPLICATION_JAVA = f"""package {BASE_PACKAGE};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** 생성 앱 진입점 (코드 고정 템플릿). 정적 자원(src/main/resources/static)은 / 로 서비스된다. */
@SpringBootApplication
public class Application {{
    public static void main(String[] args) {{
        SpringApplication.run(Application.class, args);
    }}
}}
"""

APPLICATION_PROPERTIES = """server.port=8080
spring.main.banner-mode=off
spring.jackson.default-property-inclusion=non_null
# 생성 앱의 데이터 파일 위치 (JSON). 테스트는 임시 디렉터리로 바꿔 쓴다.
app.data-dir=./data
"""


def readme_md(project_name: str, modules: list[CodeModule], apis: list[ApiSpec]) -> str:
    mods = "\n".join(f"- `{m.path}`: {m.description}" for m in modules) or "- (없음)"
    endpoints = (
        "\n".join(
            f"- `{a.method} {a.path}`: {a.request_schema.get('description', a.name)}" for a in apis
        )
        or "- (없음)"
    )
    return f"""# {project_name} — 생성 프로토타입

제안·설계 데이터로 생성한 Spring Boot(Java {JAVA_VERSION}) 프로토타입입니다. **납품 코드가 아니며** 설계 검증·개발 착수 자료입니다.
실제 로그인/권한 인증은 구현되어 있지 않습니다.

## 실행 (JDK {JAVA_VERSION}, Maven 필요)

```bash
mvn spring-boot:run
```

## 테스트 (JUnit 5)

```bash
mvn test
```

## REST API

{endpoints}

## 모듈

{mods}
"""


def template_files(
    project_name: str, modules: list[CodeModule], apis: list[ApiSpec]
) -> dict[str, str]:
    return {
        POM_PATH: pom_xml(),
        APPLICATION_CLASS_PATH: APPLICATION_JAVA,
        APPLICATION_PROPERTIES_PATH: APPLICATION_PROPERTIES,
        README_PATH: readme_md(project_name, modules, apis),
    }


__all__ = ["APPLICATION_JAVA", "APPLICATION_PROPERTIES", "pom_xml", "readme_md", "template_files"]
