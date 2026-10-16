package com.rfp.app;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/** 전체 컨텍스트 로딩 의존성까지 캐시한다. */
@SpringBootTest
class ApplicationTest {

    @Test
    @DisplayName("REQ-F-000 TC-000: 컨텍스트가 뜬다")
    void contextLoads() {
    }
}
