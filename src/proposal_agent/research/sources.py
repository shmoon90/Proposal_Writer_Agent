"""출처 신뢰도 분류 (결정적, 도메인·경로 규칙).

에이전트가 제안한 ``trust``는 참고값으로 보존하고(``trust``), 코드가 판정한 값은 ``trust_by_rule``에 따로 기록한다.
규칙이 더 낮은 등급을 판정하면 표시용 등급은 규칙 쪽을 따른다 (커뮤니티 글을 공식 문서로 올려 적는 것을 막는다).
"""

from __future__ import annotations

from urllib.parse import urlparse

from proposal_agent.models.enums import SourceTrust

OFFICIAL_DOC_HOSTS: tuple[str, ...] = (
    "docs.oracle.com",
    "learn.microsoft.com",
    "docs.microsoft.com",
    "docs.python.org",
    "docs.spring.io",
    "spring.io",
    "nodejs.org",
    "react.dev",
    "angular.dev",
    "vuejs.org",
    "docs.djangoproject.com",
    "fastapi.tiangolo.com",
    "kubernetes.io",
    "docs.docker.com",
    "www.postgresql.org",
    "dev.mysql.com",
    "mariadb.com",
    "redis.io",
    "nginx.org",
    "tomcat.apache.org",
    "httpd.apache.org",
    "kafka.apache.org",
    "docs.aws.amazon.com",
    "cloud.google.com",
    "docs.anthropic.com",
    "platform.claude.com",
    "code.claude.com",
    "www.egovframe.go.kr",
    "egovframe.go.kr",
    "developer.mozilla.org",
    "openjdk.org",
    "dotnet.microsoft.com",
    "docs.gradle.org",
    "maven.apache.org",
    "www.elastic.co",
    "docs.oracle.com",
    "www.ibm.com",
    "www.redhat.com",
)
STANDARD_HOSTS: tuple[str, ...] = (
    "www.ietf.org",
    "datatracker.ietf.org",
    "www.w3.org",
    "www.iso.org",
    "www.rfc-editor.org",
    "owasp.org",
    "www.kisa.or.kr",
    "www.nist.gov",
    "csrc.nist.gov",
    "www.law.go.kr",
    "www.tta.or.kr",
    "ecma-international.org",
)
COMMUNITY_HOSTS: tuple[str, ...] = (
    "stackoverflow.com",
    "medium.com",
    "velog.io",
    "tistory.com",
    "blog.naver.com",
    "reddit.com",
    "dev.to",
    "qiita.com",
    "brunch.co.kr",
    "github.com",
    "gist.github.com",
    "youtube.com",
    "news.ycombinator.com",
)
_RANK = {
    SourceTrust.OFFICIAL_DOC: 4,
    SourceTrust.STANDARD: 4,
    SourceTrust.VENDOR_GUIDE: 3,
    SourceTrust.COMMUNITY: 1,
    SourceTrust.UNKNOWN: 0,
}


def classify_url(url: str) -> SourceTrust:
    try:
        parsed = urlparse(url)
    except ValueError:
        return SourceTrust.UNKNOWN
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    if not host:
        return SourceTrust.UNKNOWN
    if any(host == h or host.endswith("." + h) for h in STANDARD_HOSTS):
        return SourceTrust.STANDARD
    if any(host == h or host.endswith("." + h) for h in COMMUNITY_HOSTS):
        return SourceTrust.COMMUNITY
    if any(host == h or host.endswith("." + h) for h in OFFICIAL_DOC_HOSTS):
        return SourceTrust.OFFICIAL_DOC
    if (
        host.startswith(("docs.", "developer.", "developers.", "learn."))
        or "/docs" in path
        or "/documentation" in path
        or "/guide" in path
    ):
        return SourceTrust.VENDOR_GUIDE
    return SourceTrust.UNKNOWN


def effective_trust(agent_trust: SourceTrust, rule_trust: SourceTrust) -> SourceTrust:
    """규칙이 더 낮게 보면 규칙을 따르고, 규칙이 unknown이면 에이전트 값을 쓴다."""
    if rule_trust == SourceTrust.UNKNOWN:
        return agent_trust
    return rule_trust if _RANK[rule_trust] < _RANK[agent_trust] else agent_trust
