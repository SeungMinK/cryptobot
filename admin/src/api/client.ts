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
    // 401/500은 개별 호출자가 처리. 인터셉터에서 강제 로그아웃하지 않음.
    return Promise.reject(error);
  }
);

export default client;
