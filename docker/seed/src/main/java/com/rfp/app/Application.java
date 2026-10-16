package com.rfp.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** 의존성 캐시용 seed 애플리케이션 (생성 앱의 Application 템플릿과 같은 형태). */
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
