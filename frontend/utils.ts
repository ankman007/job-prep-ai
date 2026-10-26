import { store } from "./redux/store";
import { logoutAndClearTimer, loginAndStartTimer } from "./redux/slices/authSlice";
import { useSelector } from "react-redux";
import type { RootState } from '@/redux/store';
import { jwtDecode } from "jwt-decode";

interface DecodedToken {
  exp: number;
  [key: string]: any;
}

export const apiBaseURL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const fetchWithAuth = async (url: string, options: RequestInit = {}): Promise<Response> => {
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);

    const headers: HeadersInit = {
        ...options.headers,
        ...(accessToken && { Authorization: `Bearer ${accessToken}` }),
    };

    let response = await fetch(url, {
        ...options,
        headers,
    });

    if (response.status === 401) {
        console.warn("Unauthorized. Clearing tokens.");
        store.dispatch(logoutAndClearTimer());
    }
    return response;
};


export const isTokenExpired = (token: string): boolean => {
  try {
    const decoded: DecodedToken = jwtDecode(token);
    const now = Math.floor(Date.now() / 1000); 
    return decoded.exp < now;
  } catch (e) {
      return true;
  }
};
