package com.rfp.app.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 웹·검증 의존성이 실제로 로드되게 하는 seed 컨트롤러. */
@RestController
@RequestMapping("/api/ping")
public class PingController {

    public record PingRequest(@Min(1) int count) {}

    @GetMapping
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @PostMapping
    public Map<String, Integer> echo(@Valid @RequestBody PingRequest request) {
        return Map.of("count", request.count());
    }
}
