"""개발 관리 + 코드 생성·테스트 (지시문 §13·§14, 단계 7, D-22: RFP_JAVA 발췌 이식).

생성 대상은 Spring Boot(Java 21) 프로토타입이며 납품 코드가 아니다. 에이전트는 파일 도구 없이 **구조화 출력으로 파일 내용**을
돌려주고, 코드가 작업 폴더(``14_Generated_App``)에 안전하게 쓰고(경로·확장자·크기 검사), 정적 검사와 Docker 격리 JUnit 실행을
한다. 결과는 코드 모듈(MOD)·테스트 케이스(TC)·결함(DEF) 엔티티로 들어간다.

``DevelopmentService`` 는 services 패키지와의 순환 import 를 피하려고 지연 로드한다.
"""

from __future__ import annotations

from typing import Any

__all__ = ["DevelopmentService"]


def __getattr__(name: str) -> Any:
    if name == "DevelopmentService":
        from proposal_agent.development.service import DevelopmentService

        return DevelopmentService
    raise AttributeError(name)
