package com.rfp.app.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** 테스트 플러그인·JUnit 5·MockMvc 의존성이 캐시되도록 실제로 실행되는 seed 테스트. */
@WebMvcTest(PingController.class)
class PingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @DisplayName("REQ-F-000 TC-000: ping 은 200 을 돌려준다")
    void pingReturnsOk() throws Exception {
        mockMvc.perform(get("/api/ping")).andExpect(status().isOk());
    }

    @Test
    @DisplayName("REQ-F-000 TC-000: 검증 실패는 400 이다")
    void invalidBodyIsRejected() throws Exception {
        mockMvc.perform(post("/api/ping").contentType(MediaType.APPLICATION_JSON).content("{\"count\":0}"))
            .andExpect(status().isBadRequest());
    }
}
