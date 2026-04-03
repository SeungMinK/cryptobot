import client from "../api/client";

/**
 * 에러를 서버로 전송하여 error/ 폴더에 기록.
 * 실패해도 사용자에게 영향 없음.
 */
export function reportError(message: string, source?: string, stack?: string) {
  client
    .post("/error/report", {
      message,
      source,
      stack,
      url: window.location.href,
      user_agent: navigator.userAgent,
    })
    .catch(() => {
      // 에러 리포트 실패는 무시
    });
}

/**
 * 전역 에러 핸들러 등록. App 초기화 시 한 번 호출.
 */
export function setupGlobalErrorHandler() {
  // JS 런타임 에러
  window.onerror = (message, source, lineno, colno, error) => {
    reportError(
      String(message),
      `${source}:${lineno}:${colno}`,
      error?.stack
    );
  };

  // Promise 미처리 rejection
  window.onunhandledrejection = (event) => {
    const reason = event.reason;
    reportError(
      reason?.message || String(reason),
      "unhandledrejection",
      reason?.stack
    );
  };
}
