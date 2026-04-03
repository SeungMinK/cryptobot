export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

export interface UserResponse {
  id: number;
  username: string;
  display_name: string | null;
  is_admin: boolean;
}
