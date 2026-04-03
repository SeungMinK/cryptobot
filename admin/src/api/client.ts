import axios from "axios";

const API_BASE_URL = "http://localhost:8000/api";

const client = axios.create({
  baseURL: API_BASE_URL,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    // 500 에러는 서버 로그로 전송
    if (error.response?.status >= 500) {
      const url = error.config?.url || "unknown";
      client
        .post("/error/report", {
          message: `API ${error.response.status}: ${url}`,
          source: "axios-interceptor",
          stack: JSON.stringify(error.response?.data)?.slice(0, 500),
          url: window.location.href,
        })
        .catch(() => {});
    }
    return Promise.reject(error);
  }
);

export default client;
